# fastidempotent - Idempotency support for FastAPI
"""
fastidempotent
~~~~~~~~~~~~~~

Idempotency mw & decorator for FastAPI with pluggable backends;

Basic usage::

    from fastapi import FastAPI
    from fastidempotent import idempotent, MemoryBackend

    app = FastAPI()
    backend = MemoryBackend(ttl=3600)

    @app.post("/payments")
    @idempotent(backend=backend)
    async def create_payment(request: Request, amount: float):
        return {"charged": amount}
"""
from fastidempotent.backends import (
    BaseBackend,
    MemoryBackend,
)
from fastidempotent.config import BackendConfig, IdempotencyConfig
from fastidempotent.decorator import idempotent
from fastidempotent.depends import configure, get_backend, get_config
from fastidempotent.exceptions import (
    BackendError,
    DuplicateRequestError,
    FingerprintMismatchError,
    IdempotencyError,
    KeyTooLongError,
    MissingKeyError,
)
from fastidempotent.middleware import IdempotencyMiddleware
from fastidempotent.models import IdempotencyRecord, IdempotencyStatus

__version__ = "0.1.0"

__all__ = [
    # Decorator & mw
    "idempotent",
    "IdempotencyMiddleware",
    # Backends
    "BaseBackend",
    "MemoryBackend",
    # Config
    "IdempotencyConfig",
    "BackendConfig",
    # Models
    "IdempotencyRecord",
    "IdempotencyStatus",
    # Exceptions
    "IdempotencyError",
    "DuplicateRequestError",
    "FingerprintMismatchError",
    "MissingKeyError",
    "KeyTooLongError",
    "BackendError",
    # DI helpers
    "configure",
    "get_backend",
    "get_config",
    # Version
    "__version__",
]


def __getattr__(name: str):  # noqa: N807
    """Lazy-load optional backends to avoid import errors;"""
    lazy_backends = {
        "RedisBackend": "fastidempotent.backends.redis",
        "SQLiteBackend": "fastidempotent.backends.sqlite",
        "PostgresBackend": "fastidempotent.backends.postgres",
        "MySQLBackend": "fastidempotent.backends.mysql",
    }
    if name in lazy_backends:
        import importlib
        module = importlib.import_module(lazy_backends[name])
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
