from __future__ import annotations

import re
from enum import Enum


class ErrorCategory(str, Enum):
    AUTHENTICATION_ERROR = "authentication_error"
    RATE_LIMIT = "rate_limit"
    CONCURRENCY_LIMIT = "concurrency_limit"
    TIMEOUT = "timeout"
    INVALID_OUTPUT = "invalid_output"
    VALIDATION_ERROR = "validation_error"
    DATABASE_ERROR = "database_error"
    IMAGE_GENERATION_ERROR = "image_generation_error"
    GENERATION_ERROR = "generation_error"
    EXPORT_ERROR = "export_error"
    INPUT_ERROR = "input_error"
    UNKNOWN_ERROR = "unknown_error"


class AppError(Exception):
    """User-facing error whose message is already safe to display."""

    def __init__(self, category: ErrorCategory, message: str) -> None:
        super().__init__(message)
        self.category = category


_SECRET_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z_\-]{10,}"),
    re.compile(r"AQ\.[0-9A-Za-z_\-]{8,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(r"(?i)(api[_-]?key|authorization|password|secret|token|database_url)\s*[:=]\s*\S+"),
    re.compile(r"postgres(?:ql)?(?:\+psycopg)?://[^\s'\"]+"),
)


_PUBLIC_MESSAGES = {
    ErrorCategory.AUTHENTICATION_ERROR: "احراز هویت سرویس مدل انجام نشد. تنظیمات محیط را بررسی کنید.",
    ErrorCategory.RATE_LIMIT: "تعداد درخواست بیش از حد مجاز است. کمی بعد دوباره تلاش کنید.",
    ErrorCategory.CONCURRENCY_LIMIT: "تعداد تولید همزمان به سقف رسیده است. کمی بعد دوباره تلاش کنید.",
    ErrorCategory.TIMEOUT: "زمان درخواست به پایان رسید. دوباره تلاش کنید.",
    ErrorCategory.INVALID_OUTPUT: "خروجی مدل قابل استفاده نبود. دوباره تلاش کنید.",
    ErrorCategory.VALIDATION_ERROR: "ورودی نامعتبر است.",
    ErrorCategory.DATABASE_ERROR: "ذخیره‌سازی موقتاً در دسترس نیست.",
    ErrorCategory.IMAGE_GENERATION_ERROR: "ساخت تصویر شاخص انجام نشد. محتوای سئو حفظ شده است.",
    ErrorCategory.GENERATION_ERROR: "تولید محتوا ناموفق بود. دوباره تلاش کنید.",
    ErrorCategory.EXPORT_ERROR: "خروجی فایل ساخته نشد.",
    ErrorCategory.INPUT_ERROR: "ورودی خارج از حد مجاز است.",
    ErrorCategory.UNKNOWN_ERROR: "درخواست انجام نشد. دوباره تلاش کنید.",
}


def redact(text: str) -> str:
    cleaned = text or ""
    if "Traceback (most recent call last)" in cleaned:
        cleaned = cleaned.split("Traceback (most recent call last)", 1)[0].strip()
    cleaned = "\n".join(
        line for line in cleaned.splitlines() if not line.strip().startswith('File "')
    )
    for pattern in _SECRET_PATTERNS:
        cleaned = pattern.sub("[redacted]", cleaned)
    return cleaned.strip()


def classify_error(exc: BaseException) -> ErrorCategory:
    category = getattr(exc, "category", None)
    if isinstance(category, ErrorCategory):
        return category
    message = str(exc).lower()
    name = type(exc).__name__.lower()
    if "auth" in message or "credential" in message or "401" in message or "403" in message:
        return ErrorCategory.AUTHENTICATION_ERROR
    if type(exc).__name__ in {"RateLimitError"} or "rate" in message or "429" in message or "quota" in message:
        return ErrorCategory.RATE_LIMIT
    if "concurrency" in message or "too many" in message:
        return ErrorCategory.CONCURRENCY_LIMIT
    if "timeout" in message or "timed out" in message or "deadline" in message or "timeout" in name:
        return ErrorCategory.TIMEOUT
    if "invalid_structured_output" in message:
        return ErrorCategory.INVALID_OUTPUT
    if "database" in message or "psycopg" in message or "sqlalchemy" in name or "operationalerror" in name:
        return ErrorCategory.DATABASE_ERROR
    if "image" in message and ("generat" in message or "feature" in message):
        return ErrorCategory.IMAGE_GENERATION_ERROR
    if "export" in message:
        return ErrorCategory.EXPORT_ERROR
    if name == "validationerror" or "validation" in message:
        return ErrorCategory.VALIDATION_ERROR
    if "generation" in message or "vertex" in name:
        return ErrorCategory.GENERATION_ERROR
    return ErrorCategory.UNKNOWN_ERROR


def public_error_message(exc: BaseException) -> str:
    """Message safe for the UI. Never includes tracebacks or secrets."""
    if isinstance(exc, AppError):
        return redact(str(exc)) or _PUBLIC_MESSAGES[exc.category]
    if type(exc).__name__ == "VertexAuthError":
        return redact(str(exc)) or _PUBLIC_MESSAGES[ErrorCategory.AUTHENTICATION_ERROR]
    if type(exc).__name__ == "ValidationError":
        return _PUBLIC_MESSAGES[ErrorCategory.VALIDATION_ERROR]
    return _PUBLIC_MESSAGES[classify_error(exc)]
