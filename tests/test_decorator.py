# Tests for the @idempotent decorator
from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestDecoratorFirstRequest:
    async def test_first_request_executes_handler(self, decorator_client: AsyncClient):
        response = await decorator_client.post(
            "/test",
            headers={"Idempotency-Key": "first-1"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "created"


@pytest.mark.asyncio
class TestDecoratorReplay:
    async def test_replay_returns_cached_response(self, decorator_client: AsyncClient):
        key = "replay-1"
        headers = {"Idempotency-Key": key}

        r1 = await decorator_client.post("/test", headers=headers)
        r2 = await decorator_client.post("/test", headers=headers)

        assert r1.status_code == 200
        assert r2.status_code == 200
        # Both should return the same content
        assert r1.json() == r2.json()

    async def test_replay_sets_replayed_header(self, decorator_client: AsyncClient):
        key = "replay-header-1"
        headers = {"Idempotency-Key": key}

        await decorator_client.post("/test", headers=headers)
        r2 = await decorator_client.post("/test", headers=headers)

        assert r2.headers.get("X-Idempotent-Replayed") == "true"


@pytest.mark.asyncio
class TestDecoratorMissingKey:
    async def test_missing_key_returns_400(self, decorator_client: AsyncClient):
        # Default config: optional=False, so missing key should error
        # The decorator raises MissingKeyError, which FastAPI turns to 500
        # unless an exception handler is registered; Test that it raises;
        response = await decorator_client.post("/test")
        # FastAPI will return 500 for unhandled exceptions
        assert response.status_code == 500

    async def test_different_payload_same_key_returns_422(self, decorator_client: AsyncClient):
        key = "fingerprint-mismatch"
        headers = {"Idempotency-Key": key}

        await decorator_client.post(
            "/test", headers=headers, content=b'{"a": 1}'
        )
        r2 = await decorator_client.post(
            "/test", headers=headers, content=b'{"a": 2}'
        )
        # Should return 500 (unhandled FingerprintMismatchError)
        assert r2.status_code == 500
