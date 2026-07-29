# Tests for the idempotency mw
from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestMiddlewareBasicFlow:
    async def test_first_request_succeeds(self, middleware_client: AsyncClient):
        response = await middleware_client.post(
            "/test",
            headers={"Idempotency-Key": "mw-first-1"},
        )
        assert response.status_code == 200
        assert response.json()["message"] == "created"

    async def test_replay_returns_cached(self, middleware_client: AsyncClient):
        key = "mw-replay-1"
        headers = {"Idempotency-Key": key}

        r1 = await middleware_client.post("/test", headers=headers)
        r2 = await middleware_client.post("/test", headers=headers)

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json() == r2.json()

    async def test_replay_sets_replayed_header(self, middleware_client: AsyncClient):
        key = "mw-replay-header"
        headers = {"Idempotency-Key": key}

        await middleware_client.post("/test", headers=headers)
        r2 = await middleware_client.post("/test", headers=headers)

        assert r2.headers.get("X-Idempotent-Replayed") == "true"


@pytest.mark.asyncio
class TestMiddlewareMissingKey:
    async def test_missing_key_returns_400(self, middleware_client: AsyncClient):
        response = await middleware_client.post("/test")
        assert response.status_code == 400
        assert "required" in response.json()["detail"].lower()


@pytest.mark.asyncio
class TestMiddlewareMethodFiltering:
    async def test_get_skips_idempotency(self, middleware_client: AsyncClient):
        response = await middleware_client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        # No idempotency header should be required for GET
        assert "Idempotency-Key" not in response.headers


@pytest.mark.asyncio
class TestMiddlewareFingerprintMismatch:
    async def test_different_body_same_key_returns_422(self, middleware_client: AsyncClient):
        key = "mw-mismatch"
        headers = {"Idempotency-Key": key}

        await middleware_client.post(
            "/test", headers=headers, content=b'{"a": 1}'
        )
        r2 = await middleware_client.post(
            "/test", headers=headers, content=b'{"a": 2}'
        )
        assert r2.status_code == 422


@pytest.mark.asyncio
class TestMiddlewareKeyTooLong:
    async def test_key_too_long_returns_400(self, middleware_client: AsyncClient):
        long_key = "x" * 300
        response = await middleware_client.post(
            "/test",
            headers={"Idempotency-Key": long_key},
        )
        assert response.status_code == 400
        assert "length" in response.json()["detail"].lower()
