"""Typed service-layer exceptions used by API clients and facades."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


class ServiceError(Exception):
    """Base class for service-layer failures."""


@dataclass
class ServiceRequestError(ServiceError):
    """Represents an HTTP transport or response failure."""

    message: str
    method: str
    url: str
    status_code: Optional[int] = None

    def __str__(self) -> str:
        status = f" status={self.status_code}" if self.status_code is not None else ""
        return f"{self.message} ({self.method.upper()} {self.url}{status})"


class ServiceAuthError(ServiceError):
    """Authentication or authorization failure."""


class ServiceValidationError(ServiceError):
    """Client-side input validation failure before a network request."""


class ServiceNotConfiguredError(ServiceError):
    """Raised when a service is used before configure() has completed."""
