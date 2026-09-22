from src.exporters import seo_box_to_html_document, seo_box_to_json
from src.pipeline import SeoBoxPipeline
from src.schemas import (
    Content,
    ContentMap,
    ExistingContentAnalysis,
    HeadingPlan,
    LLMQualitativeReview,
    PlanningBundle,
    SEOPlan,
)
from src.storage import Store
from tests.conftest import sample_article, sample_headings, sample_input, sample_plan, sample_topic_map


class FakeClient:
    last_model = "gemini-2.5-flash"

    def generate_json(self, *, stage, schema, **kwargs):
        if schema is PlanningBundle:
            return PlanningBundle(
                topic_map=sample_topic_map(),
                seo_plan=sample_plan(),
                heading_plan=sample_headings(),
            )
        if schema is ExistingContentAnalysis:
            return ExistingContentAnalysis(summary="حفظ معرفی استوری و مسیر ساخت با قالب.", current_h1="قالب استوری")
        if schema is ContentMap:
            return sample_topic_map()
        if schema is SEOPlan:
            return sample_plan()
        if schema is HeadingPlan:
            return sample_headings()
        if schema is Content:
            article = sample_article()
            article.word_count = 900
            return article
        if schema is LLMQualitativeReview:
            return LLMQualitativeReview(summary="کیفی قابل قبول", intent_score=88, content_quality_score=86, persian_score=84)
        return schema()


def test_pipeline_mocked_respects_locked_headings(tmp_path):
    store = Store(tmp_path / "test.sqlite")
    pipeline = SeoBoxPipeline(FakeClient(), store=store)
    locked = sample_headings()
    locked.h1 = "هدینگ قفل‌شده کاربر"
    locked.headings[0].text = "هدینگ قفل‌شده کاربر"
    user = sample_input(existing_content="متن فعلی استوری")
    from src.schemas import ManualLocks, RunOptions

    box = pipeline.run(
        user,
        RunOptions(locks=ManualLocks(headings=True), existing_headings=locked, skip_existing_analysis=False),
    )
    assert box.h1 == "هدینگ قفل‌شده کاربر" or any(item["text"] == "هدینگ قفل‌شده کاربر" for item in box.headings)
    assert box.revision_count <= 1
    assert "meta_title" in box.export_payload()
    html = seo_box_to_html_document(box)
    assert 'lang="fa"' in html and 'dir="rtl"' in html
    assert '"seo_score"' in seo_box_to_json(box)


def test_pipeline_max_one_revision(tmp_path, monkeypatch):
    store = Store(tmp_path / "rev.sqlite")
    calls = {"revision": 0}

    class RevisingClient(FakeClient):
        def generate_json(self, *, stage, schema, **kwargs):
            if schema is Content:
                if stage == "revision":
                    calls["revision"] += 1
                article = sample_article(article_html="<h1>x</h1><p>کوتاه</p>")
                article.word_count = 10
                return article
            return super().generate_json(stage=stage, schema=schema, **kwargs)

    pipeline = SeoBoxPipeline(RevisingClient(), store=store)
    box = pipeline.run(sample_input())
    assert calls["revision"] <= 1
    assert box.revision_count <= 1
    assert box.status in {"human_review_required", "revision_required", "needs_improvement", "good", "excellent"}


def test_storage_cannibalization(tmp_path):
    store = Store(tmp_path / "c.sqlite")
    from src.schemas import FinalSEOBox

    first = FinalSEOBox(category="استوری", primary_keyword="قالب استوری اینستاگرام", seo_score=88, status="good")
    store.save_run(sample_input(), first, "gemini-2.5-flash", {"SEO_PLANNER": "SEO_PLANNER_V1"})
    warnings = store.cannibalization_warnings("دندانپزشکی", "قالب استوری اینستاگرام", 0.7)
    assert warnings
    assert "استوری" in warnings[0].other_category
