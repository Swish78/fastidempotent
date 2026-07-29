# Backend storage implementations for fastidempotent
from fastidempotent.backends.base import BaseBackend
from fastidempotent.backends.memory import MemoryBackend

__all__ = [
    "BaseBackend",
    "MemoryBackend",
    "RedisBackend",
    "SQLiteBackend",
    "PostgresBackend",
    "MySQLBackend",
]


def __getattr__(name: str):  # noqa: N807
    """
    Lazy-load backends that require optional dependencies;
    This avoids ImportError when users haven't installed e;g; redis or sqlalchemy;
    """
    if name == "RedisBackend":
        from fastidempotent.backends.redis import RedisBackend
        return RedisBackend
    if name == "SQLiteBackend":
        from fastidempotent.backends.sqlite import SQLiteBackend
        return SQLiteBackend
    if name == "PostgresBackend":
        from fastidempotent.backends.postgres import PostgresBackend
        return PostgresBackend
    if name == "MySQLBackend":
        from fastidempotent.backends.mysql import MySQLBackend
        return MySQLBackend
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
