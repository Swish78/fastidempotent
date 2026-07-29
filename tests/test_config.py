# Tests for cfg and settings
from __future__ import annotations

import os
from unittest import mock

import pytest

from fastidempotent.config import BackendConfig, IdempotencyConfig


class TestIdempotencyConfigDefaults:
    def test_default_values(self):
        config = IdempotencyConfig()
        assert config.header_name == "Idempotency-Key"
        assert config.key_max_length == 256
        assert config.optional is False
        assert config.ttl == 3600
        assert config.lock_timeout == 30
        assert config.fingerprint_body is True
        assert config.fingerprint_headers == []
        assert config.enforce_on == ["POST", "PUT", "PATCH"]
        assert config.replay_header == "X-Idempotent-Replayed"
        assert config.backend_type == "memory"
        assert config.redis_url is None
        assert config.database_url is None

    def test_custom_values(self):
        config = IdempotencyConfig(
            ttl=7200,
            header_name="X-Request-Id",
            optional=True,
            backend_type="redis",
            redis_url="redis://myhost:6379",
        )
        assert config.ttl == 7200
        assert config.header_name == "X-Request-Id"
        assert config.optional is True
        assert config.backend_type == "redis"
        assert config.redis_url == "redis://myhost:6379"


class TestIdempotencyConfigEnvVars:
    def test_reads_from_env(self):
        env = {
            "IDEMPOTENCY_TTL": "1800",
            "IDEMPOTENCY_HEADER_NAME": "X-Idem",
            "IDEMPOTENCY_OPTIONAL": "true",
            "IDEMPOTENCY_BACKEND_TYPE": "redis",
            "IDEMPOTENCY_REDIS_URL": "redis://env-host",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            config = IdempotencyConfig()
            assert config.ttl == 1800
            assert config.header_name == "X-Idem"
            assert config.optional is True
            assert config.backend_type == "redis"
            assert config.redis_url == "redis://env-host"

    def test_enforce_on_from_csv_string(self):
        env = {"IDEMPOTENCY_ENFORCE_ON": '["POST", "DELETE"]'}
        with mock.patch.dict(os.environ, env, clear=False):
            config = IdempotencyConfig()
            assert config.enforce_on == ["POST", "DELETE"]

    def test_fingerprint_headers_from_csv(self):
        env = {"IDEMPOTENCY_FINGERPRINT_HEADERS": '["Authorization", "X-Tenant"]'}
        with mock.patch.dict(os.environ, env, clear=False):
            config = IdempotencyConfig()
            assert config.fingerprint_headers == ["Authorization", "X-Tenant"]


class TestIdempotencyConfigValidation:
    def test_ttl_must_be_positive(self):
        with pytest.raises(Exception):
            IdempotencyConfig(ttl=0)

    def test_key_max_length_must_be_positive(self):
        with pytest.raises(Exception):
            IdempotencyConfig(key_max_length=0)


class TestBackendConfig:
    def test_from_config(self):
        config = IdempotencyConfig(
            ttl=1800,
            lock_timeout=15,
            redis_url="redis://custom",
            redis_key_prefix="myapp:",
            database_url="sqlite+aiosqlite:///test.db",
            database_table="my_keys",
        )
        bc = BackendConfig.from_config(config)
        assert bc.ttl == 1800
        assert bc.lock_timeout == 15
        assert bc.redis_url == "redis://custom"
        assert bc.redis_key_prefix == "myapp:"
        assert bc.database_url == "sqlite+aiosqlite:///test.db"
        assert bc.database_table == "my_keys"

    def test_defaults(self):
        bc = BackendConfig()
        assert bc.ttl == 3600
        assert bc.lock_timeout == 30
        assert bc.redis_url is None
