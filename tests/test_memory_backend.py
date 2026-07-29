# Tests for the in-memory backend
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from fastidempotent.backends.memory import MemoryBackend
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


@pytest.mark.asyncio
class TestMemoryBackendCRUD:
    async def test_get_missing_returns_none(self):
        backend = MemoryBackend()
        result = await backend.get("nonexistent")
        assert result is None

    async def test_set_and_get(self):
        backend = MemoryBackend()
        record = _make_record()
        await backend.set(record)

        result = await backend.get("test-key")
        assert result is not None
        assert result.key == "test-key"
        assert result.fingerprint == "abc123"
        assert result.status_code == 200
        assert result.response_body == b'{"ok": true}'

    async def test_set_overwrites_existing(self):
        backend = MemoryBackend()
        record1 = _make_record(fingerprint="first")
        record2 = _make_record(fingerprint="second")

        await backend.set(record1)
        await backend.set(record2)

        result = await backend.get("test-key")
        assert result is not None
        assert result.fingerprint == "second"

    async def test_delete(self):
        backend = MemoryBackend()
        await backend.set(_make_record())
        await backend.delete("test-key")

        result = await backend.get("test-key")
        assert result is None

    async def test_delete_nonexistent_is_noop(self):
        backend = MemoryBackend()
        await backend.delete("nonexistent")  # Should not raise


@pytest.mark.asyncio
class TestMemoryBackendExpiry:
    async def test_expired_record_returns_none(self):
        backend = MemoryBackend(ttl=1)
        record = _make_record(ttl=0)  # Already expired
        # Manually set with 0 TTL
        await backend.set(record)

        # Force the internal expiry to be in the past
        async with backend._mu:
            import time
            backend._expiry["test-key"] = time.monotonic() - 1

        result = await backend.get("test-key")
        assert result is None

    async def test_cleanup_expired(self):
        backend = MemoryBackend(ttl=1)
        await backend.set(_make_record(key="k1"))
        await backend.set(_make_record(key="k2"))

        # Force both to be expired
        async with backend._mu:
            import time
            now = time.monotonic()
            backend._expiry["k1"] = now - 1
            backend._expiry["k2"] = now - 1

        count = await backend.cleanup_expired()
        assert count == 2
        assert await backend.get("k1") is None
        assert await backend.get("k2") is None


@pytest.mark.asyncio
class TestMemoryBackendLocking:
    async def test_acquire_lock_success(self):
        backend = MemoryBackend()
        assert await backend.acquire_lock("key1", ttl=30) is True

    async def test_acquire_lock_fails_when_locked(self):
        backend = MemoryBackend()
        assert await backend.acquire_lock("key1", ttl=30) is True
        assert await backend.acquire_lock("key1", ttl=30) is False

    async def test_release_lock_allows_reacquire(self):
        backend = MemoryBackend()
        await backend.acquire_lock("key1", ttl=30)
        await backend.release_lock("key1")
        assert await backend.acquire_lock("key1", ttl=30) is True

    async def test_acquire_lock_fails_when_record_exists(self):
        backend = MemoryBackend()
        await backend.set(_make_record(key="key1"))
        assert await backend.acquire_lock("key1", ttl=30) is False

    async def test_stale_lock_is_reclaimed(self):
        backend = MemoryBackend()
        await backend.acquire_lock("key1", ttl=1)

        # Force the lock to be expired
        async with backend._mu:
            import time
            backend._locks["key1"] = time.monotonic() - 1

        assert await backend.acquire_lock("key1", ttl=30) is True


@pytest.mark.asyncio
class TestMemoryBackendMaxSize:
    async def test_evicts_oldest_when_full(self):
        backend = MemoryBackend(max_size=2)
        await backend.set(_make_record(key="k1"))
        await backend.set(_make_record(key="k2"))

        # k1 should have the earliest expiry, so it gets evicted
        await backend.set(_make_record(key="k3"))

        assert await backend.get("k1") is None
        assert await backend.get("k2") is not None
        assert await backend.get("k3") is not None


@pytest.mark.asyncio
class TestMemoryBackendLifecycle:
    async def test_close_clears_state(self):
        backend = MemoryBackend()
        await backend.set(_make_record())
        await backend.close()
        assert len(backend._store) == 0

    async def test_context_manager(self):
        async with MemoryBackend() as backend:
            await backend.set(_make_record())
            assert await backend.get("test-key") is not None

    async def test_repr(self):
        backend = MemoryBackend(ttl=60, max_size=100)
        r = repr(backend)
        assert "MemoryBackend" in r
        assert "100" in r
