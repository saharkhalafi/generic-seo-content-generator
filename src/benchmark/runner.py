from __future__ import annotations

import time
import uuid
from typing import Any

from src.benchmark.baseline import BASELINE_PROMPT_V1, BASELINE_SYSTEM, baseline_user_prompt
from src.benchmark.gold_set import load_case
from src.benchmark.schemas import BenchmarkCase
from src.llm import VertexClient
from src.orchestration.runner import ProductionSeoOrchestrator
from src.persistence.factory import get_run_store
from src.schemas import Content, FinalSEOBox, HeadingNode, HeadingPlan, RunOptions, SearchIntent, SEOPlan
from src.scoring import evaluate


def _baseline_evaluation_context(case: BenchmarkCase):
    user_input = case.to_user_input()
    plan = SEOPlan(
        category=case.category,
        category_type=case.category_type,
        primary_keyword=case.primary_keyword,
        secondary_keywords=case.secondary_keywords,
        search_intent=SearchIntent(primary_intent=case.search_intent[0] if case.search_intent else "Commercial"),
    )
    headings = HeadingPlan(
        h1=case.primary_keyword,
        headings=[HeadingNode(level="H1", text=case.primary_keyword)],
    )
    return user_input, plan, headings


def extract_metrics(box: FinalSEOBox, *, latency_ms: int, model_calls: int = 1) -> dict[str, Any]:
    validation = box.validation or {}
    cats = validation.get("category_scores") or {}
    checks = {c.get("code"): c for c in validation.get("checks") or []}
    return {
        "seo_score": box.seo_score,
        "technical": cats.get("technical", 0),
        "keyword": cats.get("keyword", 0),
        "intent": cats.get("intent", 0),
        "content": cats.get("content", 0),
        "heading": cats.get("heading", 0),
        "persian": cats.get("persian", 0),
        "product": cats.get("product", 0),
        "trust": cats.get("trust", 0),
        "word_count": box.word_count,
        "revision_count": box.revision_count,
        "latency_ms": latency_ms,
        "model_calls": model_calls,
        "failed_checks": validation.get("failed_checks") or [],
        "hard_fails": validation.get("hard_fails") or [],
        "keyword_stuffing": _check_status(checks, "keyword_stuffing"),
        "brand_overuse": _check_status(checks, "brand_overuse"),
        "forbidden_claim": _check_status(checks, "forbidden_claim"),
        "faq_count": len(box.faq),
    }


def _check_status(checks: dict, code: str) -> str:
    item = checks.get(code)
    return item.get("status", "PASS") if item else "PASS"


def compare_metrics(pipeline: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    comparison: dict[str, Any] = {}
    for key in ("seo_score", "technical", "keyword", "intent", "content", "heading", "persian", "product", "trust"):
        p = pipeline.get(key, 0)
        b = baseline.get(key, 0)
        if isinstance(p, (int, float)) and isinstance(b, (int, float)):
            delta = p - b
            rel = (delta / b * 100) if b else None
            comparison[key] = {
                "pipeline": p,
                "baseline": b,
                "absolute_improvement": round(delta, 2),
                "relative_improvement_pct": round(rel, 1) if rel is not None else None,
            }
    comparison["latency_ms"] = {
        "pipeline": pipeline.get("latency_ms"),
        "baseline": baseline.get("latency_ms"),
        "absolute_improvement": (pipeline.get("latency_ms") or 0) - (baseline.get("latency_ms") or 0),
    }
    comparison["model_calls"] = {
        "pipeline": pipeline.get("model_calls"),
        "baseline": baseline.get("model_calls"),
    }
    return comparison


def detect_regression(
    pipeline_metrics: dict[str, Any],
    baseline_metrics: dict[str, Any],
    *,
    previous_pipeline: dict[str, Any] | None = None,
    score_threshold: float = 3.0,
) -> str:
    if previous_pipeline:
        delta = pipeline_metrics.get("seo_score", 0) - previous_pipeline.get("seo_score", 0)
        if delta <= -score_threshold:
            return "REGRESSION"
        if delta >= score_threshold:
            return "IMPROVEMENT"
        return "NO_SIGNIFICANT_CHANGE"
    delta = pipeline_metrics.get("seo_score", 0) - baseline_metrics.get("seo_score", 0)
    if delta >= 5:
        return "IMPROVEMENT"
    if delta <= -5:
        return "REGRESSION"
    return "NO_SIGNIFICANT_CHANGE"


def run_pipeline_benchmark(client: VertexClient, case: BenchmarkCase) -> tuple[FinalSEOBox, dict[str, Any]]:
    started = time.perf_counter()
    orchestrator = ProductionSeoOrchestrator(client=client, store=get_run_store())
    box = orchestrator.run(case.to_user_input(), RunOptions())
    latency = int((time.perf_counter() - started) * 1000)
    metrics = extract_metrics(box, latency_ms=latency, model_calls=2)
    return box, metrics


def run_baseline_benchmark(client: VertexClient, case: BenchmarkCase) -> tuple[Content, dict[str, Any]]:
    started = time.perf_counter()
    article = client.generate_json(
        stage="baseline_seo",
        system=BASELINE_SYSTEM,
        user=baseline_user_prompt(case.model_dump_json()),
        schema=Content,
        kind="content",
        temperature=0.55,
    )
    latency = int((time.perf_counter() - started) * 1000)
    user_input = case.to_user_input()
    plan, headings = _baseline_evaluation_context(case)[1:]
    validation = evaluate(
        user_input=user_input,
        plan=plan,
        headings=headings,
        article=article,
        content_map=None,
    )
    box = FinalSEOBox(
        category=case.category,
        primary_keyword=case.primary_keyword,
        h1=article.h1,
        content=article.article_html,
        faq=article.faqs,
        word_count=article.word_count,
        seo_score=validation.overall_score,
        validation=validation.model_dump(),
        status="good",
        box_style=case.box_style,  # type: ignore[arg-type]
    )
    metrics = extract_metrics(box, latency_ms=latency, model_calls=1)
    metrics["prompt_version"] = BASELINE_PROMPT_V1
    return article, metrics


def run_case_comparison(client: VertexClient, case_key: str) -> dict[str, Any]:
    case = load_case(case_key)
    if not case:
        raise ValueError(f"Benchmark case not found: {case_key}")
    _, pipeline_metrics = run_pipeline_benchmark(client, case)
    _, baseline_metrics = run_baseline_benchmark(client, case)
    comparison = compare_metrics(pipeline_metrics, baseline_metrics)
    flag = detect_regression(pipeline_metrics, baseline_metrics)
    benchmark_id = uuid.uuid4().hex
    store = get_run_store()
    if store.postgres:
        store.postgres.save_benchmark_run(
            benchmark_id=benchmark_id,
            case_key=case_key,
            mode="pipeline",
            run_id=None,
            metrics=pipeline_metrics,
            comparison=comparison,
            regression_flag=flag,
        )
        store.postgres.save_benchmark_run(
            benchmark_id=f"{benchmark_id}-baseline",
            case_key=case_key,
            mode="baseline",
            run_id=None,
            metrics=baseline_metrics,
            comparison=comparison,
            regression_flag=flag,
        )
    return {
        "benchmark_id": benchmark_id,
        "case_key": case_key,
        "pipeline_metrics": pipeline_metrics,
        "baseline_metrics": baseline_metrics,
        "comparison": comparison,
        "regression_flag": flag,
    }
