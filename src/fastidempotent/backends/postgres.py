# PostgreSQL backend for idempotency storage (via SQLAlchemy + asyncpg)
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import json
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from fastidempotent.backends.base import BaseBackend
from fastidempotent.exceptions import BackendError
from fastidempotent.models import IdempotencyRecord, IdempotencyStatus

#  Table definition 

metadata = sa.MetaData()


def _build_table(table_name: str) -> sa.Table:
    return sa.Table(
        table_name,
        metadata,
        sa.Column("key", sa.String(256), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("status_code", sa.Integer, nullable=True),
        sa.Column("response_headers", sa.Text, nullable=True),
        sa.Column("response_body", sa.LargeBinary, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        extend_existing=True,
    )


class PostgresBackend(BaseBackend):
    """
    PostgreSQL-backed idempotency store via SQLAlchemy async + asyncpg;

    Recommended for production alongside Redis; Supports concurrent access
    via ``SELECT ;;; FOR UPDATE SKIP LOCKED`` for safe distributed locking;
    """

    def __init__(
        self,
        url: str = "postgresql+asyncpg://localhost/fastidempotent",
        table_name: str = "idempotency_keys",
        ttl: int = 3600,
        pool_size: int = 5,
    ) -> None:
        self._url = url
        self._ttl = ttl
        self._table = _build_table(table_name)
        self._engine = create_async_engine(
            self._url, echo=False, pool_size=pool_size, max_overflow=10
        )
        self._session_factory = sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )

    #  Lifecycle 

    async def init(self) -> None:
        try:
            async with self._engine.begin() as conn:
                await conn.run_sync(metadata.create_all)
        except Exception as exc:
            raise BackendError(
                f"Failed to initialise PostgreSQL backend: {exc}", cause=exc
            )

    async def close(self) -> None:
        await self._engine.dispose()

    #  Core CRUD 

    async def get(self, key: str) -> IdempotencyRecord | None:
        async with self._session_factory() as session:
            stmt = sa.select(self._table).where(self._table.c.key == key)
            result = await session.execute(stmt)
            row = result.mappings().first()
            if row is None:
                return None

            now = datetime.now(tz=timezone.utc)
            expires_at = row["expires_at"]
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if now >= expires_at:
                await session.execute(
                    sa.delete(self._table).where(self._table.c.key == key)
                )
                await session.commit()
                return None

            return self._row_to_record(row)

    async def set(self, record: IdempotencyRecord) -> None:
        async with self._session_factory() as session:
            values: dict[str, Any] = {
                "key": record.key,
                "fingerprint": record.fingerprint,
                "status": record.status.value,
                "status_code": record.status_code,
                "response_headers": json.dumps(record.response_headers),
                "response_body": record.response_body,
                "created_at": record.created_at,
                "expires_at": record.expires_at,
            }

            # PostgreSQL native upsert (INSERT ;;; ON CONFLICT DO UPDATE)
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            stmt = pg_insert(self._table).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["key"],
                set_={
                    "fingerprint": stmt.excluded.fingerprint,
                    "status": stmt.excluded.status,
                    "status_code": stmt.excluded.status_code,
                    "response_headers": stmt.excluded.response_headers,
                    "response_body": stmt.excluded.response_body,
                    "expires_at": stmt.excluded.expires_at,
                },
            )
            await session.execute(stmt)
            await session.commit()

    async def delete(self, key: str) -> None:
        async with self._session_factory() as session:
            await session.execute(
                sa.delete(self._table).where(self._table.c.key == key)
            )
            await session.commit()

    #  Locking 

    async def acquire_lock(self, key: str, ttl: int) -> bool:
        async with self._session_factory() as session:
            now = datetime.now(tz=timezone.utc)

            # Clean up expired record for this key first
            await session.execute(
                sa.delete(self._table).where(
                    self._table.c.key == key,
                    self._table.c.expires_at <= now,
                )
            )

            # Attempt to insert a PENDING row; If the key already exists
            # (not expired), the unique constraint will cause a conflict;
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            stmt = pg_insert(self._table).values(
                key=key,
                fingerprint="",
                status=IdempotencyStatus.PENDING.value,
                status_code=None,
                response_headers=json.dumps({}),
                response_body=None,
                created_at=now,
                expires_at=now + timedelta(seconds=ttl),
            )
            # ON CONFLICT DO NOTHING → returns 0 rows if key existed
            stmt = stmt.on_conflict_do_nothing(index_elements=["key"])
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0  # type: ignore[union-attr]

    async def release_lock(self, key: str) -> None:
        await self.delete(key)

    #  Maintenance 

    async def cleanup_expired(self) -> int:
        now = datetime.now(tz=timezone.utc)
        async with self._session_factory() as session:
            result = await session.execute(
                sa.delete(self._table).where(self._table.c.expires_at <= now)
            )
            await session.commit()
            return result.rowcount  # type: ignore[return-value]

    #  Private helpers 

    @staticmethod
    def _row_to_record(row: Any) -> IdempotencyRecord:
        created_at = row["created_at"]
        expires_at = row["expires_at"]
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        return IdempotencyRecord(
            key=row["key"],
            fingerprint=row["fingerprint"],
            status=IdempotencyStatus(row["status"]),
            status_code=row["status_code"],
            response_headers=json.loads(row["response_headers"]) if row["response_headers"] else {},
            response_body=row["response_body"],
            created_at=created_at,
            expires_at=expires_at,
        )

    def __repr__(self) -> str:
        return f"<PostgresBackend url={self._url!r} ttl={self._ttl}>"
