from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from src.config import _int_env
from src.domain.errors import AppError, ErrorCategory
from src.logutil import log_event

_gate: "GenerationGate | None" = None
_gate_lock = threading.Lock()


def max_concurrent_generations() -> int:
    return _int_env("MAX_CONCURRENT_GENERATIONS", 2, minimum=1, maximum=8)


def max_requests_per_minute() -> int:
    return _int_env("MAX_REQUESTS_PER_MINUTE", 6, minimum=1, maximum=60)


def daily_limit_per_client() -> int:
    return _int_env("DAILY_LIMIT_PER_CLIENT", 20, minimum=1, maximum=500)


def daily_limit_global() -> int:
    return _int_env("DAILY_LIMIT_GLOBAL", 40, minimum=1, maximum=2000)


class GenerationGate:
    """In-process rate, daily, and concurrency limits. Excess requests are rejected."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._in_flight = 0
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._daily: dict[str, tuple[str, int]] = {}
        self._global_daily: tuple[str, int] = ("", 0)

    def acquire(self, client_key: str) -> None:
        key = (client_key or "anonymous").strip() or "anonymous"
        now = time.monotonic()
        day = datetime.now(timezone.utc).date().isoformat()
        with self._lock:
            window = self._hits[key]
            while window and now - window[0] > 60:
                window.popleft()
            if len(window) >= max_requests_per_minute():
                log_event("RATE_LIMIT", "request rejected", error="rate_limit", level=30)
                raise AppError(
                    ErrorCategory.RATE_LIMIT,
                    "تعداد درخواست در این دقیقه به سقف رسیده است. کمی بعد دوباره تلاش کنید.",
                )
            client_count = self._daily_count(key, day)
            if client_count >= daily_limit_per_client():
                log_event("RATE_LIMIT", "daily client limit", error="daily_limit", level=30)
                raise AppError(
                    ErrorCategory.RATE_LIMIT,
                    "سقف تولید امروز برای این کاربر پر شده است.",
                )
            global_count = max(self._global_count(day), _postgres_runs_today())
            if global_count >= daily_limit_global():
                log_event("RATE_LIMIT", "daily global limit", error="daily_limit", level=30)
                raise AppError(
                    ErrorCategory.RATE_LIMIT,
                    "سقف تولید امروز پر شده است.",
                )
            if self._in_flight >= max_concurrent_generations():
                log_event("RATE_LIMIT", "concurrency rejected", error="concurrency_limit", level=30)
                raise AppError(
                    ErrorCategory.CONCURRENCY_LIMIT,
                    "چند تولید دیگر در حال اجراست. کمی بعد دوباره تلاش کنید.",
                )
            window.append(now)
            self._bump_daily(key, day)
            self._in_flight += 1

    def release(self) -> None:
        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)

    def _daily_count(self, key: str, day: str) -> int:
        stored = self._daily.get(key)
        if not stored or stored[0] != day:
            return 0
        return stored[1]

    def _global_count(self, day: str) -> int:
        if self._global_daily[0] != day:
            return 0
        return self._global_daily[1]

    def _bump_daily(self, key: str, day: str) -> None:
        self._daily[key] = (day, self._daily_count(key, day) + 1)
        self._global_daily = (day, self._global_count(day) + 1)


def get_gate() -> GenerationGate:
    global _gate
    with _gate_lock:
        if _gate is None:
            _gate = GenerationGate()
        return _gate


def reset_gate() -> None:
    global _gate
    with _gate_lock:
        _gate = None


def _postgres_runs_today() -> int:
    try:
        from src.persistence.database import is_postgres_configured

        if not is_postgres_configured():
            return 0
        from src.persistence.postgres_repository import PostgresRunRepository

        return PostgresRunRepository().count_runs_today()
    except Exception as exc:  # noqa: BLE001
        log_event("DATABASE", "daily usage count failed", error=type(exc).__name__, level=30)
        return 0


def generation_slot(client_key: str):
    gate = get_gate()
    gate.acquire(client_key)

    class _Slot:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            gate.release()
            return False

    return _Slot()


def client_log_id(client_key: str) -> str:
    import hashlib

    return hashlib.sha256((client_key or "anonymous").encode("utf-8")).hexdigest()[:12]
