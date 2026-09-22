from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT_DIR / "outputs"

PIPELINE_VERSION = "1.0.0"
VALIDATION_VERSION = "1.0.0"

MIN_WORD_COUNT = 700
MAX_WORD_COUNT = 1500
DEFAULT_WORD_COUNT = 1000
WORD_COUNT_TOLERANCE = 0.18

SIMPLE_MIN_WORD_COUNT = 350
SIMPLE_MAX_WORD_COUNT = 800
SIMPLE_DEFAULT_WORD_COUNT = 500
SIMPLE_HARD_MAX_WORD_COUNT = 1000


def word_count_bounds(box_style: str = "full") -> tuple[int, int]:
    if box_style == "simple":
        return (
            _int_env("SIMPLE_MIN_WORDS", SIMPLE_MIN_WORD_COUNT, minimum=50, maximum=5000),
            _int_env("SIMPLE_MAX_WORDS", SIMPLE_MAX_WORD_COUNT, minimum=50, maximum=5000),
        )
    return (
        _int_env("FULL_MIN_WORDS", MIN_WORD_COUNT, minimum=50, maximum=5000),
        _int_env("FULL_MAX_WORDS", MAX_WORD_COUNT, minimum=50, maximum=5000),
    )


def default_word_count(box_style: str = "full") -> int:
    if box_style == "simple":
        return SIMPLE_DEFAULT_WORD_COUNT
    return DEFAULT_WORD_COUNT


def hard_max_word_count(box_style: str = "full") -> int:
    if box_style == "simple":
        return SIMPLE_HARD_MAX_WORD_COUNT
    return 1800


MAX_HEADING_REVISIONS = 0
MAX_CONTENT_REVISIONS = 1


def _int_env(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    return min(maximum, max(minimum, value))


def _float_env(name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw = os.getenv(name, "").strip()
    try:
        value = float(raw) if raw else default
    except ValueError:
        value = default
    return min(maximum, max(minimum, value))


def max_topic_length() -> int:
    return _int_env("MAX_TOPIC_LENGTH", 200, minimum=20, maximum=2000)


def max_website_description_length() -> int:
    return _int_env("MAX_WEBSITE_DESCRIPTION_LENGTH", 600, minimum=12, maximum=4000)


def max_existing_content_length() -> int:
    return _int_env("MAX_EXISTING_CONTENT_LENGTH", 12000, minimum=0, maximum=100000)


def max_request_chars() -> int:
    return _int_env("MAX_REQUEST_CHARS", 20000, minimum=1000, maximum=200000)


def max_list_items() -> int:
    return _int_env("MAX_LIST_ITEMS", 40, minimum=1, maximum=200)


REVISION_SCORE_THRESHOLD = 85
HEADING_SIMILARITY_THRESHOLD = 0.82
KEYWORD_STUFFING_FAIL = 0.035
KEYWORD_STUFFING_SEVERE = 0.05
CANNIBALIZATION_THRESHOLD = 0.78

DATA_DIR = ROOT_DIR / "data"
LOG_DIR = ROOT_DIR / "logs"
DEFAULT_SQLITE_PATH = DATA_DIR / "seo_content.sqlite"

SCORE_WEIGHTS = {
    "technical": 0.15,
    "keyword": 0.20,
    "intent": 0.20,
    "content": 0.20,
    "heading": 0.10,
    "persian": 0.05,
    "product": 0.05,
    "trust": 0.05,
}

DEFAULT_MODEL = "gemini-2.5-flash"

DEFAULT_INTENTS = ("Commercial", "Informational")
INTENT_OPTIONS = (
    "Informational",
    "Commercial",
    "Transactional",
    "Navigational",
    "Mixed",
)

ANALYSIS_FALLBACKS = (
    DEFAULT_MODEL,
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash-001",
    "gemini-2.0-flash",
)
CONTENT_FALLBACKS = (
    DEFAULT_MODEL,
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash-001",
    "gemini-2.0-flash",
)


def _csv_models(value: str | None, defaults: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        return defaults
    parts = tuple(item.strip() for item in value.split(",") if item.strip())
    return parts or defaults


def _models_from_env(specific_key: str, defaults: tuple[str, ...]) -> tuple[str, ...]:
    primary = os.getenv("GEMINI_MODEL", "").strip()
    specific = os.getenv(specific_key, "").strip()
    if specific:
        return _csv_models(specific, defaults)
    if primary:
        return _csv_models(primary, defaults)
    return defaults


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str = field(
        default_factory=lambda: (
            os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip()
        )
    )
    project_id: str = field(
        default_factory=lambda: os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    )
    location: str = field(
        default_factory=lambda: os.getenv("GOOGLE_CLOUD_LOCATION", "global")
    )
    sqlite_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("SQLITE_PATH", str(DEFAULT_SQLITE_PATH))
        )
    )
    analysis_models: tuple[str, ...] = field(
        default_factory=lambda: _models_from_env("GEMINI_ANALYSIS_MODEL", ANALYSIS_FALLBACKS)
    )
    content_models: tuple[str, ...] = field(
        default_factory=lambda: _models_from_env("GEMINI_CONTENT_MODEL", CONTENT_FALLBACKS)
    )
    validation_models: tuple[str, ...] = field(
        default_factory=lambda: _models_from_env("GEMINI_VALIDATION_MODEL", ANALYSIS_FALLBACKS)
    )
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", "").strip()
    )
    gemini_timeout_seconds: float = field(
        default_factory=lambda: _float_env("GEMINI_TIMEOUT_SECONDS", 60, minimum=5, maximum=180)
    )
    gemini_max_attempts: int = field(
        default_factory=lambda: _int_env("GEMINI_MAX_ATTEMPTS", 2, minimum=1, maximum=3)
    )
    gemini_retry_min_seconds: float = field(
        default_factory=lambda: _float_env("GEMINI_RETRY_MIN_SECONDS", 1, minimum=0.2, maximum=10)
    )
    gemini_retry_max_seconds: float = field(
        default_factory=lambda: _float_env("GEMINI_RETRY_MAX_SECONDS", 8, minimum=1, maximum=30)
    )
    gemini_max_models: int = field(
        default_factory=lambda: _int_env("GEMINI_MAX_MODELS", 1, minimum=1, maximum=4)
    )
    db_max_attempts: int = field(
        default_factory=lambda: _int_env("DB_MAX_ATTEMPTS", 2, minimum=1, maximum=3)
    )


def postgres_enabled() -> bool:
    url = get_settings().database_url
    return bool(url) and url.startswith(("postgresql://", "postgresql+psycopg://", "postgres://"))


def get_settings() -> Settings:
    return Settings()
