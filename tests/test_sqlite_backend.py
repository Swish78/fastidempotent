# Tests for the SQLite backend
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from fastidempotent.backends.sqlite import SQLiteBackend
from fastidempotent.models import IdempotencyRecord, IdempotencyStatus


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
async def sqlite_backend():
    """In-memory SQLite backend for testing;"""
    backend = SQLiteBackend(
        url="sqlite+aiosqlite://",  # in-memory
        table_name="test_idempotency",
        ttl=3600,
    )
    await backend.init()
    yield backend
    await backend.close()


@pytest.mark.asyncio
class TestSQLiteBackendCRUD:
    async def test_get_missing_returns_none(self, sqlite_backend: SQLiteBackend):
        result = await sqlite_backend.get("nonexistent")
        assert result is None

    async def test_set_and_get(self, sqlite_backend: SQLiteBackend):
        record = _make_record()
        await sqlite_backend.set(record)

        result = await sqlite_backend.get("test-key")
        assert result is not None
        assert result.key == "test-key"
        assert result.fingerprint == "abc123"
        assert result.status == IdempotencyStatus.COMPLETE

    async def test_set_overwrites(self, sqlite_backend: SQLiteBackend):
        await sqlite_backend.set(_make_record(fingerprint="v1"))
        await sqlite_backend.set(_make_record(fingerprint="v2"))

        result = await sqlite_backend.get("test-key")
        assert result is not None
        assert result.fingerprint == "v2"

    async def test_delete(self, sqlite_backend: SQLiteBackend):
        await sqlite_backend.set(_make_record())
        await sqlite_backend.delete("test-key")

        result = await sqlite_backend.get("test-key")
        assert result is None


@pytest.mark.asyncio
class TestSQLiteBackendLocking:
    async def test_acquire_lock_success(self, sqlite_backend: SQLiteBackend):
        assert await sqlite_backend.acquire_lock("key1", ttl=30) is True

    async def test_acquire_lock_fails_when_locked(self, sqlite_backend: SQLiteBackend):
        assert await sqlite_backend.acquire_lock("key1", ttl=30) is True
        assert await sqlite_backend.acquire_lock("key1", ttl=30) is False

    async def test_release_lock_allows_reacquire(self, sqlite_backend: SQLiteBackend):
        await sqlite_backend.acquire_lock("key1", ttl=30)
        await sqlite_backend.release_lock("key1")
        assert await sqlite_backend.acquire_lock("key1", ttl=30) is True


@pytest.mark.asyncio
class TestSQLiteBackendExpiry:
    async def test_expired_record_returns_none(self, sqlite_backend: SQLiteBackend):
        record = _make_record(ttl=-1)  # Already expired
        await sqlite_backend.set(record)

        result = await sqlite_backend.get("test-key")
        assert result is None

    async def test_cleanup_expired(self, sqlite_backend: SQLiteBackend):
        await sqlite_backend.set(_make_record(key="fresh", ttl=3600))
        await sqlite_backend.set(_make_record(key="stale", ttl=-1))

        count = await sqlite_backend.cleanup_expired()
        assert count >= 1

        assert await sqlite_backend.get("fresh") is not None
        assert await sqlite_backend.get("stale") is None
