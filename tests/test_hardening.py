from __future__ import annotations

import time
from pathlib import Path

import pytest
from google.genai.errors import ClientError
from pydantic import ValidationError
from sqlalchemy.engine import make_url
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.testclient import TestClient

from src.config import MAX_CONTENT_REVISIONS, get_settings
from src.domain.errors import AppError, ErrorCategory, classify_error, public_error_message, redact
from src.exporters import seo_box_to_html_document
from src.health import build_routes, health_payload, readiness_payload
from src.image.feature_image import FeatureImageService
from src.limits import GenerationGate, reset_gate
from src.persistence.database import get_database_url, reset_engine
from src.prompts.content import content_system
from src.retrying import call_with_retry, is_retryable_api_error, is_transient_db_error
from src.schemas import FinalSEOBox
from src.security import SecurityHeadersMiddleware, sanitize_html, sanitize_markdown
from tests.conftest import sample_input

ROOT = Path(__file__).resolve().parents[1]


def test_public_errors_hide_secrets_and_tracebacks():
    secret = "AIzaSyTHISSHOULDNEVERLEAK0000"
    exc = RuntimeError(f"Traceback (most recent call last):\nFile \"app.py\"\napi_key={secret}")
    message = public_error_message(exc)
    assert "Traceback" not in message
    assert secret not in message
    assert "AIza" not in redact(f"token={secret}")
    assert "postgres:postgres@" not in redact("postgresql+psycopg://postgres:postgres@localhost/content_generator")
    assert classify_error(TimeoutError("timed out")) == ErrorCategory.TIMEOUT
    assert "psycopg" not in public_error_message(RuntimeError("psycopg operational error"))


def test_retry_transient_api_and_skip_permanent():
    assert is_retryable_api_error(ClientError(429, {"error": {"message": "rate"}}, None))
    assert not is_retryable_api_error(ClientError(400, {"error": {"message": "bad request"}}, None))
    assert is_retryable_api_error(TimeoutError("timed out"))
    assert not is_retryable_api_error(ValueError("invalid request"))
    assert is_transient_db_error(TimeoutError("database timeout"))
    assert not is_transient_db_error(type("IntegrityError", (Exception,), {})("duplicate"))

    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("timed out")
        return "ok"

    assert call_with_retry(flaky, is_retryable=is_retryable_api_error, max_attempts=2, base_delay=0, max_delay=0) == "ok"
    assert calls["n"] == 2

    def permanent():
        raise ClientError(400, {"error": {"message": "bad request"}}, None)

    with pytest.raises(ClientError):
        call_with_retry(permanent, is_retryable=is_retryable_api_error, max_attempts=3, base_delay=0, max_delay=0)


def test_rate_limit_and_concurrency(monkeypatch):
    monkeypatch.setattr("src.limits._postgres_runs_today", lambda: 0)
    monkeypatch.setenv("MAX_REQUESTS_PER_MINUTE", "2")
    monkeypatch.setenv("DAILY_LIMIT_PER_CLIENT", "10")
    monkeypatch.setenv("DAILY_LIMIT_GLOBAL", "10")
    monkeypatch.setenv("MAX_CONCURRENT_GENERATIONS", "1")
    reset_gate()
    gate = GenerationGate()
    gate.acquire("client-a")
    gate.release()
    gate.acquire("client-a")
    gate.release()
    with pytest.raises(AppError) as rate_error:
        gate.acquire("client-a")
    assert rate_error.value.category == ErrorCategory.RATE_LIMIT

    limited = GenerationGate()
    limited.acquire("one")
    with pytest.raises(AppError) as busy:
        limited.acquire("two")
    assert busy.value.category == ErrorCategory.CONCURRENCY_LIMIT
    limited.release()


def test_input_limits_reject_oversized_topic():
    with pytest.raises(ValidationError):
        sample_input(category_name="موضوع" * 80)
    with pytest.raises(ValidationError):
        sample_input(website_description="توضیح وب‌سایت " * 80)
    user = sample_input()
    assert user.desired_word_count <= 1500


def test_health_and_security_headers(monkeypatch):
    assert health_payload()["status"] == "ok"
    monkeypatch.setenv("DATABASE_URL", "")
    reset_engine()
    body, code = readiness_payload()
    assert code == 200
    assert body["database"] == "sqlite"

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://invalid:invalid@127.0.0.1:1/none")
    monkeypatch.setenv("DB_CONNECT_TIMEOUT_SECONDS", "1")
    reset_engine()
    _body, status_code = readiness_payload()
    assert status_code == 503

    app = Starlette(routes=build_routes(), middleware=[Middleware(SecurityHeadersMiddleware)])
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "SAMEORIGIN"


def test_html_export_strips_active_content():
    raw = '<h1>عنوان</h1><script>alert(1)</script><a href="javascript:alert(1)">x</a><p>متن</p>'
    cleaned = sanitize_html(raw)
    assert "<script>" not in cleaned.lower()
    assert "javascript:" not in cleaned.lower()
    assert "<h1>عنوان</h1>" in cleaned
    assert "alert" not in sanitize_markdown(raw).lower() or "<script>" not in sanitize_markdown(raw).lower()
    box = FinalSEOBox(
        category="استوری",
        primary_keyword="قالب استوری",
        h1="عنوان",
        content=raw,
        seo_score=80,
        status="good",
    )
    document = seo_box_to_html_document(box)
    assert "<script>" not in document.lower()
    assert 'lang="fa"' in document


def test_image_failure_does_not_raise(tmp_path):
    service = FeatureImageService.__new__(FeatureImageService)
    service.model = "gemini-2.5-flash-image"
    service.output_dir = tmp_path
    result = FeatureImageService.generate(service, article="   ", category="topic")
    assert result.success is False
    assert result.error


def test_language_and_revision_budget():
    prompt = content_system(sample_input())
    assert "فارسی" in prompt
    assert "انگلیسی" in prompt
    assert MAX_CONTENT_REVISIONS == 1
    assert get_settings().gemini_max_attempts <= 3
    assert get_settings().gemini_max_models == 1


def test_database_url_override_keeps_database_name(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5434/content_generator",
    )
    monkeypatch.setenv("POSTGRES_HOST_OVERRIDE", "host.docker.internal")
    reset_engine()
    parsed = make_url(get_database_url())
    assert parsed.host == "host.docker.internal"
    assert parsed.database == "content_generator"
    monkeypatch.delenv("POSTGRES_HOST_OVERRIDE", raising=False)
    reset_engine()


def test_startup_paths_do_not_drop_data():
    sources = list((ROOT / "src").rglob("*.py")) + list((ROOT / "alembic").rglob("*.py"))
    text = "\n".join(path.read_text(encoding="utf-8") for path in sources)
    assert "drop_all" not in text
    assert "DROP TABLE" not in text.upper() or "DROP CONSTRAINT" in text.upper()
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert "USER appuser" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert ".env" in ignore.splitlines()


def test_queries_stay_parameterized():
    from sqlalchemy import select

    from src.persistence.models import SeoRun

    statement = select(SeoRun).where(SeoRun.run_id == "run-1")
    compiled = statement.compile()
    assert "run-1" not in str(compiled)
    assert compiled.params


def test_retry_sleep_is_bounded():
    started = time.perf_counter()
    with pytest.raises(TimeoutError):
        call_with_retry(
            lambda: (_ for _ in ()).throw(TimeoutError("timed out")),
            is_retryable=is_retryable_api_error,
            max_attempts=2,
            base_delay=0,
            max_delay=0,
        )
    assert time.perf_counter() - started < 1
