# ex: Using fastidempotent with Redis backend
"""
Redis ex — run with:
    uvicorn examples.redis_example:app --reload

Requires:
    uv add fastidempotent[redis]
    # and a running Redis server on localhost:6379
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from fastidempotent import IdempotencyConfig, idempotent
from fastidempotent.backends.redis import RedisBackend

# Create Redis backend (connects on init)
backend = RedisBackend(
    url="redis://localhost:6379/0",
    key_prefix="myapp:idempotent:",
    ttl=3600,
)

config = IdempotencyConfig(ttl=3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise and clean up the Redis backend;"""
    await backend.init()
    yield
    await backend.close()


app = FastAPI(title="fastidempotent — Redis Example", lifespan=lifespan)


@app.post("/payments")
@idempotent(backend=backend, config=config)
async def create_payment(request: Request, amount: float):
    return {
        "status": "charged",
        "amount": amount,
    }


@app.post("/notifications")
@idempotent(backend=backend, config=config)
async def send_notification(request: Request, user_id: str, message: str):
    # Simulate sending a notification
    return {
        "user_id": user_id,
        "message": message,
        "status": "sent",
    }
