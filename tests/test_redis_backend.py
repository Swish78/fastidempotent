# Tests for the Redis backend (uses fakeredis)
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from fastidempotent.backends.redis import RedisBackend
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
def fake_redis_client():
    """Create a fakeredis async client;"""
    import fakeredis.aioredis

    return fakeredis.aioredis.FakeRedis(decode_responses=False)


@pytest.fixture
def redis_backend(fake_redis_client) -> RedisBackend:
    """RedisBackend wired to fakeredis;"""
    return RedisBackend(
        url="redis://fake",
        key_prefix="test:",
        ttl=3600,
        client=fake_redis_client,
    )


@pytest.mark.asyncio
class TestRedisBackendCRUD:
    async def test_get_missing_returns_none(self, redis_backend: RedisBackend):
        result = await redis_backend.get("nonexistent")
        assert result is None

    async def test_set_and_get(self, redis_backend: RedisBackend):
        record = _make_record()
        await redis_backend.set(record)

        result = await redis_backend.get("test-key")
        assert result is not None
        assert result.key == "test-key"
        assert result.fingerprint == "abc123"
        assert result.status == IdempotencyStatus.COMPLETE
        assert result.status_code == 200

    async def test_set_overwrites(self, redis_backend: RedisBackend):
        await redis_backend.set(_make_record(fingerprint="v1"))
        await redis_backend.set(_make_record(fingerprint="v2"))

        result = await redis_backend.get("test-key")
        assert result is not None
        assert result.fingerprint == "v2"

    async def test_delete(self, redis_backend: RedisBackend):
        await redis_backend.set(_make_record())
        await redis_backend.delete("test-key")

        result = await redis_backend.get("test-key")
        assert result is None

    async def test_delete_nonexistent_is_noop(self, redis_backend: RedisBackend):
        await redis_backend.delete("nonexistent")


@pytest.mark.asyncio
class TestRedisBackendLocking:
    async def test_acquire_lock_success(self, redis_backend: RedisBackend):
        assert await redis_backend.acquire_lock("key1", ttl=30) is True

    async def test_acquire_lock_fails_when_locked(self, redis_backend: RedisBackend):
        assert await redis_backend.acquire_lock("key1", ttl=30) is True
        assert await redis_backend.acquire_lock("key1", ttl=30) is False

    async def test_release_lock_allows_reacquire(self, redis_backend: RedisBackend):
        await redis_backend.acquire_lock("key1", ttl=30)
        await redis_backend.release_lock("key1")
        assert await redis_backend.acquire_lock("key1", ttl=30) is True


@pytest.mark.asyncio
class TestRedisBackendSerialization:
    async def test_roundtrip_preserves_body(self, redis_backend: RedisBackend):
        body = b'\x00\x01\x02\xff binary data'
        record = _make_record()
        record.response_body = body
        await redis_backend.set(record)

        result = await redis_backend.get("test-key")
        assert result is not None
        assert result.response_body == body

    async def test_roundtrip_preserves_none_body(self, redis_backend: RedisBackend):
        record = _make_record()
        record.response_body = None
        await redis_backend.set(record)

        result = await redis_backend.get("test-key")
        assert result is not None
        assert result.response_body is None


@pytest.mark.asyncio
class TestRedisBackendRepr:
    async def test_repr(self, redis_backend: RedisBackend):
        r = repr(redis_backend)
        assert "RedisBackend" in r
        assert "test:" in r
