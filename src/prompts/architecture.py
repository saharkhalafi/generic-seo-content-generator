from __future__ import annotations

from src.prompts import CORE_SYSTEM, input_brief
from src.prompts.versions import HEADING_PLANNER_V2
from src.schemas import UserInput


def heading_planner_system(user_input: UserInput | None = None) -> str:
    simple = bool(user_input and user_input.is_simple)
    extra = (
        """
حالت ساده: معماری صفحه دسته کوتاه.
- H1 کوتاه و موضوع‌محور.
- فقط ۲ تا ۳ H2.
- H3 نساز مگر اجتناب‌ناپذیر باشد.
- هدینگ FAQ نساز.
- مقدمه جدا هدینگ نمی‌خواهد.
- قالب ثابت ضرورت/مزایا/انواع را روی هر دسته کپی نکن؛ بخش‌ها از موضوع همین صفحه بیایند.
"""
        if simple
        else """
از چیدن پشت‌سرهم تعریف + مزایا + انواع + نحوه استفاده به‌عنوان معماری پیش‌فرض پرهیز کن.
"""
    )
    return CORE_SYSTEM + f"""

نسخه پرامپت: {HEADING_PLANNER_V2}
برنامه‌ریز معماری پویای هدینگ هستی. محتوا ننویس.
هدینگ‌ها را از ContentMap و SEOPlan بساز، نه از قالب ازپیش‌تعیین‌شده.
فقط موضوعاتی که در ContentMap با heading_worthy مشخص شده‌اند H2/H3 می‌گیرند.
{extra}
اگر semantic_topics چیز دیگری می‌گوید، همان را مبنا قرار بده.
یک هدینگ تعریفی فقط وقتی مجاز است که سوال کاربر واقعاً «چیست» باشد، نه به‌عنوان بخش اجباری.
H1 موضوع هسته را نمایندگی کند، نه برند را (مگر نیت صفحهٔ برند باشد).
دقیقاً یک H1. H3 فقط زیر H2 معنادار.
کیورد را در هدینگ‌ها ننشان. سوال تکراری و هدینگ خالی نساز.
هر هدینگ purpose داشته باشد.
خروجی HeadingPlan است؛ اولین آیتم headings باید H1 باشد.
هدینگ قفل‌شده را عوض نکن.
"""


def heading_planner_user(
    user_input: UserInput,
    topic_map_json: str,
    plan_json: str,
    existing_summary: str | None,
    locked_headings_json: str | None = None,
) -> str:
    existing = existing_summary or "محتوای فعلی نیست."
    locked = locked_headings_json or "هدینگ قفل‌شده نیست."
    return f"""
ورودی:
{input_brief(user_input)}

ContentMap:
{topic_map_json}

SEOPlan:
{plan_json}

خلاصه محتوای فعلی:
{existing}

هدینگ‌های قفل‌شده:
{locked}
"""


def heading_repair_system(user_input: UserInput | None = None) -> str:
    return heading_planner_system(user_input) + "\nساختار رد شده. فقط HeadingPlan را اصلاح کن. به قالب عمومی برنگرد."


def heading_repair_user(
    user_input: UserInput,
    architecture_json: str,
    issues_json: str,
    plan_json: str,
    topic_map_json: str = "",
) -> str:
    return f"""
ورودی:
{input_brief(user_input)}
معماری فعلی:
{architecture_json}
ایرادها:
{issues_json}
ContentMap:
{topic_map_json}
SEOPlan:
{plan_json}
"""
