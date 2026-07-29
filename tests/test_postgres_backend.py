# Tests for the PostgreSQL backend
# These tests require a running PostgreSQL instance or are skipped;
from __future__ import annotations

import pytest

# Skip all tests in this mod if asyncpg is not installed
# or no test db is available;
pytest.importorskip("asyncpg")

from datetime import datetime, timedelta, timezone

from fastidempotent.backends.postgres import PostgresBackend
from fastidempotent.models import IdempotencyRecord, IdempotencyStatus

# Set to a real test db URL or use an env var;
# These tests are marked as integration tests;
TEST_DB_URL = "postgresql+asyncpg://localhost/fastidempotent_test"


def _make_record(
    key: str = "test-key",
    fingerprint: str = "abc123",
    status: IdempotencyStatus = IdempotencyStatus.COMPLETE,
    ttl: int = 3600,
) -> IdempotencyRecord:
    now = datetime.now(tz=timezone.utc)
    return IdempotencyRecord(
        key=key,
        fingerprint=fingerprint,
        status=status,
        status_code=200,
        response_headers={"content-type": "application/json"},
        response_body=b'{"ok": true}',
        created_at=now,
        expires_at=now + timedelta(seconds=ttl),
    )


@pytest.fixture
async def pg_backend():
    """PostgreSQL backend — requires a running test db;"""
    backend = PostgresBackend(
        url=TEST_DB_URL,
        table_name="test_idempotency",
        ttl=3600,
    )
    try:
        await backend.init()
    except Exception:
        pytest.skip("PostgreSQL test database is not available")
    yield backend
    # Cleanup: drop all test records
    await backend.cleanup_expired()
    await backend.close()


@pytest.mark.asyncio
class TestPostgresBackendCRUD:
    async def test_set_and_get(self, pg_backend: PostgresBackend):
        record = _make_record(key="pg-test-1")
        await pg_backend.set(record)

        result = await pg_backend.get("pg-test-1")
        assert result is not None
        assert result.key == "pg-test-1"
        await pg_backend.delete("pg-test-1")

    async def test_delete(self, pg_backend: PostgresBackend):
        await pg_backend.set(_make_record(key="pg-del"))
        await pg_backend.delete("pg-del")
        assert await pg_backend.get("pg-del") is None


@pytest.mark.asyncio
class TestPostgresBackendLocking:
    async def test_acquire_and_release(self, pg_backend: PostgresBackend):
        assert await pg_backend.acquire_lock("pg-lock-1", ttl=30) is True
        assert await pg_backend.acquire_lock("pg-lock-1", ttl=30) is False
        await pg_backend.release_lock("pg-lock-1")
        assert await pg_backend.acquire_lock("pg-lock-1", ttl=30) is True
        await pg_backend.release_lock("pg-lock-1")
