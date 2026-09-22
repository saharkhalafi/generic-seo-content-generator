from __future__ import annotations

import json
import logging
import shutil
import subprocess
from typing import Any, Callable, TypeVar

from google import genai
from google.auth import default as google_auth_default
from google.auth.credentials import Credentials
from google.auth.exceptions import DefaultCredentialsError
from google.genai import types
from google.oauth2 import credentials as oauth2_credentials
from pydantic import BaseModel, ValidationError

from src.config import Settings, get_settings
from src.domain.errors import redact
from src.retrying import api_retry, is_retryable_api_error

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

_ADC_HELP = (
    "برای احراز هویت پایدار Vertex AI این دستورها را اجرا کنید:\n"
    "gcloud auth application-default login --project={project}\n"
    "gcloud auth application-default set-quota-project {project}"
)


class VertexAuthError(RuntimeError):
    pass


class VertexGenerationError(RuntimeError):
    pass


def _is_retryable(exc: BaseException) -> bool:
    return is_retryable_api_error(exc)


def _adc_help(project_id: str) -> str:
    return _ADC_HELP.format(project=project_id)


def resolve_credentials(project_id: str) -> tuple[Credentials | None, str]:
    try:
        credentials, detected = google_auth_default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
            quota_project_id=project_id,
        )
        if credentials:
            if hasattr(credentials, "with_quota_project"):
                credentials = credentials.with_quota_project(project_id)
            account = getattr(credentials, "service_account_email", None) or detected or "ADC"
            return credentials, f"احراز هویت Vertex AI با ADC آماده است ({account} / {project_id})."
    except DefaultCredentialsError:
        logger.info("ADC missing; trying gcloud user credentials.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("ADC check failed: %s", redact(str(exc)))

    gcloud = shutil.which("gcloud")
    if not gcloud:
        return None, "ADC موجود نیست و gcloud در PATH پیدا نشد. " + _adc_help(project_id)
    try:
        completed = subprocess.run(
            [gcloud, "auth", "print-access-token"],
            check=True,
            capture_output=True,
            text=True,
        )
        token = (completed.stdout or "").strip()
        if not token:
            return None, "توکن gcloud خالی بود. " + _adc_help(project_id)
        credentials = oauth2_credentials.Credentials(token=token)
        if hasattr(credentials, "with_quota_project"):
            credentials = credentials.with_quota_project(project_id)
        return credentials, (
            f"احراز هویت موقت با حساب gcloud برای پروژه {project_id} انجام شد. "
            "برای محیط پایدار ADC را تنظیم کنید."
        )
    except subprocess.CalledProcessError:
        return None, "ورود gcloud معتبر نیست. " + _adc_help(project_id)


def check_adc(project_id: str) -> tuple[bool, str]:
    credentials, message = resolve_credentials(project_id)
    return credentials is not None, message


def _client_http_options(settings: Settings) -> dict[str, int]:
    return {"timeout": int(settings.gemini_timeout_seconds * 1000)}


def create_genai_client(settings: Settings | None = None) -> tuple[genai.Client, str, str]:
    """Prefer a local Gemini API key. Fall back to Vertex only when a project is configured."""
    settings = settings or get_settings()
    http_options = _client_http_options(settings)
    if settings.gemini_api_key:
        client = genai.Client(api_key=settings.gemini_api_key, http_options=http_options)
        return client, "gemini", "احراز هویت Gemini با کلید API آماده است."
    if not settings.project_id:
        raise VertexAuthError(
            "کلید GEMINI_API_KEY در فایل .env تنظیم نشده است. "
            "برای اجرای محلی، کلید Gemini خود را در .env قرار دهید."
        )
    credentials, message = resolve_credentials(settings.project_id)
    if credentials is None:
        raise VertexAuthError(message)
    client = genai.Client(
        vertexai=True,
        project=settings.project_id,
        location=settings.location,
        credentials=credentials,
        http_options=http_options,
    )
    return client, "vertex", message


class VertexClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client, self.provider, self.auth_message = create_genai_client(self.settings)
        logger.info(self.auth_message)
        self._working_models: dict[str, str] = {}
        self.last_model = self.settings.analysis_models[0]
        self.call_listener: Callable[[dict[str, Any]], None] | None = None

    def generate_json(
        self,
        *,
        stage: str,
        system: str,
        user: str,
        schema: type[T],
        kind: str = "analysis",
        temperature: float = 0.35,
    ) -> T:
        models = self._models_for(kind)
        last_error: Exception | None = None
        for model_name in models:
            try:
                parsed = self._generate_json_with_model(
                    model_name=model_name,
                    system=system,
                    user=user,
                    schema=schema,
                    temperature=temperature,
                    stage=stage,
                )
                self._working_models[kind] = model_name
                self.last_model = model_name
                logger.info("Stage %s used model %s", stage, model_name)
                return parsed
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning("Stage %s failed on %s: %s", stage, model_name, redact(str(exc))[:300])
                continue
        raise VertexGenerationError(
            f"تولید JSON برای مرحله {stage} ناموفق بود: {redact(str(last_error))[:300]}"
        )

    def generate_text(
        self,
        *,
        stage: str,
        system: str,
        user: str,
        kind: str = "content",
        temperature: float = 0.55,
    ) -> str:
        models = self._models_for(kind)
        last_error: Exception | None = None
        for model_name in models:
            try:
                text = self._generate_text_with_model(
                    model_name=model_name,
                    system=system,
                    user=user,
                    temperature=temperature,
                    stage=stage,
                )
                self._working_models[kind] = model_name
                self.last_model = model_name
                logger.info("Stage %s used model %s", stage, model_name)
                return text
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning("Stage %s failed on %s: %s", stage, model_name, redact(str(exc))[:300])
                continue
        raise VertexGenerationError(
            f"تولید متن برای مرحله {stage} ناموفق بود: {redact(str(last_error))[:300]}"
        )

    def _models_for(self, kind: str) -> tuple[str, ...]:
        cached = self._working_models.get(kind)
        if kind == "content":
            models = self.settings.content_models
        elif kind == "validation":
            models = self.settings.validation_models
        else:
            models = self.settings.analysis_models
        if cached:
            rest = [item for item in models if item != cached]
            ordered = (cached, *rest)
        else:
            ordered = models
        return ordered[: max(1, self.settings.gemini_max_models)]

    def _emit_call(self, record: dict[str, Any]) -> None:
        if self.call_listener:
            self.call_listener(record)

    def _usage_from_response(self, response: Any) -> tuple[int | None, int | None]:
        usage = getattr(response, "usage_metadata", None)
        if not usage:
            return None, None
        return getattr(usage, "prompt_token_count", None), getattr(usage, "candidates_token_count", None)

    @api_retry()
    def _generate_json_with_model(
        self,
        *,
        model_name: str,
        system: str,
        user: str,
        schema: type[T],
        temperature: float,
        stage: str = "",
    ) -> T:
        import time
        from datetime import datetime, timezone

        started = time.perf_counter()
        started_at = datetime.now(timezone.utc)
        try:
            config_kwargs: dict[str, Any] = {
                "temperature": temperature,
                "system_instruction": system,
                "response_mime_type": "application/json",
                "response_schema": schema,
            }
            if "2.5" in model_name:
                config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
            config = types.GenerateContentConfig(**config_kwargs)
            response = self._client.models.generate_content(
                model=model_name,
                contents=user,
                config=config,
            )
            raw = (response.text or "").strip()
            if not raw:
                raise VertexGenerationError("پاسخ خالی از مدل دریافت شد.")
            try:
                parsed = schema.model_validate_json(raw)
            except ValidationError:
                try:
                    payload = _extract_json_object(raw)
                    parsed = schema.model_validate(payload)
                except (ValidationError, VertexGenerationError, json.JSONDecodeError) as inner:
                    raise VertexGenerationError(
                        f"invalid_structured_output: {inner}"
                    ) from inner
            duration_ms = int((time.perf_counter() - started) * 1000)
            in_tok, out_tok = self._usage_from_response(response)
            self._emit_call(
                {
                    "provider": self.provider,
                    "model": model_name,
                    "operation": "generate_json",
                    "stage": stage,
                    "started_at": started_at,
                    "duration_ms": duration_ms,
                    "input_tokens": in_tok,
                    "output_tokens": out_tok,
                    "estimated_cost_usd": None,
                    "status": "success",
                    "retry_count": 0,
                }
            )
            return parsed
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            self._emit_call(
                {
                    "provider": self.provider,
                    "model": model_name,
                    "operation": "generate_json",
                    "stage": stage,
                    "started_at": started_at,
                    "duration_ms": duration_ms,
                    "status": "failure",
                    "error_type": type(exc).__name__,
                    "error_message": redact(str(exc))[:500],
                    "retry_count": 0,
                }
            )
            raise

    @api_retry()
    def _generate_text_with_model(
        self,
        *,
        model_name: str,
        system: str,
        user: str,
        temperature: float,
        stage: str = "",
    ) -> str:
        import time
        from datetime import datetime, timezone

        started = time.perf_counter()
        started_at = datetime.now(timezone.utc)
        try:
            config_kwargs: dict[str, Any] = {
                "temperature": temperature,
                "system_instruction": system,
            }
            if "2.5" in model_name:
                config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
            config = types.GenerateContentConfig(**config_kwargs)
            response = self._client.models.generate_content(
                model=model_name,
                contents=user,
                config=config,
            )
            text = (response.text or "").strip()
            if not text:
                raise VertexGenerationError("پاسخ خالی از مدل دریافت شد.")
            duration_ms = int((time.perf_counter() - started) * 1000)
            in_tok, out_tok = self._usage_from_response(response)
            self._emit_call(
                {
                    "provider": self.provider,
                    "model": model_name,
                    "operation": "generate_text",
                    "stage": stage,
                    "started_at": started_at,
                    "duration_ms": duration_ms,
                    "input_tokens": in_tok,
                    "output_tokens": out_tok,
                    "estimated_cost_usd": None,
                    "status": "success",
                    "retry_count": 0,
                }
            )
            return text
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            self._emit_call(
                {
                    "provider": self.provider,
                    "model": model_name,
                    "operation": "generate_text",
                    "stage": stage,
                    "started_at": started_at,
                    "duration_ms": duration_ms,
                    "status": "failure",
                    "error_type": type(exc).__name__,
                    "error_message": redact(str(exc))[:500],
                    "retry_count": 0,
                }
            )
            raise

    def ping(self) -> str:
        class _Ping(BaseModel):
            ok: bool
            message: str

        result = self.generate_json(
            stage="connection_ping",
            system="Return JSON only.",
            user='Set ok=true and message="pong".',
            schema=_Ping,
            kind="analysis",
            temperature=0,
        )
        if not result.ok:
            raise VertexGenerationError("پاسخ اتصال Gemini نامعتبر بود.")
        return result.message


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise VertexGenerationError("JSON معتبر در پاسخ مدل پیدا نشد.")
    return json.loads(text[start : end + 1])
