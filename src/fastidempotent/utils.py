# Utility functions (hashing, key generation, serialization)
from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.requests import Request


def compute_fingerprint(
    method: str,
    path: str,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    include_body: bool = True,
) -> str:
    """
    Compute a SHA-256 fingerprint from the req's method, path,
    optionally its body, and selected headers;

    The fingerprint is used to detect payload mismatches when the
    same idempotency key is reused with a different req;
    """
    parts: list[str] = [method.upper(), path]

    if include_body and body:
        parts.append(hashlib.sha256(body).hexdigest())
    elif include_body:
        parts.append(hashlib.sha256(b"").hexdigest())

    if headers:
        # Sort for deterministic ordering
        sorted_headers = sorted(headers.items())
        parts.append(
            hashlib.sha256(json.dumps(sorted_headers).encode()).hexdigest()
        )

    combined = "|".join(parts)
    return hashlib.sha256(combined.encode()).hexdigest()


async def extract_fingerprint_from_request(
    request: Request,
    include_body: bool = True,
    fingerprint_headers: list[str] | None = None,
) -> str:
    """
    Build a fingerprint from a Starlette/FastAPI ``req`` object;
    """
    body: bytes | None = None
    if include_body:
        body = await request.body()

    selected_headers: dict[str, str] | None = None
    if fingerprint_headers:
        selected_headers = {
            h: request.headers.get(h, "")
            for h in fingerprint_headers
        }

    return compute_fingerprint(
        method=request.method,
        path=request.url.path,
        body=body,
        headers=selected_headers,
        include_body=include_body,
    )


def serialize_response_body(body: bytes | str | dict | list | None) -> bytes | None:
    """
    Normalise a resp body to bytes for storage;
    """
    if body is None:
        return None
    if isinstance(body, bytes):
        return body
    if isinstance(body, str):
        return body.encode("utf-8")
    # dict / list → JSON bytes
    return json.dumps(body, default=str).encode("utf-8")


def deserialize_response_body(body: bytes | None) -> bytes | None:
    """
    Return stored bytes as-is; Exists as a symmetry point for
    future compression / encryption support;
    """
    return body


def serialize_headers(headers: dict[str, str]) -> str:
    """Serialize resp headers to a JSON string for storage;"""
    return json.dumps(headers)


def deserialize_headers(raw: str | None) -> dict[str, str]:
    """Deserialize resp headers from a JSON string;"""
    if not raw:
        return {}
    return json.loads(raw)  # type: ignore[no-any-return]
