# ex: Using fastidempotent with the in-memory backend
"""
Quick-start ex — run with:
    uvicorn examples.memory_example:app --reload
"""
from fastapi import FastAPI, Request

from fastidempotent import IdempotencyConfig, MemoryBackend, idempotent

app = FastAPI(title="fastidempotent — Memory Example")

# Create an in-memory backend (data lost on restart)
backend = MemoryBackend(ttl=3600, max_size=10_000)

config = IdempotencyConfig(
    ttl=3600,
    optional=False,
    fingerprint_body=True,
)


@app.post("/payments")
@idempotent(backend=backend, config=config)
async def create_payment(request: Request, amount: float):
    """
    Idempotent payment endpoint;

    Try it:
        curl -X POST http://localhost:8000/payments?amount=99.99 \\
             -H "Idempotency-Key: pay-001"

        # Repeat the same curl — you'll get the cached resp
    """
    return {
        "status": "charged",
        "amount": amount,
        "message": "Payment processed successfully",
    }


@app.post("/orders")
@idempotent(backend=backend, config=config)
async def create_order(request: Request, item: str, qty: int = 1):
    return {
        "item": item,
        "qty": qty,
        "status": "created",
    }


@app.get("/health")
async def health():
    """Health check — no idempotency needed for GET;"""
    return {"status": "ok", "backend": repr(backend)}
