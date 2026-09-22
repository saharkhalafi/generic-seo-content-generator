from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Generator

STAGES = (
    "input_validation",
    "semantic_analysis",
    "seo_planning",
    "heading_planning",
    "content_generation",
    "validation",
    "revision",
    "finalization",
    "feature_image_generation",
)


@dataclass
class StageRecord:
    stage: str
    started_at: float
    ended_at: float | None = None
    duration_ms: int | None = None
    status: str = "success"
    model: str | None = None
    error_type: str | None = None
    error_message: str | None = None

    def finish(self, *, status: str = "success", model: str | None = None) -> None:
        self.ended_at = time.perf_counter()
        self.duration_ms = int((self.ended_at - self.started_at) * 1000)
        self.status = status
        self.model = model

    def to_dict(self) -> dict[str, Any]:
        from datetime import datetime, timezone

        started = datetime.fromtimestamp(self.started_at, tz=timezone.utc)
        ended = datetime.fromtimestamp(self.ended_at, tz=timezone.utc) if self.ended_at else None
        return {
            "stage": self.stage,
            "started_at": started,
            "ended_at": ended,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "model": self.model,
            "error_type": self.error_type,
            "error_message": self.error_message,
        }


@dataclass
class RunObservability:
    run_id: str
    stages: list[StageRecord] = field(default_factory=list)
    model_calls: list[dict[str, Any]] = field(default_factory=list)
    started_at: float = field(default_factory=time.perf_counter)

    @contextmanager
    def track_stage(self, stage: str, model: str | None = None) -> Generator[StageRecord, None, None]:
        record = StageRecord(stage=stage, started_at=time.perf_counter())
        try:
            yield record
            record.finish(status="success", model=model)
        except Exception as exc:
            record.finish(status="failure", model=model)
            record.error_message = str(exc)[:500]
            record.error_type = type(exc).__name__
            raise
        finally:
            self.stages.append(record)

    def total_latency_ms(self) -> int:
        return int((time.perf_counter() - self.started_at) * 1000)

    def add_model_call(self, call: dict[str, Any]) -> None:
        self.model_calls.append(call)
