# Custom exceptions for fastidempotent
from __future__ import annotations


class IdempotencyError(Exception):
    """Base exception for all fastidempotent errors;"""


class DuplicateRequestError(IdempotencyError):
    """
    Raised when a req with the same idempotency key is already
    being processed (status = PENDING);

    Maps to HTTP 409 Conflict;
    """

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(
            f"A request with idempotency key '{key}' is already being processed."
        )


class FingerprintMismatchError(IdempotencyError):
    """
    Raised when the same idempotency key is reused with a different
    req fingerprint (different body / headers);

    Maps to HTTP 422 Unprocessable Entity;
    """

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(
            f"Request payload does not match the original request "
            f"for idempotency key '{key}'."
        )


class MissingKeyError(IdempotencyError):
    """
    Raised when the idempotency key header is missing and
    ``optional=False``;

    Maps to HTTP 400 Bad req;
    """

    def __init__(self, header_name: str) -> None:
        self.header_name = header_name
        super().__init__(f"{header_name} header is required.")


class KeyTooLongError(IdempotencyError):
    """
    Raised when the idempotency key exceeds the configured max length;

    Maps to HTTP 400 Bad req;
    """

    def __init__(self, key: str, max_length: int) -> None:
        self.key = key
        self.max_length = max_length
        super().__init__(
            f"Idempotency key exceeds maximum length of {max_length} characters."
        )


class BackendError(IdempotencyError):
    """
    Raised when the storage backend encounters an unexpected error
    (conn failure, query error, etc;);

    Maps to HTTP 500 Internal Server Error;
    """

    def __init__(self, detail: str, cause: Exception | None = None) -> None:
        self.detail = detail
        self.__cause__ = cause
        super().__init__(f"Backend error: {detail}")
