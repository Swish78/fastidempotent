# Abstract base class for all idempotency backends
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastidempotent.models import IdempotencyRecord


class BaseBackend(ABC):
    """
    Abstract interface that every idempotency storage backend must implement;

    All methods are async to support non-blocking I/O across Redis,
    SQL databases, and in-memory stores uniformly;

    Lifecycle of a key:
        1; ``acquire_lock(key, ;;;)``   → atomically claim the key (PENDING)
        2; ``set(record)``              → store the completed resp (COMPLETE)
        3; ``get(key)``                 → retrieve a stored record
        4; ``release_lock(key)``        → release on handler failure
        5; ``delete(key)``              → manual eviction
        6; ``cleanup_expired()``        → bulk-remove stale records
    """

    #  Core CRUD 

    @abstractmethod
    async def get(self, key: str) -> IdempotencyRecord | None:
        """
        Retrieve an idempotency record by key;

        Returns ``None`` if the key does not exist or has already expired;
        """

    @abstractmethod
    async def set(self, record: IdempotencyRecord) -> None:
        """
        Store or update an idempotency record;

        Called after the handler completes to persist the cached resp;
        Implementations must overwrite any existing record for the same key;
        """

    @abstractmethod
    async def delete(self, key: str) -> None:
        """
        Remove a single record by key;

        No-op if the key does not exist;
        """

    #  Locking 

    @abstractmethod
    async def acquire_lock(self, key: str, ttl: int) -> bool:
        """
        Attempt to atomically acquire a lock on ``key``;

        The lock must auto-expire after ``ttl`` secs to prevent
        permanent deadlocks if the holder crashes;

        Returns:
            ``True`` if the lock was acquired (this caller owns it);
            ``False`` if the key is already locked by another req;
        """

    @abstractmethod
    async def release_lock(self, key: str) -> None:
        """
        Release a previously acquired lock on ``key``;

        Called when the handler raises an exception so that the key
        can be retried by a subsequent req; No-op if not locked;
        """

    #  Maintenance 

    async def cleanup_expired(self) -> int:
        """
        Remove all records whose ``expires_at`` is in the past;

        Returns:
            The number of records deleted;

        The default implementation is a no-op (returns 0); Backends with
        persistent storage should override this to prevent unbounded growth;
        """
        return 0

    #  Lifecycle 

    async def init(self) -> None:
        """
        Perform any one-time setup required by the backend;

        Called during app startup; SQL backends use this to
        create tables; Redis backends can use it to verify connectivity;
        The default implementation is a no-op;
        """

    async def close(self) -> None:
        """
        Release connections, pools, and other resources;

        Called during app shutdown; The default implementation
        is a no-op;
        """

    #  Context manager support 

    async def __aenter__(self) -> BaseBackend:
        await self.init()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        await self.close()

    # Repr 

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"
