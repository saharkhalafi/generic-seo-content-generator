from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.config import PIPELINE_VERSION, VALIDATION_VERSION, get_settings
from src.domain.errors import redact
from src.domain.hashes import content_hash, input_hash
from src.logutil import log_event
from src.persian import normalize_fa, similarity
from src.persistence.database import session_scope
from src.persistence.models import (
    Category,
    FeatureImageRun,
    HeadingPlanRecord,
    KeywordRegistry,
    ModelCall,
    PipelineStage,
    Project,
    SeoInput,
    SeoOutput,
    SeoPlanRecord,
    SeoRun,
    SystemError,
    ValidationCheck,
    ValidationResult,
)
from src.retrying import call_with_retry, is_transient_db_error
from src.schemas import CannibalizationWarning, FinalSEOBox, UserInput


def new_run_id() -> str:
    return uuid.uuid4().hex


def _retry_write(fn):
    def wrapper(*args, **kwargs):
        return call_with_retry(
            lambda: fn(*args, **kwargs),
            is_retryable=is_transient_db_error,
            max_attempts=get_settings().db_max_attempts,
            base_delay=0.25,
            max_delay=2,
        )

    return wrapper


class PostgresRunRepository:
    """PostgreSQL persistence — does not replace SQLite Store; used when DATABASE_URL is set."""

    def cannibalization_warnings(
        self, category_name: str, primary_keyword: str, threshold: float, website_name: str = ""
    ) -> list[CannibalizationWarning]:
        needle = normalize_fa(primary_keyword)
        warnings: list[CannibalizationWarning] = []
        site = website_name.strip()
        try:
            with session_scope() as session:
                project_id = None
                if site:
                    project = session.scalar(select(Project).where(Project.name == site).limit(1))
                    project_id = project.id if project else None
                rows = session.scalars(select(KeywordRegistry)).all()
                for row in rows:
                    if site:
                        category = session.get(Category, row.category_id) if row.category_id else None
                        if project_id is None or category is None or category.project_id != project_id:
                            continue
                    if normalize_fa(row.category_name) == normalize_fa(category_name):
                        continue
                    score = similarity(needle, row.primary_normalized)
                    if score >= threshold:
                        warnings.append(
                            CannibalizationWarning(
                                other_category=row.category_name,
                                other_keyword=row.primary_keyword,
                                similarity=round(score, 3),
                                message=(
                                    f"کلمه کلیدی «{primary_keyword}» به «{row.primary_keyword}» "
                                    f"در دسته «{row.category_name}» شبیه است (شباهت {score:.2f})."
                                ),
                            )
                        )
        except Exception as exc:  # noqa: BLE001
            log_event(
                "DATABASE",
                "cannibalization lookup failed",
                status="failure",
                error_type="database_error",
                error=redact(str(exc))[:200],
                level=30,
            )
            return []
        return warnings

    def count_runs_today(self) -> int:
        start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        with session_scope() as session:
            value = session.scalar(
                select(func.count()).select_from(SeoRun).where(SeoRun.created_at >= start)
            )
            return int(value or 0)

    @_retry_write
    def save_run(
        self,
        *,
        run_id: str,
        user_input: UserInput,
        box: FinalSEOBox,
        model: str,
        prompt_versions: dict[str, str],
        latency_ms: int | None = None,
        topic_map: dict[str, Any] | None = None,
        heading_plan: dict[str, Any] | None = None,
        model_calls: list[dict[str, Any]] | None = None,
        stages: list[dict[str, Any]] | None = None,
    ) -> str:
        now = datetime.now(timezone.utc)
        inp_hash = input_hash(user_input.model_dump())
        out_hash = content_hash(box.content or "")
        with session_scope() as session:
            category = self._upsert_category(session, user_input, box)
            run = SeoRun(
                run_id=run_id,
                category_id=category.id,
                model=model,
                pipeline_version=PIPELINE_VERSION,
                prompt_versions=prompt_versions,
                input_hash=inp_hash,
                output_hash=out_hash,
                validation_version=VALIDATION_VERSION,
                seo_score=box.seo_score,
                revision_count=box.revision_count,
                status=box.status,
                box_style=box.box_style,
                latency_ms=latency_ms,
                completed_at=now,
            )
            session.add(run)
            session.add(
                SeoInput(
                    run_id=run_id,
                    raw_input=user_input.model_dump(),
                    normalized_input=user_input.model_dump(),
                )
            )
            session.add(
                SeoPlanRecord(
                    run_id=run_id,
                    plan_json=box.seo_strategy or {},
                    topic_map_json=topic_map or box.topic_map or {},
                )
            )
            session.add(
                HeadingPlanRecord(
                    run_id=run_id,
                    heading_plan_json={"h1": box.h1, "headings": box.headings},
                )
            )
            session.add(SeoOutput(run_id=run_id, output_json=box.export_payload()))
            session.add(
                ValidationResult(
                    run_id=run_id,
                    overall_score=box.seo_score,
                    validation_json=box.validation or {},
                )
            )
            for check in (box.validation or {}).get("checks") or []:
                session.add(
                    ValidationCheck(
                        run_id=run_id,
                        code=check.get("code", ""),
                        category=check.get("category", ""),
                        status=check.get("status", ""),
                        message=check.get("message", ""),
                        hard_fail=bool(check.get("hard_fail")),
                    )
                )
            self._upsert_keyword_registry(session, category, user_input, box)
            for stage in stages or []:
                session.add(PipelineStage(run_id=run_id, **stage))
            for call in model_calls or []:
                payload = dict(call)
                if isinstance(payload.get("started_at"), (int, float)):
                    payload["started_at"] = datetime.fromtimestamp(payload["started_at"], tz=timezone.utc)
                session.add(ModelCall(run_id=run_id, **payload))
            session.flush()
        return run_id

    @_retry_write
    def record_system_error(
        self,
        *,
        run_id: str | None,
        stage: str,
        error_type: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        with session_scope() as session:
            session.add(
                SystemError(
                    run_id=run_id,
                    stage=stage,
                    error_type=error_type,
                    message=message,
                    details_json=details,
                )
            )

    @_retry_write
    def record_feature_image_run(
        self,
        *,
        seo_run_id: str | None,
        input_summary: str,
        model: str,
        output_path: str | None,
        status: str,
        duration_ms: int | None,
        error_message: str | None = None,
    ) -> None:
        with session_scope() as session:
            session.add(
                FeatureImageRun(
                    seo_run_id=seo_run_id,
                    input_summary=input_summary[:2000],
                    model=model,
                    output_path=output_path,
                    status=status,
                    duration_ms=duration_ms,
                    error_message=error_message,
                )
            )

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with session_scope() as session:
            rows = session.scalars(
                select(SeoRun).order_by(SeoRun.created_at.desc()).limit(limit)
            ).all()
            return [
                {
                    "run_id": row.run_id,
                    "created_at": row.created_at.isoformat() if row.created_at else "",
                    "seo_score": row.seo_score,
                    "status": row.status,
                    "revision_count": row.revision_count,
                    "model": row.model,
                    "pipeline_version": row.pipeline_version,
                    "latency_ms": row.latency_ms,
                    "box_style": row.box_style,
                }
                for row in rows
            ]

    def get_run_detail(self, run_id: str) -> dict[str, Any] | None:
        with session_scope() as session:
            run = session.scalar(select(SeoRun).where(SeoRun.run_id == run_id))
            if not run:
                return None
            seo_input = session.scalar(select(SeoInput).where(SeoInput.run_id == run_id))
            output = session.scalar(select(SeoOutput).where(SeoOutput.run_id == run_id))
            validation = session.scalar(select(ValidationResult).where(ValidationResult.run_id == run_id))
            plan = session.scalar(select(SeoPlanRecord).where(SeoPlanRecord.run_id == run_id))
            headings = session.scalar(select(HeadingPlanRecord).where(HeadingPlanRecord.run_id == run_id))
            checks = session.scalars(select(ValidationCheck).where(ValidationCheck.run_id == run_id)).all()
            stages = session.scalars(select(PipelineStage).where(PipelineStage.run_id == run_id)).all()
            calls = session.scalars(select(ModelCall).where(ModelCall.run_id == run_id)).all()
            images = session.scalars(select(FeatureImageRun).where(FeatureImageRun.seo_run_id == run_id)).all()
            return {
                "run": {
                    "run_id": run.run_id,
                    "seo_score": run.seo_score,
                    "status": run.status,
                    "model": run.model,
                    "pipeline_version": run.pipeline_version,
                    "prompt_versions": run.prompt_versions,
                    "input_hash": run.input_hash,
                    "output_hash": run.output_hash,
                    "latency_ms": run.latency_ms,
                    "revision_count": run.revision_count,
                    "created_at": run.created_at.isoformat() if run.created_at else "",
                },
                "input": seo_input.raw_input if seo_input else {},
                "output": output.output_json if output else {},
                "validation": validation.validation_json if validation else {},
                "seo_plan": plan.plan_json if plan else {},
                "topic_map": plan.topic_map_json if plan else {},
                "headings": headings.heading_plan_json if headings else {},
                "checks": [
                    {
                        "code": c.code,
                        "status": c.status,
                        "message": c.message,
                        "hard_fail": c.hard_fail,
                    }
                    for c in checks
                ],
                "stages": [
                    {
                        "stage": s.stage,
                        "duration_ms": s.duration_ms,
                        "status": s.status,
                    }
                    for s in stages
                ],
                "model_calls": [
                    {
                        "operation": m.operation,
                        "model": m.model,
                        "duration_ms": m.duration_ms,
                        "status": m.status,
                    }
                    for m in calls
                ],
                "feature_images": [
                    {
                        "status": i.status,
                        "output_path": i.output_path,
                        "model": i.model,
                    }
                    for i in images
                ],
            }

    def observability_summary(self) -> dict[str, Any]:
        with session_scope() as session:
            runs = session.scalars(select(SeoRun)).all()
            if not runs:
                return {
                    "total_runs": 0,
                    "successful_runs": 0,
                    "failed_runs": 0,
                    "avg_latency_ms": 0,
                    "avg_seo_score": 0,
                    "avg_revision_count": 0,
                    "validation_failure_rate": 0,
                    "model_usage": {},
                    "recent_errors": [],
                    "score_distribution": {},
                    "rate_limit_hits": 0,
                    "database_failures": 0,
                    "generation_failures": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                }
            total = len(runs)
            successful = sum(1 for r in runs if r.status in {"excellent", "good"})
            failed = sum(1 for r in runs if r.status not in {"excellent", "good", "needs_improvement"})
            latencies = [r.latency_ms for r in runs if r.latency_ms]
            scores = [r.seo_score for r in runs]
            revisions = [r.revision_count for r in runs]
            model_usage: dict[str, int] = {}
            for r in runs:
                model_usage[r.model] = model_usage.get(r.model, 0) + 1
            score_buckets = {"90+": 0, "80-89": 0, "70-79": 0, "<70": 0}
            for s in scores:
                if s >= 90:
                    score_buckets["90+"] += 1
                elif s >= 80:
                    score_buckets["80-89"] += 1
                elif s >= 70:
                    score_buckets["70-79"] += 1
                else:
                    score_buckets["<70"] += 1
            errors = session.scalars(
                select(SystemError).order_by(SystemError.created_at.desc()).limit(10)
            ).all()
            fail_checks = session.scalars(
                select(ValidationCheck).where(ValidationCheck.status == "FAIL")
            ).all()
            all_checks = session.scalars(select(ValidationCheck)).all()
            fail_rate = (len(fail_checks) / len(all_checks)) if all_checks else 0
            token_input, token_output = session.execute(
                select(func.coalesce(func.sum(ModelCall.input_tokens), 0), func.coalesce(func.sum(ModelCall.output_tokens), 0))
            ).one()
            def _error_count(error_type: str) -> int:
                value = session.scalar(
                    select(func.count()).select_from(SystemError).where(SystemError.error_type == error_type)
                )
                return int(value or 0)

            return {
                "total_runs": total,
                "successful_runs": successful,
                "failed_runs": failed,
                "avg_latency_ms": round(sum(latencies) / len(latencies)) if latencies else 0,
                "avg_seo_score": round(sum(scores) / len(scores), 1) if scores else 0,
                "avg_revision_count": round(sum(revisions) / len(revisions), 2) if revisions else 0,
                "validation_failure_rate": round(fail_rate, 3),
                "model_usage": model_usage,
                "recent_errors": [
                    {"stage": e.stage, "error_type": e.error_type, "message": redact(e.message)[:200]}
                    for e in errors
                ],
                "score_distribution": score_buckets,
                "rate_limit_hits": _error_count("rate_limit"),
                "database_failures": _error_count("database_error"),
                "generation_failures": _error_count("generation_error") + _error_count("timeout"),
                "input_tokens": int(token_input or 0),
                "output_tokens": int(token_output or 0),
            }

    def save_benchmark_run(
        self,
        *,
        benchmark_id: str,
        case_key: str,
        mode: str,
        run_id: str | None,
        metrics: dict[str, Any],
        comparison: dict[str, Any] | None = None,
        regression_flag: str | None = None,
    ) -> None:
        from src.persistence.models import BenchmarkRun

        with session_scope() as session:
            session.add(
                BenchmarkRun(
                    benchmark_id=benchmark_id,
                    case_key=case_key,
                    mode=mode,
                    run_id=run_id,
                    metrics_json=metrics,
                    comparison_json=comparison,
                    regression_flag=regression_flag,
                )
            )

    def save_human_evaluation(
        self,
        *,
        run_id: str,
        case_key: str | None,
        reviewer: str,
        scores: dict[str, int | None],
        notes: str = "",
    ) -> None:
        from src.persistence.models import HumanEvaluation

        with session_scope() as session:
            session.add(
                HumanEvaluation(
                    run_id=run_id,
                    case_key=case_key,
                    reviewer=reviewer,
                    usefulness=scores.get("usefulness"),
                    intent_satisfaction=scores.get("intent_satisfaction"),
                    persian_naturalness=scores.get("persian_naturalness"),
                    factual_accuracy=scores.get("factual_accuracy"),
                    heading_quality=scores.get("heading_quality"),
                    commercial_usefulness=scores.get("commercial_usefulness"),
                    overall_quality=scores.get("overall_quality"),
                    notes=notes,
                )
            )

    def human_automation_correlation(self) -> dict[str, Any] | None:
        from src.persistence.models import HumanEvaluation

        with session_scope() as session:
            evals = session.scalars(select(HumanEvaluation)).all()
            if len(evals) < 5:
                return None
            pairs: list[tuple[int, int]] = []
            for ev in evals:
                run = session.scalar(select(SeoRun).where(SeoRun.run_id == ev.run_id))
                if run and ev.overall_quality is not None:
                    pairs.append((ev.overall_quality, run.seo_score))
            if len(pairs) < 5:
                return None
            human_avg = sum(p[0] for p in pairs) / len(pairs)
            auto_avg = sum(p[1] for p in pairs) / len(pairs)
            return {
                "sample_size": len(pairs),
                "avg_human_overall": round(human_avg, 2),
                "avg_automated_seo_score": round(auto_avg, 2),
                "note": "Informal correlation only; not statistical significance.",
            }

    def _upsert_project(self, session: Session, user_input: UserInput) -> Project:
        name = (user_input.website_name or user_input.website_description[:80] or "local-site").strip()
        existing = session.scalar(select(Project).where(Project.name == name).limit(1))
        if existing:
            return existing
        project = Project(name=name)
        session.add(project)
        session.flush()
        return project

    def _upsert_category(self, session: Session, user_input: UserInput, box: FinalSEOBox) -> Category:
        slug = user_input.category_url or box.slug or ""
        project = self._upsert_project(session, user_input)
        existing = session.scalar(
            select(Category)
            .where(Category.name == user_input.category_name, Category.project_id == project.id)
            .limit(1)
        )
        if existing:
            existing.url = user_input.category_url or existing.url
            existing.category_type = box.category_type or existing.category_type
            existing.slug = slug or existing.slug
            existing.project_id = project.id
            existing.updated_at = datetime.now(timezone.utc)
            return existing
        category = Category(
            project_id=project.id,
            name=user_input.category_name,
            category_type=box.category_type,
            slug=slug,
            url=user_input.category_url,
        )
        session.add(category)
        session.flush()
        return category

    def _upsert_keyword_registry(
        self,
        session: Session,
        category: Category,
        user_input: UserInput,
        box: FinalSEOBox,
    ) -> None:
        existing = session.scalar(
            select(KeywordRegistry)
            .where(KeywordRegistry.category_id == category.id)
            .limit(1)
        )
        if existing:
            existing.primary_keyword = user_input.primary_keyword
            existing.primary_normalized = normalize_fa(user_input.primary_keyword)
            existing.secondary_keywords = user_input.secondary_keywords
            existing.semantic_keywords = box.semantic_keywords
            existing.slug = category.slug
            existing.updated_at = datetime.now(timezone.utc)
            return
        session.add(
            KeywordRegistry(
                category_id=category.id,
                category_name=user_input.category_name,
                primary_keyword=user_input.primary_keyword,
                primary_normalized=normalize_fa(user_input.primary_keyword),
                secondary_keywords=user_input.secondary_keywords,
                semantic_keywords=box.semantic_keywords,
                slug=category.slug,
            )
        )
