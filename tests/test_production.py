from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.benchmark.runner import compare_metrics, detect_regression
from src.domain.errors import ErrorCategory, classify_error
from src.domain.hashes import input_hash
from src.pipeline import SeoBoxPipeline
from src.storage import Store
from tests.conftest import sample_input
from tests.test_pipeline_storage import FakeClient

BASELINE_PATH = Path(__file__).resolve().parents[1] / "data" / "baselines" / "clip_story_full.json"


def test_input_hash_stable():
    a = input_hash({"x": 1, "y": 2})
    b = input_hash({"y": 2, "x": 1})
    assert a == b


def test_classify_rate_limit():
    assert classify_error(Exception("429 rate limit exceeded")) == ErrorCategory.RATE_LIMIT


def test_compare_metrics_improvement():
    pipeline = {"seo_score": 93, "technical": 90}
    baseline = {"seo_score": 78, "technical": 80}
    cmp = compare_metrics(pipeline, baseline)
    assert cmp["seo_score"]["absolute_improvement"] == 15
    assert cmp["seo_score"]["relative_improvement_pct"] == pytest.approx(19.2, rel=0.1)


def test_detect_regression_flag():
    assert detect_regression({"seo_score": 70}, {"seo_score": 80}) == "REGRESSION"
    assert detect_regression({"seo_score": 90}, {"seo_score": 80}) == "IMPROVEMENT"


@pytest.mark.regression
def test_protected_pipeline_matches_baseline_score():
    """Regression guard: mocked pipeline must not drop below saved baseline."""
    if not BASELINE_PATH.exists():
        pytest.skip("Baseline file missing; run scripts/save_baseline.py")
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    baseline_score = int(baseline["seo_score"])
    store = Store(Path("data/regression_test.sqlite"))
    box = SeoBoxPipeline(FakeClient(), store=store).run(sample_input())
    assert box.seo_score >= baseline_score - 5, (
        f"SEO score regressed: {box.seo_score} vs baseline {baseline_score}"
    )
    assert box.h1
    assert box.status in {"excellent", "good", "needs_improvement"}


def test_exports_still_work():
    from src.exporters import seo_box_to_html_document, seo_box_to_json, seo_box_to_markdown
    from src.schemas import FinalSEOBox
    from tests.conftest import sample_article

    box = FinalSEOBox(
        category="استوری",
        primary_keyword="قالب استوری",
        h1="قالب استوری",
        content=sample_article().article_html,
        seo_score=90,
        status="excellent",
    )
    assert '"seo_score"' in seo_box_to_json(box)
    assert 'lang="fa"' in seo_box_to_html_document(box)
    assert "قالب استوری" in seo_box_to_markdown(box)
