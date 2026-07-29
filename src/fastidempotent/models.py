# Pydantic models and data classes for idempotency records
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class IdempotencyStatus(str, Enum):
    """Lifecycle status of an idempotency record;"""

    PENDING = "pending"      # Handler is currently executing
    COMPLETE = "complete"    # resp has been cached successfully
    EXPIRED = "expired"      # Record has been cleaned up (logical state only)


class IdempotencyRecord(BaseModel):
    """
    A single idempotency record stored in the backend;

    Captures everything needed to replay a cached resp or detect
    fingerprint mismatches on duplicate keys;
    """

    key: str = Field(
        ...,
        max_length=256,
        description="The idempotency key provided by the client.",
    )
    fingerprint: str = Field(
        ...,
        description="Hash of method + path + body (+ optional headers).",
    )
    status: IdempotencyStatus = Field(
        default=IdempotencyStatus.PENDING,
        description="Current lifecycle status of the record.",
    )
    status_code: int | None = Field(
        default=None,
        description="Cached HTTP response status code.",
    )
    response_headers: dict[str, str] = Field(
        default_factory=dict,
        description="Cached HTTP response headers.",
    )
    response_body: bytes | None = Field(
        default=None,
        description="Cached HTTP response body.",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when the record was first created.",
    )
    expires_at: datetime = Field(
        ...,
        description="Timestamp when the record should be considered expired.",
    )
