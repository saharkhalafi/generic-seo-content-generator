from __future__ import annotations

import time
from typing import Callable, TypeVar

from google.genai.errors import ClientError, ServerError
from pydantic import ValidationError
from tenacity import retry, retry_if_exception
from tenacity.stop import stop_base
from tenacity.wait import wait_base

from src.config import get_settings

T = TypeVar("T")


def is_retryable_api_error(exc: BaseException) -> bool:
    """Retry only transient transport, timeout, and overload failures."""
    if isinstance(exc, (ValidationError, ValueError)):
        return False
    name = type(exc).__name__.lower()
    if "vertexgenerationerror" in name or "invalid_structured_output" in str(exc).lower():
        return False
    if isinstance(exc, (ConnectionError, TimeoutError, BrokenPipeError)):
        return True
    if "timeout" in name:
        return True
    if isinstance(exc, ServerError):
        return True
    if isinstance(exc, ClientError):
        code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        return code in {408, 429, 500, 503, 504}
    return False


def is_transient_db_error(exc: BaseException) -> bool:
    name = type(exc).__name__.lower()
    if name in {"integrityerror", "dataerror", "programmingerror", "invalidrequesterror"}:
        return False
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    if name in {"operationalerror", "interfaceerror", "dbapierror"}:
        return bool(getattr(exc, "connection_invalidated", False) or name != "dbapierror")
    message = str(exc).lower()
    return any(token in message for token in ("timeout", "connection refused", "could not connect", "deadlock"))


class _StopConfigured(stop_base):
    def __call__(self, retry_state) -> bool:
        return retry_state.attempt_number >= max(1, get_settings().gemini_max_attempts)


class _WaitConfigured(wait_base):
    def __call__(self, retry_state) -> float:
        settings = get_settings()
        delay = settings.gemini_retry_min_seconds * (2 ** (retry_state.attempt_number - 1))
        return min(settings.gemini_retry_max_seconds, delay)


def api_retry():
    return retry(
        wait=_WaitConfigured(),
        stop=_StopConfigured(),
        retry=retry_if_exception(is_retryable_api_error),
        reraise=True,
    )


def call_with_retry(
    fn: Callable[[], T],
    *,
    is_retryable: Callable[[BaseException], bool],
    max_attempts: int,
    base_delay: float = 0.2,
    max_delay: float = 2.0,
) -> T:
    attempts = max(1, max_attempts)
    last_error: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt >= attempts or not is_retryable(exc):
                raise
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            time.sleep(delay)
    if last_error:
        raise last_error
    raise RuntimeError("retry failed without an exception")
