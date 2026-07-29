# ⚡ fastidempotent

**Idempotency middleware & decorator for FastAPI — prevent duplicate side-effects with pluggable storage backends.**

[![PyPI version](https://img.shields.io/pypi/v/fastidempotent.svg)](https://pypi.org/project/fastidempotent/)
[![Python](https://img.shields.io/pypi/pyversions/fastidempotent.svg)](https://pypi.org/project/fastidempotent/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Tests](https://img.shields.io/github/actions/workflow/status/Swish78/fastidempotent/ci.yml?label=tests)](https://github.com/Swish78/fastidempotent/actions)

---

## Why?

HTTP is inherently unreliable. Clients retry, networks hiccup, and load-balancers replay requests. Without idempotency, a single `POST /payments` can charge a customer twice.

**fastidempotent** solves this at the framework level:

- Client sends an `Idempotency-Key` header with a unique token.
- On the first request, the response is executed and cached.
- On any replay, the cached response is returned **without re-executing** the handler.
- Concurrent duplicates are rejected with `409 Conflict` while the first is still processing.

---

## Features

- 🎯 **Decorator & Middleware** — choose per-route `@idempotent` or app-wide middleware
- 🔌 **Pluggable Backends** — in-memory, Redis, PostgreSQL, MySQL, SQLite
- ⏱️ **Configurable TTL** — auto-expire idempotency records after a duration
- 🔒 **Concurrency-safe** — distributed locking prevents race conditions
- 📦 **Async-native** — built on `async/await` throughout, zero blocking I/O
- 🏷️ **Fully Typed** — PEP 561 compliant with `py.typed` marker
- 🧩 **Optional Dependencies** — install only the backend drivers you need

---

## Installation

```bash
# Core (in-memory backend only)
uv add fastidempotent

# With a specific backend
uv add fastidempotent[redis]
uv add fastidempotent[postgres]
uv add fastidempotent[mysql]
uv add fastidempotent[sqlite]

# All backends
uv add fastidempotent[all]
```

---

## Quick Start

### Decorator Approach (per-route)

```python
from fastapi import FastAPI, Request
from fastidempotent import idempotent, MemoryBackend

app = FastAPI()
backend = MemoryBackend(ttl=3600)

@app.post("/payments")
@idempotent(backend=backend)
async def create_payment(request: Request, amount: float):
    # this will only execute ONCE per idempotency key
    return {"status": "charged", "amount": amount}
```

### Middleware Approach (app-wide)

```python
from fastapi import FastAPI
from fastidempotent import IdempotencyMiddleware, RedisBackend

app = FastAPI()

app.add_middleware(
    IdempotencyMiddleware,
    backend=RedisBackend(url="redis://localhost:6379"),
    ttl=3600,
    methods=["POST", "PUT", "PATCH"],
)

@app.post("/orders")
async def create_order(item: str, qty: int):
    return {"item": item, "qty": qty, "status": "created"}
```

### Making Idempotent Requests

```bash
# first req — executes the handler, caches the resp
curl -X POST http://localhost:8000/payments \
  -H "Idempotency-Key: unique-key-123" \
  -H "Content-Type: application/json" \
  -d '{"amount": 99.99}'

# replay — returns cached resp, handler is NOT called again
curl -X POST http://localhost:8000/payments \
  -H "Idempotency-Key: unique-key-123" \
  -H "Content-Type: application/json" \
  -d '{"amount": 99.99}'
```

---

## Backend Configuration

### In-Memory (default)

Best for dev and testing. Data is lost on restart.

```python
from fastidempotent import MemoryBackend

backend = MemoryBackend(ttl=3600)  # records expire after 1hr
```

### Redis

Recommended for prod. Supports distributed deployments.

```python
from fastidempotent import RedisBackend

backend = RedisBackend(
    url="redis://localhost:6379/0",
    key_prefix="idempotent:",
    ttl=3600,
)
```

### PostgreSQL

Uses SQLAlchemy async with `asyncpg`.

```python
from fastidempotent import PostgresBackend

backend = PostgresBackend(
    url="postgresql+asyncpg://user:pass@localhost/mydb",
    table_name="idempotency_keys",
    ttl=3600,
)
```

### MySQL

Uses SQLAlchemy async with `asyncmy`.

```python
from fastidempotent import MySQLBackend

backend = MySQLBackend(
    url="mysql+asyncmy://user:pass@localhost/mydb",
    table_name="idempotency_keys",
    ttl=3600,
)
```

### SQLite

Uses SQLAlchemy async with `aiosqlite`. Great for single-process deployments.

```python
from fastidempotent import SQLiteBackend

backend = SQLiteBackend(
    url="sqlite+aiosqlite:///./idempotency.db",
    ttl=3600,
)
```

---

## Configuration

Use env vars or pass settings directly:

```python
from fastidempotent import IdempotencyConfig

config = IdempotencyConfig(
    ttl=3600,                          # record TTL in secs
    header_name="Idempotency-Key",     # custom header name
    enforce_on=["POST", "PUT", "PATCH"],  # which methods require a key
    optional=False,                    # if True, missing key skips idempotency
    fingerprint_body=True,             # include req body in fingerprint
)
```


---

## API Reference

### Decorator

| Parameter | Type | Default | Description |
|---|---|---|---|
| `backend` | `BaseBackend` | required | Storage backend instance |
| `config` | `IdempotencyConfig` | `None` | Optional config override |

### Middleware

| Parameter | Type | Default | Description |
|---|---|---|---|
| `backend` | `BaseBackend` | required | Storage backend instance |
| `ttl` | `int` | `3600` | TTL for cached responses (secs) |
| `methods` | `list[str]` | `["POST"]` | HTTP methods to enforce |
| `header` | `str` | `"Idempotency-Key"` | Header to read the key from |
| `optional` | `bool` | `False` | Skip idempotency if header missing |

### Response Headers

| Header | Description |
|---|---|
| `Idempotency-Key` | Echo of the key used |
| `X-Idempotent-Replayed` | `"true"` if this is a cached replay |

---

## How It Works

```
Client                    fastidempotent                  Your Handler
  │                            │                               │
  │── POST with Key ──────────▶│                               │
  │                            │── Check backend for key ─────▶│
  │                            │                               │
  │                     [Key not found]                        │
  │                            │── Lock key (status=PENDING) ──│
  │                            │── Forward to handler ────────▶│
  │                            │◀── Response ─────────────────│
  │                            │── Cache response ────────────▶│
  │◀── Response ──────────────│                               │
  │                            │                               │
  │── POST with SAME Key ────▶│                               │
  │                            │── Check backend for key ─────▶│
  │                     [Key found, status=COMPLETE]           │
  │◀── Cached Response ──────│       (handler NOT called)     │
```

---

## Development

```bash
# clone and install
git clone https://github.com/Swish78/fastidempotent.git
cd fastidempotent
uv sync

# run tests
uv run pytest

# type checking
uv run mypy src/

# linting
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```


---

## Contributing

Contributions are welcome! Please:

1. Fork the repo and create a feature branch
2. Add tests for any new functionality
3. Ensure `pytest`, `mypy`, and `ruff` all pass
4. Open a pull request with a clear description

---

## License

Apache-2.0 — see [LICENSE](LICENSE) for details.