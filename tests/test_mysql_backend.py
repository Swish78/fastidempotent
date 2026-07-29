# Tests for the MySQL backend
# These tests require a running MySQL instance or are skipped;
from __future__ import annotations

import pytest

# Skip all tests if asyncmy is not installed or no test DB is available;
pytest.importorskip("asyncmy")

from datetime import datetime, timedelta, timezone

from fastidempotent.backends.mysql import MySQLBackend
from fastidempotent.models import IdempotencyRecord, IdempotencyStatus

TEST_DB_URL = "mysql+asyncmy://root@localhost/fastidempotent_test"


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
async def mysql_backend():
    """MySQL backend — requires a running test db;"""
    backend = MySQLBackend(
        url=TEST_DB_URL,
        table_name="test_idempotency",
        ttl=3600,
    )
    try:
        await backend.init()
    except Exception:
        pytest.skip("MySQL test database is not available")
    yield backend
    await backend.cleanup_expired()
    await backend.close()


@pytest.mark.asyncio
class TestMySQLBackendCRUD:
    async def test_set_and_get(self, mysql_backend: MySQLBackend):
        record = _make_record(key="mysql-test-1")
        await mysql_backend.set(record)

        result = await mysql_backend.get("mysql-test-1")
        assert result is not None
        assert result.key == "mysql-test-1"
        await mysql_backend.delete("mysql-test-1")

    async def test_delete(self, mysql_backend: MySQLBackend):
        await mysql_backend.set(_make_record(key="mysql-del"))
        await mysql_backend.delete("mysql-del")
        assert await mysql_backend.get("mysql-del") is None


@pytest.mark.asyncio
class TestMySQLBackendLocking:
    async def test_acquire_and_release(self, mysql_backend: MySQLBackend):
        assert await mysql_backend.acquire_lock("mysql-lock-1", ttl=30) is True
        assert await mysql_backend.acquire_lock("mysql-lock-1", ttl=30) is False
        await mysql_backend.release_lock("mysql-lock-1")
        assert await mysql_backend.acquire_lock("mysql-lock-1", ttl=30) is True
        await mysql_backend.release_lock("mysql-lock-1")
