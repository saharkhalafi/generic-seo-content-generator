import pytest
from pydantic import ValidationError

from src.schemas import FinalSEOBox, SEOPlan, UserInput
from tests.conftest import sample_input


def test_rejects_short_word_count():
    with pytest.raises(ValidationError):
        sample_input(desired_word_count=500)


def test_simple_style_accepts_shorter_word_count():
    user = sample_input(box_style="simple", desired_word_count=500)
    assert user.is_simple
    assert user.desired_word_count == 500


def test_simple_style_defaults_word_count():
    user = UserInput(
        website_description="یک وب‌سایت نمونه برای معرفی قالب استوری است.",
        category_name="استوری",
        primary_keyword="قالب استوری",
        secondary_keywords=["کلیپ استوری"],
        industries_professions=["فروشگاه"],
        box_style="simple",
    )
    assert user.desired_word_count == 500


def test_rejects_long_word_count():
    with pytest.raises(ValidationError):
        sample_input(desired_word_count=2000)


def test_rejects_empty_primary_keyword():
    with pytest.raises(ValidationError):
        UserInput(category_name="استوری", primary_keyword="  ")


def test_accepts_valid_input(user_input):
    assert user_input.primary_keyword == "قالب استوری اینستاگرام"


def test_seoplan_and_final_box_schema():
    plan = SEOPlan(primary_keyword="قالب استوری اینستاگرام", category="استوری")
    box = FinalSEOBox(
        category="استوری",
        primary_keyword=plan.primary_keyword,
        seo_score=91,
        status="excellent",
    )
    payload = box.export_payload()
    assert set(payload) >= {
        "category",
        "primary_keyword",
        "meta_title",
        "h1",
        "content",
        "faq",
        "seo_score",
        "validation",
        "revision_count",
        "status",
    }
    FinalSEOBox.model_validate(box.model_dump())
