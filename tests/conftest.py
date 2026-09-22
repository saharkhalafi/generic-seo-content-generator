from __future__ import annotations

import pytest

from src.schemas import Content, ContentMap, HeadingNode, HeadingPlan, Metadata, SearchIntent, SEOPlan, UserInput


def sample_input(**kwargs) -> UserInput:
    data = dict(
        website_name="نمونه",
        website_description="یک وب‌سایت نمونه برای آموزش ساخت استوری با قالب آماده است.",
        category_name="استوری",
        primary_keyword="قالب استوری اینستاگرام",
        secondary_keywords=["قالب استوری", "کلیپ استوری"],
        industries_professions=["فروشگاه", "پزشکی", "دندانپزشکی"],
        desired_word_count=1000,
        category_url="https://example.com/story/",
    )
    data.update(kwargs)
    if data.get("box_style") == "simple" and "desired_word_count" not in kwargs:
        data["desired_word_count"] = 500
    return UserInput(**data)


def _words(n: int, extra: str = "") -> str:
    unit = "ساخت ویدئو با قالب آماده برای معرفی محصول فروشگاه و خدمات پزشکی "
    tokens = (unit * (n // 8 + 4)).split()
    text = " ".join(tokens[:n])
    return f"{extra} {text}".strip()


def sample_html(keyword: str = "قالب استوری اینستاگرام", words: int = 850) -> str:
    body = _words(words, keyword)
    return f"""
    <article>
      <h1>{keyword}؛ ساخت استوری حرفه‌ای</h1>
      <p>{keyword} به کسب‌وکارها کمک می‌کند استوری اینستاگرام را با قالب آماده بسازند. {body[:400]}</p>
      <h2>چرا استوری برای معرفی محصول فروشگاه اهمیت دارد؟</h2>
      <p>{body}</p>
      <h2>قالب استوری برای چه کسب‌وکارهایی مناسب است؟</h2>
      <h3>قالب استوری برای فروشگاه‌ها</h3>
      <p>فروشگاه می‌تواند محصول را با قالب استوری معرفی کند. {body[:200]}</p>
      <h3>قالب استوری برای پزشکان و دندانپزشکی</h3>
      <p>پزشکی و دندانپزشکی می‌توانند خدمات را بدون طراحی از صفر معرفی کنند. {body[:200]}</p>
      <h2>با قالب آماده چگونه استوری بسازیم؟</h2>
      <p>متن، تصویر، لوگو و موزیک را ویرایش کنید، پیش‌نمایش ببینید و کیفیت 1080p را انتخاب کنید. {body[:300]}</p>
      <h2>سوالات متداول درباره قالب استوری اینستاگرام</h2>
      <h3>قالب استوری اینستاگرام برای معرفی چه خدماتی مناسب است؟</h3>
      <p>برای معرفی محصول فروشگاه و خدمات کلینیک مناسب است.</p>
    </article>
    """


def sample_topic_map() -> ContentMap:
    return ContentMap(
        core_topic="قالب استوری اینستاگرام",
        topic_interpretation="موضوع هسته ساخت استوری با قالب آماده است، نه صفحه برند.",
        category_type="story",
        primary_search_intent="Informational",
        secondary_intents=["Commercial"],
        user_questions=["چطور استوری حرفه‌ای بسازیم؟"],
        related_concepts=["قالب آماده", "شخصی‌سازی استوری"],
        industry_uses=[
            {"name": "فروشگاه", "relevance": "USE", "role": "use_case", "reason": "معرفی محصول"},
            {"name": "دندانپزشکی", "relevance": "OPTIONAL", "role": "audience"},
        ],
        product_mention_policy="supporting_section",
        recommended_word_count=900,
    )


def sample_plan() -> SEOPlan:
    return SEOPlan(
        category="استوری",
        category_type="story",
        primary_keyword="قالب استوری اینستاگرام",
        secondary_keywords=["قالب استوری", "کلیپ استوری"],
        keyword_variants=["استوری اینستاگرام", "کلیپ استوری اینستا"],
        semantic_keywords=["قالب آماده", "ساخت استوری"],
        industries=["فروشگاه"],
        professions=["پزشکی", "دندانپزشکی"],
        recommended_word_count=900,
        search_intent=SearchIntent(primary_intent="Commercial", questions_to_answer=["چطور استوری بسازیم؟"]),
        strategy_summary="تمرکز روی قالب آماده استوری",
    )


def sample_headings() -> HeadingPlan:
    return HeadingPlan(
        h1="قالب استوری اینستاگرام؛ ساخت استوری حرفه‌ای",
        headings=[
            HeadingNode(level="H1", text="قالب استوری اینستاگرام؛ ساخت استوری حرفه‌ای"),
            HeadingNode(level="H2", text="چرا استوری برای معرفی محصول فروشگاه اهمیت دارد؟"),
            HeadingNode(level="H2", text="قالب استوری برای چه کسب‌وکارهایی مناسب است؟"),
            HeadingNode(level="H3", text="قالب استوری برای فروشگاه‌ها", parent_h2="قالب استوری برای چه کسب‌وکارهایی مناسب است؟"),
            HeadingNode(level="H3", text="قالب استوری برای پزشکان و دندانپزشکی", parent_h2="قالب استوری برای چه کسب‌وکارهایی مناسب است؟"),
            HeadingNode(level="H2", text="با قالب آماده چگونه استوری بسازیم؟"),
            HeadingNode(level="H2", text="سوالات متداول درباره قالب استوری اینستاگرام"),
        ],
        architecture_rationale="معماری اختصاصی استوری",
        why_not_generic_template="به‌جای مزایا کلی، صنعت و ساخت با قالب آمده است.",
    )


def sample_article(**kwargs) -> Content:
    html = kwargs.pop("article_html", sample_html())
    article = Content(
        h1="قالب استوری اینستاگرام؛ ساخت استوری حرفه‌ای",
        article_html=html,
        article_markdown="# قالب استوری",
        introduction_html="<p>قالب استوری اینستاگرام به ساخت استوری با قالب آماده کمک می‌کند.</p>",
        cta="اگر به دنبال ساخت یک استوری حرفه‌ای بدون طراحی از صفر هستید، قالب آماده را در نمونه انتخاب کنید.",
        faqs=[
            {"question": "قالب استوری اینستاگرام برای معرفی چه خدماتی مناسب است؟", "answer": "برای فروشگاه و کلینیک."},
            {"question": "چطور قالب استوری را شخصی‌سازی کنیم؟", "answer": "متن، تصویر، لوگو و موزیک را عوض کنید."},
            {"question": "آیا پیش‌نمایش قبل از پرداخت وجود دارد؟", "answer": "بله."},
            {"question": "کیفیت خروجی چیست؟", "answer": "360p و 720p و 1080p."},
        ],
        metadata=Metadata(
            seo_title="قالب استوری اینستاگرام | ساخت استوری",
            meta_description="با قالب استوری اینستاگرام در نمونه، استوری فروشگاه یا کلینیک را بدون طراحی از صفر بسازید و پیش‌نمایش ببینید.",
            url_slug="https://example.com/story/",
            preserve_existing_url=True,
        ),
        internal_links=[
            {
                "anchor": "نمونه",
                "suggested_url": "https://example.com/",
                "topic": "خانه",
                "reason": "برند",
            }
        ],
        word_count=0,
    )
    for key, value in kwargs.items():
        setattr(article, key, value)
    return article


@pytest.fixture
def user_input() -> UserInput:
    return sample_input()
