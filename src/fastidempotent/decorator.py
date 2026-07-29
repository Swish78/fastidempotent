# @idempotent decorator for FastAPI route handlers
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Callable, TypeVar

from starlette.requests import Request
from starlette.responses import Response

from fastidempotent.backends.base import BaseBackend
from fastidempotent.config import IdempotencyConfig
from fastidempotent.exceptions import (
    DuplicateRequestError,
    FingerprintMismatchError,
    KeyTooLongError,
    MissingKeyError,
)
from fastidempotent.models import IdempotencyRecord, IdempotencyStatus
from fastidempotent.utils import extract_fingerprint_from_request

logger = logging.getLogger("fastidempotent")

F = TypeVar("F", bound=Callable[..., Any])


def idempotent(
    backend: BaseBackend,
    config: IdempotencyConfig | None = None,
) -> Callable[[F], F]:
    """
    Decorator that adds idempotency to a FastAPI route handler;

    Usage::

        backend = MemoryBackend()

        @app.post("/payments")
        @idempotent(backend=backend)
        async def create_payment(request: Request, amount: float):
            return {"charged": amount}

    The decorated endpoint **must** accept a ``request: Request`` param
    (either explicitly or via FastAPI's automatic injection);
    """
    cfg = config or IdempotencyConfig()

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            #  Extract the req object 
            request: Request | None = kwargs.get("request")
            if request is None:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            # If no req object found, just call through (e;g; testing)
            if request is None:
                return await func(*args, **kwargs)

            #  Should we enforce idempotency on this method? 
            if request.method.upper() not in cfg.enforce_on:
                return await func(*args, **kwargs)

            #  Extract idempotency key 
            idem_key = request.headers.get(cfg.header_name)

            if not idem_key:
                if cfg.optional:
                    return await func(*args, **kwargs)
                raise MissingKeyError(cfg.header_name)

            if len(idem_key) > cfg.key_max_length:
                raise KeyTooLongError(idem_key, cfg.key_max_length)

            # Scope the key to method + path
            scoped_key = f"{request.method}:{request.url.path}:{idem_key}"

            #  Compute fingerprint 
            fingerprint = await extract_fingerprint_from_request(
                request,
                include_body=cfg.fingerprint_body,
                fingerprint_headers=cfg.fingerprint_headers or None,
            )

            #  Check for existing record 
            existing = await backend.get(scoped_key)

            if existing is not None:
                if existing.status == IdempotencyStatus.PENDING:
                    raise DuplicateRequestError(idem_key)

                if existing.fingerprint != fingerprint:
                    raise FingerprintMismatchError(idem_key)

                # Return cached resp
                logger.debug("Replaying cached response for key=%s", idem_key)
                return Response(
                    content=existing.response_body,
                    status_code=existing.status_code or 200,
                    headers={
                        **existing.response_headers,
                        cfg.header_name: idem_key,
                        cfg.replay_header: "true",
                    },
                )

            #  Acquire lock 
            acquired = await backend.acquire_lock(scoped_key, cfg.lock_timeout)
            if not acquired:
                raise DuplicateRequestError(idem_key)

            #  exec handler 
            try:
                result = await func(*args, **kwargs)
            except Exception:
                # Release the lock so the key can be retried
                await backend.release_lock(scoped_key)
                raise

            #  Cache the resp 
            now = datetime.now(tz=timezone.utc)

            if isinstance(result, Response):
                record = IdempotencyRecord(
                    key=scoped_key,
                    fingerprint=fingerprint,
                    status=IdempotencyStatus.COMPLETE,
                    status_code=result.status_code,
                    response_headers=dict(result.headers),
                    response_body=result.body,
                    created_at=now,
                    expires_at=now + timedelta(seconds=cfg.ttl),
                )
                await backend.set(record)

                # Inject idempotency headers
                result.headers[cfg.header_name] = idem_key
                return result
            else:
                # Handler returned a dict/model — FastAPI will serialize it;
                # We need to serialize it ourselves for caching;
                import json

                if hasattr(result, "model_dump"):
                    body = json.dumps(result.model_dump(), default=str).encode()
                elif isinstance(result, dict | list):
                    body = json.dumps(result, default=str).encode()
                else:
                    body = str(result).encode()

                record = IdempotencyRecord(
                    key=scoped_key,
                    fingerprint=fingerprint,
                    status=IdempotencyStatus.COMPLETE,
                    status_code=200,
                    response_headers={"content-type": "application/json"},
                    response_body=body,
                    created_at=now,
                    expires_at=now + timedelta(seconds=cfg.ttl),
                )
                await backend.set(record)
                return result

        return wrapper  # type: ignore[return-value]

    return decorator