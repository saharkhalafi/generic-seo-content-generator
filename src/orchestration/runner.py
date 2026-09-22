"""Production orchestration around the protected SEO pipeline."""

from __future__ import annotations

import time
from typing import Callable

from src.domain.errors import classify_error, redact
from src.limits import client_log_id, generation_slot
from src.llm import VertexClient, VertexGenerationError
from src.logutil import log_event
from src.observability.tracker import RunObservability
from src.persistence.factory import CompositeRunStore, PipelineStoreAdapter, get_run_store
from src.persistence.postgres_repository import new_run_id
from src.pipeline import SeoBoxPipeline
from src.prompts.versions import PROMPT_VERSIONS
from src.schemas import FinalSEOBox, RunOptions, UserInput

ProgressCb = Callable[[str, str], None]


class ProductionSeoOrchestrator:
    """Wraps SeoBoxPipeline without modifying generation logic."""

    def __init__(
        self,
        client: VertexClient | None = None,
        store: CompositeRunStore | None = None,
        on_progress: ProgressCb | None = None,
    ) -> None:
        self.client = client or VertexClient()
        self.store = store or get_run_store()
        self.on_progress = on_progress or (lambda _s, _m: None)
        self._obs: RunObservability | None = None

    def run(
        self,
        user_input: UserInput,
        options: RunOptions | None = None,
        client_key: str = "local",
    ) -> FinalSEOBox:
        options = options or RunOptions()
        run_id = new_run_id()
        obs = RunObservability(run_id=run_id)
        self._obs = obs

        def _track_call(record: dict) -> None:
            record.setdefault("stage", record.get("stage") or "")
            obs.add_model_call(record)

        self.client.call_listener = _track_call
        started = time.perf_counter()

        def progress(stage: str, message: str) -> None:
            self.on_progress(stage, message)

        pipeline = SeoBoxPipeline(self.client, on_progress=progress, store=PipelineStoreAdapter(self.store))

        try:
            with generation_slot(client_key):
                with obs.track_stage("input_validation"):
                    user_input.model_dump()

                box = pipeline.run(user_input, options)

                with obs.track_stage("finalization", model=pipeline.client.last_model):
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    self.store.save_run(
                        user_input,
                        box,
                        box.model or pipeline.client.last_model,
                        PROMPT_VERSIONS,
                        run_id=run_id,
                        latency_ms=latency_ms,
                        topic_map=box.topic_map,
                        heading_plan={"h1": box.h1, "headings": box.headings},
                        model_calls=obs.model_calls,
                        stages=[s.to_dict() for s in obs.stages],
                    )
                box.pipeline_notes = [*box.pipeline_notes, f"run_id={run_id}", f"latency_ms={latency_ms}"]
                log_event(
                    "finalization",
                    "generation finished",
                    request_id=run_id,
                    run_id=run_id,
                    model=box.model or pipeline.client.last_model,
                    duration_ms=latency_ms,
                    status=box.status,
                    revisions=box.revision_count,
                    score=box.seo_score,
                )
                return box
        except VertexGenerationError as exc:
            self._record_failure(run_id, "content_generation", exc, started, client_key)
            raise
        except Exception as exc:  # noqa: BLE001
            self._record_failure(run_id, "unknown", exc, started, client_key)
            raise

    def _record_failure(
        self,
        run_id: str,
        stage: str,
        exc: BaseException,
        started: float,
        client_key: str,
    ) -> None:
        category = classify_error(exc)
        duration_ms = int((time.perf_counter() - started) * 1000)
        log_event(
            stage,
            "generation failed",
            request_id=run_id,
            run_id=run_id,
            duration_ms=duration_ms,
            status="failure",
            error_type=category.value,
            error=redact(str(exc))[:300],
            level=40,
            category=client_log_id(client_key),
        )
        if self.store.postgres:
            try:
                self.store.postgres.record_system_error(
                    run_id=run_id,
                    stage=stage,
                    error_type=category.value,
                    message=redact(str(exc))[:500],
                )
            except Exception as db_exc:  # noqa: BLE001
                log_event(
                    "DATABASE",
                    "failed to store system error",
                    run_id=run_id,
                    status="failure",
                    error_type="database_error",
                    error=type(db_exc).__name__,
                    level=40,
                )
