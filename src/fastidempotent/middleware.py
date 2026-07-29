# Starlette / FastAPI mw for idempotency
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Sequence

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from fastidempotent.backends.base import BaseBackend
from fastidempotent.config import IdempotencyConfig
from fastidempotent.models import IdempotencyRecord, IdempotencyStatus
from fastidempotent.utils import extract_fingerprint_from_request

logger = logging.getLogger("fastidempotent")


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Starlette mw that enforces idempotency on configured
    HTTP methods across the entire app;

    Usage::

        from fastidempotent import IdempotencyMiddleware, MemoryBackend

        app.add_middleware(
            IdempotencyMiddleware,
            backend=MemoryBackend(),
            ttl=3600,
            methods=["POST", "PUT", "PATCH"],
        )
    """

    def __init__(
        self,
        app: Callable,
        backend: BaseBackend,
        config: IdempotencyConfig | None = None,
        ttl: int | None = None,
        methods: Sequence[str] | None = None,
        header: str | None = None,
        optional: bool | None = None,
    ) -> None:
        super().__init__(app)
        self.backend = backend
        self.config = config or IdempotencyConfig()

        # Allow per-params overrides
        if ttl is not None:
            self.config = self.config.model_copy(update={"ttl": ttl})
        if methods is not None:
            self.config = self.config.model_copy(
                update={"enforce_on": [m.upper() for m in methods]}
            )
        if header is not None:
            self.config = self.config.model_copy(update={"header_name": header})
        if optional is not None:
            self.config = self.config.model_copy(update={"optional": optional})

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        cfg = self.config

        #  Skip methods not in enforce list 
        if request.method.upper() not in cfg.enforce_on:
            return await call_next(request)

        #  Extract idempotency key 
        idem_key = request.headers.get(cfg.header_name)

        if not idem_key:
            if cfg.optional:
                return await call_next(request)
            return Response(
                content=f'{{"detail":"{cfg.header_name} header is required"}}',
                status_code=400,
                media_type="application/json",
            )

        if len(idem_key) > cfg.key_max_length:
            return Response(
                content=f'{{"detail":"Idempotency key exceeds maximum length of {cfg.key_max_length} characters"}}',
                status_code=400,
                media_type="application/json",
            )

        scoped_key = f"{request.method}:{request.url.path}:{idem_key}"

        #  Compute fingerprint 
        fingerprint = await extract_fingerprint_from_request(
            request,
            include_body=cfg.fingerprint_body,
            fingerprint_headers=cfg.fingerprint_headers or None,
        )

        #  Check for existing record 
        existing = await self.backend.get(scoped_key)

        if existing is not None:
            if existing.status == IdempotencyStatus.PENDING:
                return Response(
                    content='{"detail":"A request with this idempotency key is already being processed"}',
                    status_code=409,
                    media_type="application/json",
                )

            if existing.fingerprint != fingerprint:
                return Response(
                    content='{"detail":"Request payload does not match the original request for this idempotency key"}',
                    status_code=422,
                    media_type="application/json",
                )

            # Replay cached resp
            logger.debug("Replaying cached response for key=%s", idem_key)
            headers = dict(existing.response_headers)
            headers[cfg.header_name] = idem_key
            headers[cfg.replay_header] = "true"
            return Response(
                content=existing.response_body,
                status_code=existing.status_code or 200,
                headers=headers,
            )

        #  Acquire lock 
        acquired = await self.backend.acquire_lock(scoped_key, cfg.lock_timeout)
        if not acquired:
            return Response(
                content='{"detail":"A request with this idempotency key is already being processed"}',
                status_code=409,
                media_type="application/json",
            )

        #  exec the actual handler 
        try:
            response = await call_next(request)
        except Exception:
            await self.backend.release_lock(scoped_key)
            raise

        #  Read and cache the resp 
        # We need to consume the resp body to cache it, then
        # return a new resp with the same body;
        body = b""
        async for chunk in response.body_iterator:  # type: ignore[union-attr]
            if isinstance(chunk, str):
                body += chunk.encode("utf-8")
            else:
                body += chunk

        now = datetime.now(tz=timezone.utc)
        record = IdempotencyRecord(
            key=scoped_key,
            fingerprint=fingerprint,
            status=IdempotencyStatus.COMPLETE,
            status_code=response.status_code,
            response_headers={
                k: v for k, v in response.headers.items()
                if k.lower() not in ("content-length", "transfer-encoding")
            },
            response_body=body,
            created_at=now,
            expires_at=now + timedelta(seconds=cfg.ttl),
        )
        await self.backend.set(record)

        # Return a fresh resp with the cached body
        headers = dict(response.headers)
        headers[cfg.header_name] = idem_key
        return Response(
            content=body,
            status_code=response.status_code,
            headers=headers,
        )
