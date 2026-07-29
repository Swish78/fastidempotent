# Shared fixtures for tests
from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from fastidempotent import IdempotencyMiddleware, MemoryBackend, idempotent


@pytest_asyncio.fixture
async def memory_backend():
    """Provide a fresh MemoryBackend for each test;"""
    backend = MemoryBackend(ttl=60)
    yield backend
    await backend.close()


@pytest.fixture
def app_with_decorator(memory_backend: MemoryBackend) -> FastAPI:
    """FastAPI app using the @idempotent decorator;"""
    app = FastAPI()

    @app.post("/test")
    @idempotent(backend=memory_backend)
    async def test_endpoint(request: Request):
        return {"message": "created", "count": 1}

    @app.post("/fail")
    @idempotent(backend=memory_backend)
    async def failing_endpoint(request: Request):
        raise ValueError("Something broke")

    return app


@pytest.fixture
def app_with_middleware(memory_backend: MemoryBackend) -> FastAPI:
    """FastAPI app using IdempotencyMiddleware;"""
    app = FastAPI()
    app.add_middleware(
        IdempotencyMiddleware,
        backend=memory_backend,
        ttl=60,
    )

    @app.post("/test")
    async def test_endpoint():
        return {"message": "created", "count": 1}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


@pytest_asyncio.fixture
async def decorator_client(app_with_decorator: FastAPI):
    """httpx AsyncClient for the decorator-based app;"""
    transport = ASGITransport(app=app_with_decorator, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def middleware_client(app_with_middleware: FastAPI):
    """httpx AsyncClient for the mw-based app;"""
    transport = ASGITransport(app=app_with_middleware, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
