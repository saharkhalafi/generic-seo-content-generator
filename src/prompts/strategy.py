from __future__ import annotations

from src.prompts import CORE_SYSTEM, input_brief
from src.prompts.versions import EXISTING_CONTENT_V2, SEO_PLANNER_V2
from src.schemas import UserInput


def existing_content_system() -> str:
    return CORE_SYSTEM + f"""

نسخه پرامپت: {EXISTING_CONTENT_V2}
فقط تحلیل کن. بازنویسی کامل نکن.
KEEP / IMPROVE / REWRITE / REMOVE / ADD را مشخص کن.
حقایق مفید و اطلاعات تأییدشده در WEBSITE CONTEXT را حفظ کن.
شکاف نیت، شکاف معنایی، تکرار، ضعف معماری و سوالات بی‌پاسخ را پیدا کن.
summary باید فشرده باشد تا مراحل بعد متن کامل را دوباره نبینند.
"""


def existing_content_user(user_input: UserInput) -> str:
    return f"""
ورودی دسته:
{input_brief(user_input)}

محتوای فعلی صفحه:
\"\"\"{user_input.existing_content.strip()}\"\"\"
"""


def seo_planner_system(user_input: UserInput | None = None) -> str:
    extra = ""
    if user_input and user_input.is_simple:
        extra = """
حالت ساده: استراتژی را سبک نگه دار.
potential_faq_topics را خالی بگذار.
commercial_placement معمولاً پاراگراف پایانی است، نه H2 برند.
تعداد کلمات را در بازهٔ ساده نگه دار.
"""
    return CORE_SYSTEM + f"""

نسخه پرامپت: {SEO_PLANNER_V2}
این مرحله SEO Strategy است و باید از ContentMap پیروی کند، نه آن را عوض کند.
محتوا و هدینگ نهایی ننویس.

SEOPlan شامل تمایز exact / variant / semantic / entity / profession / industry / service / intent است.
بیشتر عبارات OPTIONAL باشند. MUST_USE فقط برای موضوع هسته.
NOT_RELEVANT برای هر عبارت نامرتبط.
heading_topics_from_map را از semantic_topics با heading_worthy بساز.
commercial_placement مشخص کند برند حداکثر در کدام بخش کمکی بیاید (معمولاً یک بخش پایانی یا CTA).
recommended_word_count را از ContentMap بگیر مگر پیچیدگی خلاف آن را نشان دهد.
{extra}
"""


def seo_planner_user(user_input: UserInput, topic_map_json: str, existing_summary: str | None) -> str:
    existing = existing_summary or "محتوای فعلی ارائه نشده است."
    return f"""
ورودی:
{input_brief(user_input)}

ContentMap (منبع حقیقت موضوع و نیت):
{topic_map_json}

خلاصه محتوای فعلی:
{existing}
"""
