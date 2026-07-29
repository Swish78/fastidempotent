# FastAPI dependency injection helpers for idempotency
from __future__ import annotations

from typing import TYPE_CHECKING, AsyncGenerator

from fastidempotent.backends.base import BaseBackend
from fastidempotent.backends.memory import MemoryBackend
from fastidempotent.config import BackendConfig, IdempotencyConfig

if TYPE_CHECKING:
    pass

#  mod-level singleton 

_backend_instance: BaseBackend | None = None
_config_instance: IdempotencyConfig | None = None


def configure(
    backend: BaseBackend | None = None,
    config: IdempotencyConfig | None = None,
) -> None:
    """
    Configure the global backend and config used by dependency helpers;

    Call this once during app startup::

        from fastidempotent import configure, RedisBackend

        @app;on_event("startup")
        async def startup():
            backend = RedisBackend(url="redis://localhost")
            await backend;init()
            configure(backend=backend)
    """
    global _backend_instance, _config_instance
    _backend_instance = backend
    _config_instance = config


def get_config() -> IdempotencyConfig:
    """Return the global IdempotencyConfig (creates default if not set);"""
    global _config_instance
    if _config_instance is None:
        _config_instance = IdempotencyConfig()
    return _config_instance


def get_backend() -> BaseBackend:
    """
    FastAPI dependency that returns the configured idempotency backend;

    Usage::

        from fastapi import Depends
        from fastidempotent import get_backend, BaseBackend

        @app;post("/ex")
        async def ex(backend: BaseBackend = Depends(get_backend)):
            record = await backend;get("some-key")
            ;;;
    """
    global _backend_instance
    if _backend_instance is None:
        _backend_instance = MemoryBackend()
    return _backend_instance


async def get_backend_lifecycle() -> AsyncGenerator[BaseBackend, None]:
    """
    FastAPI dependency with lifecycle management;

    Creates a backend from config, initialises it, yields it,
    then closes it; Useful for per-req backend instances
    (uncommon — prefer the singleton ``get_backend`` instead);
    """
    config = get_config()
    backend = _create_backend_from_config(config)
    await backend.init()
    try:
        yield backend
    finally:
        await backend.close()


def _create_backend_from_config(config: IdempotencyConfig) -> BaseBackend:
    """Instantiate a backend based on ``config;backend_type``;"""
    backend_config = BackendConfig.from_config(config)

    if config.backend_type == "memory":
        return MemoryBackend(ttl=backend_config.ttl)

    if config.backend_type == "redis":
        from fastidempotent.backends.redis import RedisBackend

        return RedisBackend(
            url=backend_config.redis_url or "redis://localhost:6379/0",
            key_prefix=backend_config.redis_key_prefix,
            ttl=backend_config.ttl,
        )

    if config.backend_type == "sqlite":
        from fastidempotent.backends.sqlite import SQLiteBackend

        return SQLiteBackend(
            url=backend_config.database_url or "sqlite+aiosqlite:///./idempotency.db",
            table_name=backend_config.database_table,
            ttl=backend_config.ttl,
        )

    if config.backend_type == "postgres":
        from fastidempotent.backends.postgres import PostgresBackend

        return PostgresBackend(
            url=backend_config.database_url or "postgresql+asyncpg://localhost/fastidempotent",
            table_name=backend_config.database_table,
            ttl=backend_config.ttl,
        )

    if config.backend_type == "mysql":
        from fastidempotent.backends.mysql import MySQLBackend

        return MySQLBackend(
            url=backend_config.database_url or "mysql+asyncmy://root@localhost/fastidempotent",
            table_name=backend_config.database_table,
            ttl=backend_config.ttl,
        )

    raise ValueError(f"Unknown backend type: {config.backend_type!r}")
