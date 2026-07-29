# cfg and settings for fastidempotent
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class IdempotencyConfig(BaseSettings):
    """
    cfg for the fastidempotent idempotency layer;

    All settings can be overridden via env variables prefixed with
    ``IDEMPOTENCY_`` (e;g; ``IDEMPOTENCY_TTL=7200``);
    """

    model_config = SettingsConfigDict(
        env_prefix="IDEMPOTENCY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    #  Key extraction 
    header_name: str = Field(
        default="Idempotency-Key",
        description="HTTP header from which the idempotency key is read.",
    )
    key_max_length: int = Field(
        default=256,
        ge=1,
        description="Maximum allowed length of an idempotency key.",
    )
    optional: bool = Field(
        default=False,
        description=(
            "When False, requests without an idempotency key return 400. "
            "When True, missing keys skip idempotency and execute normally."
        ),
    )

    #  Lifetime 
    ttl: int = Field(
        default=3600,
        ge=1,
        description="Time-to-live (seconds) for cached idempotency records.",
    )
    lock_timeout: int = Field(
        default=30,
        ge=1,
        description=(
            "Maximum seconds a PENDING lock is held before it is considered "
            "stale and can be reclaimed."
        ),
    )

    #  Fingerprinting 
    fingerprint_body: bool = Field(
        default=True,
        description=(
            "Include a hash of the request body in the fingerprint. "
            "When True, replaying the same key with a different body returns 422."
        ),
    )
    fingerprint_headers: list[str] = Field(
        default_factory=list,
        description=(
            "Additional request headers to include in the fingerprint "
            "(e.g. ['Authorization'] to scope keys per-user)."
        ),
    )

    #  Scope 
    enforce_on: list[str] = Field(
        default=["POST", "PUT", "PATCH"],
        description="HTTP methods that require an idempotency key.",
    )

    #  resp 
    replay_header: str = Field(
        default="X-Idempotent-Replayed",
        description="Response header set to 'true' on replayed (cached) responses.",
    )

    #  Backend 
    backend_type: Literal["memory", "redis", "postgres", "mysql", "sqlite"] = Field(
        default="memory",
        description="Which storage backend to use (when auto-configuring via env vars).",
    )

    #  Backend conn strings 
    redis_url: str | None = Field(
        default=None,
        description="Redis connection URL (e.g. redis://localhost:6379/0).",
    )
    redis_key_prefix: str = Field(
        default="idempotent:",
        description="Prefix prepended to every key stored in Redis.",
    )
    database_url: str | None = Field(
        default=None,
        description=(
            "SQLAlchemy async connection URL for SQL backends "
            "(e.g. postgresql+asyncpg://user:pass@localhost/mydb)."
        ),
    )
    database_table: str = Field(
        default="idempotency_keys",
        description="Table name used by SQL backends.",
    )


class BackendConfig(BaseModel):
    """
    Subset of config passed to backend constructors;

    This is a plain Pydantic model (not settings) — it is built
    programmatically from ``IdempotencyConfig`` or passed directly;
    """

    ttl: int = 3600
    lock_timeout: int = 30

    # Redis-specific
    redis_url: str | None = None
    redis_key_prefix: str = "idempotent:"

    # SQL-specific
    database_url: str | None = None
    database_table: str = "idempotency_keys"

    @classmethod
    def from_config(cls, config: IdempotencyConfig) -> BackendConfig:
        """Extract backend-relevant fields from the full config;"""
        return cls(
            ttl=config.ttl,
            lock_timeout=config.lock_timeout,
            redis_url=config.redis_url,
            redis_key_prefix=config.redis_key_prefix,
            database_url=config.database_url,
            database_table=config.database_table,
        )