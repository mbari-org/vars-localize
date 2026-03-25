"""Shared HTTP request policy helpers for service clients."""

from __future__ import annotations

import time
from typing import Optional

import requests

from vars_localize.services.errors import ServiceRequestError

DEFAULT_TIMEOUT_SECS = 8
DEFAULT_RETRIES = 2
DEFAULT_BACKOFF_SECS = 0.2


def _status_code_from_exception(exc: Exception) -> Optional[int]:
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None)


def _is_retryable_exception(exc: Exception) -> bool:
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True

    if isinstance(exc, requests.HTTPError):
        status_code = _status_code_from_exception(exc)
        return status_code is not None and (status_code >= 500 or status_code == 429)

    return False


def request_with_policy(
    session: requests.Session,
    method: str,
    url: str,
    *,
    timeout_secs: int = DEFAULT_TIMEOUT_SECS,
    retries: int = DEFAULT_RETRIES,
    backoff_secs: float = DEFAULT_BACKOFF_SECS,
    **kwargs,
) -> requests.Response:
    """Execute an HTTP request with consistent timeout/retry/backoff behavior."""
    last_exc: Optional[Exception] = None
    timeout = max(1, int(timeout_secs))
    max_retries = max(0, int(retries))

    for attempt in range(max_retries + 1):
        try:
            response = session.request(method, url, timeout=timeout, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_exc = exc
            should_retry = attempt < max_retries and _is_retryable_exception(exc)
            if not should_retry:
                break
            time.sleep(backoff_secs * (2**attempt))

    status_code = _status_code_from_exception(last_exc) if last_exc else None
    message = str(last_exc) if last_exc is not None else "HTTP request failed"
    raise ServiceRequestError(
        message=message,
        method=method,
        url=url,
        status_code=status_code,
    ) from last_exc
