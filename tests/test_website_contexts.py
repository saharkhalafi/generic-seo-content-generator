"""The same pipeline must accept arbitrary websites and must not inject a fixed brand."""

from __future__ import annotations

import pytest

from src.image.feature_image import build_feature_image_prompt
from src.pipeline import SeoBoxPipeline
from src.prompts.content import content_system, content_user
from src.prompts.planning import planning_bundle_system, planning_bundle_user
from src.schemas import PlanningBundle, UserInput, WebsiteContext
from src.storage import Store
from tests.conftest import sample_article, sample_headings, sample_plan, sample_topic_map

FORBIDDEN_MARKERS = (
    "asanclip",
    "آسان‌کلیپ",
    "آسان کلیپ",
    "asanclip.ir",
    "logo motion",
    "instagram templates",
)

CONTEXTS = [
    {
        "key": "furniture",
        "website_name": "ExampleShop",
        "website_description": "یک فروشگاه آنلاین مبلمان و دکوراسیون منزل است که محصولات مدرن و مینیمال می‌فروشد.",
        "topic": "ایده‌های دکوراسیون اتاق خواب کوچک",
        "business_type": "فروشگاه مبلمان",
    },
    {
        "key": "saas",
        "website_name": "Planly",
        "website_description": "یک شرکت نرم‌افزار ابری برای مدیریت پروژه تیم‌های کوچک است.",
        "topic": "بهترین روش برنامه‌ریزی اسپرینت",
        "business_type": "نرم‌افزار ابری",
    },
    {
        "key": "restaurant",
        "website_name": "خانه کباب",
        "website_description": "یک رستوران ایرانی در تهران است که غذاهای خانگی و کباب سرو می‌کند.",
        "topic": "غذاهای مناسب مهمانی خانوادگی",
        "business_type": "رستوران",
    },
    {
        "key": "education",
        "website_name": "درس‌یار",
        "website_description": "یک وب‌سایت آموزشی است که دوره‌های آنلاین برنامه‌نویسی برای مبتدی‌ها منتشر می‌کند.",
        "topic": "یادگیری پایتون برای مبتدی‌ها",
        "business_type": "آموزش آنلاین",
    },
]


def _user(case: dict) -> UserInput:
    return UserInput(
        website_name=case["website_name"],
        website_description=case["website_description"],
        category_name=case["topic"],
        primary_keyword=case["topic"],
        box_style="simple",
        desired_word_count=500,
    )


def _assert_generic(text: str) -> None:
    lowered = text.lower()
    for marker in FORBIDDEN_MARKERS:
        assert marker.lower() not in lowered


@pytest.mark.parametrize("case", CONTEXTS, ids=[item["key"] for item in CONTEXTS])
def test_prompts_use_website_context_without_fixed_brand(case):
    user = _user(case)
    planning = planning_bundle_system(user) + "\n" + planning_bundle_user(user, None)
    content = content_system(user) + "\n" + content_user(
        user, "{}", "{}", "{}", None, user.desired_word_count
    )
    _assert_generic(planning)
    _assert_generic(content)
    assert case["website_description"] in planning
    assert case["website_description"] in content
    assert "business_type" in planning
    assert "products_or_services" in planning
    assert "WEBSITE CONTEXT" in planning


@pytest.mark.parametrize("case", CONTEXTS, ids=[item["key"] for item in CONTEXTS])
def test_pipeline_accepts_each_website_context(case, tmp_path):
    user = _user(case)
    captured: list[tuple[str, str, str]] = []

    class RecordingClient:
        last_model = "gemini-test"

        def generate_json(self, *, stage, system, user, schema, **kwargs):
            captured.append((stage, system, user))
            if schema is PlanningBundle:
                return PlanningBundle(
                    website_context=WebsiteContext(
                        website_name=case["website_name"],
                        website_description=case["website_description"],
                        business_type=case["business_type"],
                        audience="مخاطب همین وب‌سایت",
                        products_or_services=["خدمت یا محصول مرتبط"],
                        domain_context=case["business_type"],
                    ),
                    topic_map=sample_topic_map(),
                    seo_plan=sample_plan(),
                    heading_plan=sample_headings(),
                )
            article = sample_article()
            article.word_count = 900
            return article

    box = SeoBoxPipeline(RecordingClient(), store=Store(tmp_path / f"{case['key']}.sqlite")).run(user)
    assert box.website_name == case["website_name"]
    assert box.website_description == case["website_description"]
    assert box.primary_keyword == case["topic"]
    assert user.website_context is not None
    assert user.website_context.business_type == case["business_type"]
    assert captured
    for _stage, system, prompt_user in captured:
        _assert_generic(system)
        _assert_generic(prompt_user)
    content_prompts = [prompt for stage, _system, prompt in captured if stage == "content_generation"]
    assert content_prompts
    assert case["business_type"] in content_prompts[0]
    assert case["website_description"] in content_prompts[0]


def test_feature_image_prompt_follows_topic_not_a_fixed_brand():
    description = CONTEXTS[0]["website_description"]
    prompt = build_feature_image_prompt(
        "ایده‌های چیدمان تخت و نور در اتاق خواب کوچک.",
        category=CONTEXTS[0]["topic"],
        website_name=CONTEXTS[0]["website_name"],
        website_description=description,
    )
    _assert_generic(prompt)
    assert CONTEXTS[0]["website_name"] in prompt
    assert description in prompt
    assert CONTEXTS[0]["topic"] in prompt
    assert "advertisement" in prompt.lower()
