from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

from src.config import LOG_DIR
from src.domain.errors import redact

_CONFIGURED = False

_LOG_FIELDS = (
    "request_id",
    "run_id",
    "stage",
    "model",
    "duration_ms",
    "status",
    "error_type",
    "score",
    "revisions",
)


class _Defaults(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for key in _LOG_FIELDS:
            if not hasattr(record, key):
                setattr(record, key, "-")
        record.msg = redact(str(record.msg))
        if record.args:
            record.args = tuple(redact(str(arg)) if isinstance(arg, str) else arg for arg in record.args)
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": redact(record.getMessage()),
            "logger": record.name,
        }
        for key in _LOG_FIELDS:
            payload[key] = getattr(record, key, "-")
        return json.dumps(payload, ensure_ascii=False)


def setup_logging() -> logging.Logger:
    global _CONFIGURED
    logger = logging.getLogger("seo-content")
    if _CONFIGURED:
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False
    defaults = _Defaults()
    if os.getenv("LOG_FORMAT", "text").strip().lower() == "json":
        formatter: logging.Formatter = _JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s request_id=%(request_id)s run_id=%(run_id)s "
            "stage=%(stage)s model=%(model)s duration_ms=%(duration_ms)s status=%(status)s "
            "error_type=%(error_type)s score=%(score)s revisions=%(revisions)s %(message)s"
        )
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    stream.addFilter(defaults)
    logger.addHandler(stream)
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            LOG_DIR / "seo-content.log",
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(defaults)
        logger.addHandler(file_handler)
    except OSError:
        pass
    _CONFIGURED = True
    return logger


def log_event(
    stage: str,
    message: str,
    *,
    category: str = "",
    model: str = "",
    score: int | str = "",
    revisions: int | str = "",
    level: int = logging.INFO,
    error: str = "",
    request_id: str = "",
    run_id: str = "",
    duration_ms: int | str = "",
    status: str = "",
    error_type: str = "",
) -> None:
    logger = setup_logging()
    extra = {
        "request_id": request_id or "-",
        "run_id": run_id or "-",
        "stage": stage,
        "model": model or "-",
        "duration_ms": duration_ms if duration_ms != "" else "-",
        "status": status or "-",
        "error_type": error_type or "-",
        "score": score if score != "" else "-",
        "revisions": revisions if revisions != "" else "-",
    }
    text = redact(message)
    if category:
        text = f"category={category} {text}"
    if error:
        text = f"{text} error={redact(error)}"
    logger.log(level, text, extra=extra)
