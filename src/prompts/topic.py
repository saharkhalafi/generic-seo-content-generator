from __future__ import annotations

from src.config import SIMPLE_MAX_WORD_COUNT, SIMPLE_MIN_WORD_COUNT
from src.prompts import CORE_SYSTEM, input_brief
from src.prompts.versions import TOPIC_MAP_V2
from src.schemas import UserInput


def topic_map_system(user_input: UserInput | None = None) -> str:
    simple = bool(user_input and user_input.is_simple)
    length_rule = (
        f"recommended_word_count برای حالت ساده بین {SIMPLE_MIN_WORD_COUNT} تا {SIMPLE_MAX_WORD_COUNT}؛ معمولاً حدود ۵۰۰."
        if simple
        else "recommended_word_count بر اساس پیچیدگی موضوع بین ۷۰۰ تا ۱۵۰۰، نه برای پر کردن عدد کاربر."
    )
    extra = (
        """
حالت ساده: نقشه را جمع‌وجور نگه دار.
حداکثر ۲ تا ۳ موضوع heading_worthy با اولویت core.
FAQ و موضوعات فرعی راهنمای جامع را گسترش نده.
product_mention_policy معمولاً minimal یا supporting_section در پایان است.
"""
        if simple
        else ""
    )
    return CORE_SYSTEM + f"""

نسخه پرامپت: {TOPIC_MAP_V2}
این مرحله Topic Interpretation + Search Intent + Semantic Topic Map است.
محتوا، هدینگ و استراتژی نهایی را ننویس.

خروجی مدل ContentMap:
- core_topic: موضوع واقعی صفحه، نه نام برند
- topic_interpretation: اگر کلمه کلیدی مبهم است، مرتبط‌ترین خوانش را از بافت ورودی استنباط کن
- primary_search_intent و secondary_intents
- user_questions واقعی
- semantic_topics با priority و heading_worthy
- related_concepts
- industry_uses با USE / OPTIONAL / SKIP و دلیل
  پیش‌فرض OPTIONAL است. USE فقط اگر آن صنعت کاربرد/مسئله/مخاطب متمایزی می‌سازد.
  همهٔ صنایع ورودی را USE نکن.
- relevant_keyword_variants و relevant_entities فقط اگر به موضوع می‌خورند
- product_relevance: محصول چگونه (اگر اصلاً) به نیاز پاسخ می‌دهد
- product_mention_policy: معمولاً supporting_section یا minimal؛ brand_page فقط اگر نیت صریحاً برند/ناوبری است
- commercial_opportunities محدود و طبیعی
- {length_rule}
{extra}
اولویت نقشه: Topic، Search Intent، User Questions، Semantic Topics، Related Concepts.
صنایع و فرصت تجاری در اولویت پایین‌ترند.
"""


def topic_map_user(user_input: UserInput, existing_summary: str | None) -> str:
    existing = existing_summary or "محتوای فعلی ارائه نشده است."
    return f"""
ورودی:
{input_brief(user_input)}

خلاصه محتوای فعلی (متن کامل را تکرار نکن):
{existing}

کلمه کلیدی اصلی را کورکورانه موضوع ندان. از موضوع، کلمات فرعی، نیت، محتوای فعلی و WEBSITE CONTEXT، موضوع هسته را استخراج کن.
"""
