# ex: Using fastidempotent with SQLAlchemy-based backends (SQLite, Postgres, MySQL)
"""
SQL backend ex — run with:
    uvicorn examples.sql_example:app --reload

This ex uses SQLite (zero config); Swap the backend class
and URL for Postgres or MySQL;

Requires:
    uv add fastidempotent[sqlite]   # or [postgres] or [mysql]
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from fastidempotent import IdempotencyMiddleware
from fastidempotent.backends.sqlite import SQLiteBackend

#  Choose your backend 
# SQLite (default — zero config):
backend = SQLiteBackend(
    url="sqlite+aiosqlite:///./idempotency.db",
    table_name="idempotency_keys",
    ttl=3600,
)

# PostgreSQL (uncomment and adjust):
# from fastidempotent.backends.postgres import PostgresBackend
# backend = PostgresBackend(
#     url="postgresql+asyncpg://user:pass@localhost/mydb",
#     ttl=3600,
# )

# MySQL (uncomment and adjust):
# from fastidempotent.backends.mysql import MySQLBackend
# backend = MySQLBackend(
#     url="mysql+asyncmy://user:pass@localhost/mydb",
#     ttl=3600,
# )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables on startup, dispose engine on shutdown;"""
    await backend.init()
    yield
    await backend.close()


app = FastAPI(title="fastidempotent — SQL Example", lifespan=lifespan)

# Use mw approach (app-wide) instead of per-route decorator
app.add_middleware(
    IdempotencyMiddleware,
    backend=backend,
    ttl=3600,
    methods=["POST", "PUT", "PATCH"],
)


@app.post("/orders")
async def create_order(item: str, qty: int = 1):
    return {
        "item": item,
        "qty": qty,
        "status": "created",
    }


@app.put("/orders/{order_id}")
async def update_order(order_id: str, item: str, qty: int):
    return {
        "order_id": order_id,
        "item": item,
        "qty": qty,
        "status": "updated",
    }


@app.get("/health")
async def health():
    """GET is not in enforce_on, so no idempotency key needed;"""
    return {"status": "ok"}
