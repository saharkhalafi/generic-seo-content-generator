from __future__ import annotations

import json

from src.product import product_guardrail_prompt, website_context_prompt
from src.schemas import UserInput


def dump(data: object) -> str:
    if hasattr(data, "model_dump"):
        data = data.model_dump()
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def input_brief(user_input: UserInput) -> str:
    payload = dump(
        {
            "website_name": user_input.website_name,
            "category_name": user_input.category_name,
            "primary_keyword": user_input.primary_keyword,
            "secondary_keywords": user_input.secondary_keywords,
            "industries_professions": user_input.industries_professions,
            "search_intents": user_input.search_intents,
            "target_audience": user_input.target_audience,
            "desired_word_count": user_input.desired_word_count,
            "category_url": user_input.category_url,
            "has_existing_content": bool(user_input.existing_content.strip()),
            "box_style": user_input.box_style,
        }
    )
    return website_context_prompt(user_input) + "\n\n" + payload + "\n\n" + box_style_block(user_input)


def box_style_block(user_input: UserInput) -> str:
    if user_input.is_simple:
        return """حالت SEO Box: ساده (صفحه دسته کوتاه، نه راهنمای جامع).

شکل مورد انتظار:
- H1 کوتاه، معمولاً نزدیک به نام موضوع/دسته؛ بدون برند.
- بعد از H1 یک یا دو پاراگراف معرفی روان بنویس؛ برای مقدمه هدینگ جدا نساز.
- فقط ۲ تا ۳ هدینگ H2. H3 تقریباً نساز مگر واقعاً لازم باشد.
- FAQ نساز و faqs را خالی بگذار.
- در صورت سود، حداکثر یک فهرست کوتاه گلوله‌ای.
- نام وب‌سایت فقط نزدیک پایان، به‌عنوان کمک برای انجام کار و فقط اگر با توضیح وب‌سایت هم‌خوان است، نه موضوع مقاله.
- لحن فارسی خوانا، مفید و مختصر؛ شبیه صفحه دسته واقعی، نه مقاله سئوی سنگین.

این شکل را کپی نکن: ضرورت / مزایا / انواع را برای هر دسته تکرار نکن.
بخش‌ها باید از موضوع همین صفحه بیایند. ادعای محصول، آمار و قابلیت اختراع‌شده ممنوع است."""
    return """حالت SEO Box: کامل (راهنمای جامع صفحه دسته).
FAQ چهار تا شش سوال مرتبط با همین موضوع. معماری عمیق‌تر در صورت نیاز موضوع مجاز است.
برند همچنان راه‌حل کمکی است، نه محور مقاله."""


def existing_summary_text(existing: object | None) -> str | None:
    if existing is None:
        return None
    if hasattr(existing, "model_dump"):
        data = existing.model_dump()
        compact = {
            "summary": data.get("summary", ""),
            "current_h1": data.get("current_h1", ""),
            "current_h2s": data.get("current_h2s", []),
            "useful_facts_to_preserve": data.get("useful_facts_to_preserve", []),
            "blocks": data.get("blocks", []),
            "missing_topics": data.get("missing_topics", []),
            "missing_search_intent": data.get("missing_search_intent", []),
            "seo_weaknesses": data.get("seo_weaknesses", []),
            "product_features": data.get("product_features", []),
            "repetitions": data.get("repetitions", []),
        }
        return dump(compact)
    return dump(existing)


def compact_topic_map(topic_map: object) -> str:
    data = topic_map.model_dump() if hasattr(topic_map, "model_dump") else dict(topic_map)
    topics = [
        item
        for item in data.get("semantic_topics", [])
        if item.get("heading_worthy") or item.get("priority") == "core"
    ][:6]
    industries = [item for item in data.get("industry_uses", []) if item.get("relevance") == "USE"][:6]
    return dump(
        {
            "core_topic": data.get("core_topic", ""),
            "topic_interpretation": data.get("topic_interpretation", ""),
            "primary_search_intent": data.get("primary_search_intent", ""),
            "user_questions": (data.get("user_questions") or [])[:6],
            "semantic_topics": topics,
            "related_concepts": (data.get("related_concepts") or [])[:6],
            "industry_uses": industries,
            "product_mention_policy": data.get("product_mention_policy", "supporting_section"),
            "product_relevance": data.get("product_relevance", ""),
            "commercial_opportunities": (data.get("commercial_opportunities") or [])[:4],
            "recommended_word_count": data.get("recommended_word_count"),
        }
    )


def compact_seo_plan(plan: object) -> str:
    data = plan.model_dump() if hasattr(plan, "model_dump") else dict(plan)
    return dump(
        {
            "primary_keyword": data.get("primary_keyword", ""),
            "secondary_keywords": (data.get("secondary_keywords") or [])[:8],
            "semantic_keywords": (data.get("semantic_keywords") or [])[:6],
            "strategy_summary": data.get("strategy_summary", ""),
            "commercial_placement": data.get("commercial_placement", ""),
            "heading_topics_from_map": data.get("heading_topics_from_map") or data.get("recommended_heading_topics") or [],
            "potential_faq_topics": (data.get("potential_faq_topics") or [])[:6],
            "user_questions": (data.get("user_questions") or [])[:6],
        }
    )


def compact_headings(plan: object) -> str:
    data = plan.model_dump() if hasattr(plan, "model_dump") else dict(plan)
    headings = [
        {"level": item.get("level"), "text": item.get("text"), "purpose": item.get("purpose", "")}
        for item in data.get("headings") or []
        if item.get("text")
    ]
    return dump({"h1": data.get("h1", ""), "headings": headings})


CORE_SYSTEM = f"""
تو متخصص سئوی فارسی برای صفحات دستهٔ موضوعی هستی، نه کپی‌رایتر برند.

اصل محوری:
موضوع و نیت جستجو محور مقاله‌اند. برند/محصول فقط راه‌حل کمکی است و فقط جایی می‌آید که به نیاز کاربر پاسخ بدهد.
مقاله باید حتی با حذف نام برند همچنان مفید بماند.

قواعد غیرقابل نقض:
- به فارسی طبیعی فکر کن و بنویس. محتوای انگلیسی را ترجمه نکن.
- استراتژی سئو را در مرحلهٔ تولید محتوا از نو تصمیم نگیر؛ از نقشهٔ موضوعی و معماری هدینگ پیروی کن.
- قالب هدینگ ثابت نساز و برای همهٔ دسته‌ها یک ساختار تکرار نکن.
- صنایع، مشاغل و موجودیت‌های ورودی فهرست کیورد نیستند؛ فقط اگر اطلاعات مفیدی می‌افزایند استفاده کن.
- کلمهٔ کلیدی عرضه‌شده را اگر نامرتبط یا غیرطبیعی است حذف کن.
- به چگالی کیورد بهینه نکن.
- آمار، حجم جستجو، سختی کیورد، قیمت، تضمین و قابلیت محصول را اختراع نکن.
- برای رسیدن به تعداد کلمات پرکننده ننویس و محتوای مفید را فقط برای عدد کوتاه نکن.
- جدول فقط وقتی مقایسه/داده واقعاً فهم را بهتر می‌کند.
- مقدمهٔ کلی، زبان تبلیغاتی اغراق‌آمیز و انتقال‌های مصنوعی ممنوع است.

{product_guardrail_prompt()}
""".strip()
