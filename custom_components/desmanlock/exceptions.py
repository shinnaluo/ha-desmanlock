"""Exceptions raised by the Desman Lock integration."""

from __future__ import annotations


class DesmanLockError(Exception):
    """Base error for the integration."""


class DesmanLockApiError(DesmanLockError):
    """An API request or response failed."""


class DesmanLockResponseError(DesmanLockApiError):
    """The cloud returned a well-formed business error (success=false).

    Unlike transport-level ``DesmanLockApiError`` failures, this means the
    server was reached and replied; the request itself was rejected.
    """

    def __init__(self, message: str, *, code: str = "") -> None:
        """Store the cloud status/code alongside the message."""
        super().__init__(message)
        self.code = code


class DesmanLockAuthError(DesmanLockApiError):
    """The Desman account authentication is invalid or expired."""
