# In-memory backend (dict-based)
from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from fastidempotent.backends.base import BaseBackend

if TYPE_CHECKING:
    from fastidempotent.models import IdempotencyRecord


class MemoryBackend(BaseBackend):
    """
    Dict-backed in-memory idempotency store;
    Data is lost on restart; NOT safe across multiple workers/processes;

    Per-key TTL is enforced lazily on ``get()`` and eagerly via
    ``cleanup_expired()``;
    """

    def __init__(self, ttl: int = 3600, max_size: int = 10_000) -> None:
        self._ttl = ttl
        self._max_size = max_size

        # key -> IdempotencyRecord
        self._store: dict[str, IdempotencyRecord] = {}

        # key -> expiry timestamp (monotonic)
        self._expiry: dict[str, float] = {}

        # key -> asyncio;Event (acts as a per-key lock)
        # Present = key is locked (PENDING); absent = unlocked
        self._locks: dict[str, float] = {}

        # Serialises writes to the internal dicts
        self._mu = asyncio.Lock()

    #  Core CRUD 

    async def get(self, key: str) -> IdempotencyRecord | None:
        async with self._mu:
            if key not in self._store:
                return None

            # Lazy expiry check
            if self._is_expired(key):
                self._evict(key)
                return None

            return self._store[key]

    async def set(self, record: IdempotencyRecord) -> None:
        async with self._mu:
            # Enforce max size by evicting oldest entries
            if len(self._store) >= self._max_size and record.key not in self._store:
                self._evict_oldest()

            self._store[record.key] = record
            self._expiry[record.key] = time.monotonic() + self._ttl

            # Clear the lock since the record is now COMPLETE
            self._locks.pop(record.key, None)

    async def delete(self, key: str) -> None:
        async with self._mu:
            self._evict(key)

    #  Locking 

    async def acquire_lock(self, key: str, ttl: int) -> bool:
        async with self._mu:
            now = time.monotonic()

            # If already locked and lock hasn't expired → deny
            if key in self._locks:
                if now < self._locks[key]:
                    return False
                # Stale lock — reclaim it
                self._locks.pop(key, None)

            # If a completed record already exists → deny
            # (caller should use get() first, but be safe)
            if key in self._store and not self._is_expired(key):
                return False

            self._locks[key] = now + ttl
            return True

    async def release_lock(self, key: str) -> None:
        async with self._mu:
            self._locks.pop(key, None)
            # Also remove any partial record that may have been stored
            self._evict(key)

    #  Maintenance 

    async def cleanup_expired(self) -> int:
        async with self._mu:
            now = time.monotonic()
            expired_keys = [
                k for k, exp in self._expiry.items() if now >= exp
            ]
            for k in expired_keys:
                self._evict(k)

            # Also clean stale locks
            stale_locks = [
                k for k, exp in self._locks.items() if now >= exp
            ]
            for k in stale_locks:
                self._locks.pop(k, None)

            return len(expired_keys)

    #  Lifecycle 

    async def close(self) -> None:
        async with self._mu:
            self._store.clear()
            self._expiry.clear()
            self._locks.clear()

    #  Private helpers 

    def _is_expired(self, key: str) -> bool:
        """Check if a key has passed its expiry time (monotonic);"""
        return time.monotonic() >= self._expiry.get(key, 0.0)

    def _evict(self, key: str) -> None:
        """Remove a key from all internal dicts;"""
        self._store.pop(key, None)
        self._expiry.pop(key, None)
        self._locks.pop(key, None)

    def _evict_oldest(self) -> None:
        """Remove the entry with the earliest expiry to make room;"""
        if not self._expiry:
            return
        oldest_key = min(self._expiry, key=self._expiry.get)  # type: ignore[arg-type]
        self._evict(oldest_key)

    def __repr__(self) -> str:
        return (
            f"<MemoryBackend "
            f"entries={len(self._store)} "
            f"max_size={self._max_size} "
            f"ttl={self._ttl}>"
        )
