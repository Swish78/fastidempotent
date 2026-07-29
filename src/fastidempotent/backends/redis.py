# Redis backend for idempotency storage
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from fastidempotent.backends.base import BaseBackend
from fastidempotent.exceptions import BackendError
from fastidempotent.models import IdempotencyRecord, IdempotencyStatus

if TYPE_CHECKING:
    from redis.asyncio import Redis


class RedisBackend(BaseBackend):
    """
    Redis-backed idempotency store;

    Recommended for production; Supports distributed deployments
    with multiple workers/processes; Uses native Redis TTL for
    automatic expiry and ``SET NX`` for atomic locking;
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        key_prefix: str = "idempotent:",
        ttl: int = 3600,
        client: Redis | None = None,
    ) -> None:
        self._url = url
        self._prefix = key_prefix
        self._ttl = ttl
        self._client = client
        self._owns_client = client is None

    #  Key helpers 

    def _record_key(self, key: str) -> str:
        return f"{self._prefix}record:{key}"

    def _lock_key(self, key: str) -> str:
        return f"{self._prefix}lock:{key}"

    #  Lifecycle 

    async def init(self) -> None:
        if self._client is None:
            try:
                from redis.asyncio import from_url

                self._client = from_url(self._url, decode_responses=False)
                self._owns_client = True
            except ImportError as exc:
                raise BackendError(
                    "redis package is required for RedisBackend. "
                    "Install with: pip install fastidempotent[redis]",
                    cause=exc,
                )
        # Verify connectivity
        await self._client.ping()  # type: ignore[union-attr]

    async def close(self) -> None:
        if self._client and self._owns_client:
            await self._client.aclose()  # type: ignore[union-attr]
            self._client = None

    #  Core CRUD 

    async def get(self, key: str) -> IdempotencyRecord | None:
        assert self._client is not None, "Backend not initialised. Call init() first."
        raw: bytes | None = await self._client.get(self._record_key(key))
        if raw is None:
            return None
        return self._deserialize(raw)

    async def set(self, record: IdempotencyRecord) -> None:
        assert self._client is not None
        rkey = self._record_key(record.key)
        data = self._serialize(record)
        await self._client.set(rkey, data, ex=self._ttl)
        # Release the lock now that the record is COMPLETE
        await self._client.delete(self._lock_key(record.key))

    async def delete(self, key: str) -> None:
        assert self._client is not None
        await self._client.delete(self._record_key(key), self._lock_key(key))

    #  Locking 

    async def acquire_lock(self, key: str, ttl: int) -> bool:
        assert self._client is not None
        # SET NX with EX → atomic "create if not exists" with auto-expiry
        acquired: bool | None = await self._client.set(
            self._lock_key(key),
            b"1",
            nx=True,
            ex=ttl,
        )
        return acquired is True

    async def release_lock(self, key: str) -> None:
        assert self._client is not None
        await self._client.delete(self._lock_key(key))
        # Also remove any partial record
        await self._client.delete(self._record_key(key))

    #  Maintenance 

    async def cleanup_expired(self) -> int:
        # Redis handles expiry natively via TTL; No manual cleanup needed;
        return 0

    #  Serialization 

    @staticmethod
    def _serialize(record: IdempotencyRecord) -> bytes:
        data: dict[str, Any] = {
            "key": record.key,
            "fingerprint": record.fingerprint,
            "status": record.status.value,
            "status_code": record.status_code,
            "response_headers": record.response_headers,
            "response_body": record.response_body.hex() if record.response_body else None,
            "created_at": record.created_at.isoformat(),
            "expires_at": record.expires_at.isoformat(),
        }
        return json.dumps(data).encode("utf-8")

    @staticmethod
    def _deserialize(raw: bytes) -> IdempotencyRecord:
        data = json.loads(raw)
        return IdempotencyRecord(
            key=data["key"],
            fingerprint=data["fingerprint"],
            status=IdempotencyStatus(data["status"]),
            status_code=data.get("status_code"),
            response_headers=data.get("response_headers", {}),
            response_body=bytes.fromhex(data["response_body"]) if data.get("response_body") else None,
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
        )

    def __repr__(self) -> str:
        return f"<RedisBackend url={self._url!r} prefix={self._prefix!r} ttl={self._ttl}>"
