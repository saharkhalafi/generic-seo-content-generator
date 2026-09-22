from __future__ import annotations

from src.domain.errors import redact
from src.logutil import log_event
from src.persistence.database import is_postgres_configured
from src.persistence.postgres_repository import PostgresRunRepository
from src.storage import Store


class PipelineStoreAdapter:
    """Cannibalization for pipeline; persistence handled by orchestrator after run."""

    def __init__(self, composite: CompositeRunStore) -> None:
        self._composite = composite

    def cannibalization_warnings(
        self, category_name: str, primary_keyword: str, threshold: float, website_name: str = ""
    ):
        return self._composite.cannibalization_warnings(
            category_name, primary_keyword, threshold, website_name=website_name
        )

    def save_run(self, user_input, box, model: str, prompt_versions: dict[str, str]) -> int:
        return 0


class CompositeRunStore:
    """Uses PostgreSQL when DATABASE_URL is set; always keeps SQLite for backward compatibility."""

    def __init__(self, sqlite_path=None) -> None:
        self._sqlite = Store(sqlite_path)
        self._postgres: PostgresRunRepository | None = None
        if is_postgres_configured():
            self._postgres = PostgresRunRepository()

    @property
    def postgres(self) -> PostgresRunRepository | None:
        return self._postgres

    def cannibalization_warnings(
        self, category_name: str, primary_keyword: str, threshold: float, website_name: str = ""
    ):
        if self._postgres:
            warnings = self._postgres.cannibalization_warnings(
                category_name, primary_keyword, threshold, website_name=website_name
            )
            if warnings:
                return warnings
        return self._sqlite.cannibalization_warnings(
            category_name, primary_keyword, threshold, website_name=website_name
        )

    def save_run(self, user_input, box, model: str, prompt_versions: dict[str, str], **extra) -> int | str:
        sqlite_id = self._sqlite.save_run(user_input, box, model, prompt_versions)
        if self._postgres and extra.get("run_id"):
            try:
                self._postgres.save_run(
                    run_id=extra["run_id"],
                    user_input=user_input,
                    box=box,
                    model=model,
                    prompt_versions=prompt_versions,
                    latency_ms=extra.get("latency_ms"),
                    topic_map=extra.get("topic_map"),
                    heading_plan=extra.get("heading_plan"),
                    model_calls=extra.get("model_calls"),
                    stages=extra.get("stages"),
                )
            except Exception as exc:  # noqa: BLE001
                log_event(
                    "DATABASE",
                    "postgres save failed; sqlite fallback kept",
                    run_id=str(extra.get("run_id") or ""),
                    status="failure",
                    error_type="database_error",
                    error=redact(str(exc))[:300],
                    level=40,
                )
        return sqlite_id


def get_run_store(sqlite_path=None) -> CompositeRunStore:
    return CompositeRunStore(sqlite_path)
