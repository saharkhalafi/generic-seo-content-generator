from __future__ import annotations

from src.prompts import CORE_SYSTEM, input_brief
from src.prompts.versions import REVISION_V2, SEO_VALIDATOR_V2
from src.schemas import UserInput


def validator_system(user_input: UserInput | None = None) -> str:
    extra = ""
    if user_input and user_input.is_simple:
        extra = """
حالت ساده: نبود FAQ، کم بودن H2، و کوتاه بودن متن ایراد نیست.
از مدل نخواه متن را به راهنمای جامع یا ۱۰۰۰+ کلمه تبدیل کند.
فقط کیفیت موضوع‌محور، صحت محصول و نبود پرکننده را بسنج.
"""
    return CORE_SYSTEM + f"""

نسخه پرامپت: {SEO_VALIDATOR_V2}
اعتبارسنجی معنایی. وجود کیورد یا H2 به‌تنهایی PASS نیست.

بسنج:
- آیا نیت جستجو برآورده شده؟
- آیا هر بخش به هدینگش پاسخ می‌دهد؟
- آیا موضوعات معنایی پوشش داده شده؟
- آیا کیوردها طبیعی‌اند؟
- آیا صنایع نامربوط یا اجباری آمده‌اند؟
- آیا برند بیش‌ازحد حضور دارد؟
- آیا بدون زبان تبلیغاتی مفید است؟
- آیا توهم محصول/آمار هست؟
- آیا پرکننده هست؟
{extra}
خروجی LLMQualitativeReview.
revision_action را از این‌ها انتخاب کن:
none, revise_architecture, revise_passages, reduce_brand, add_semantic_topics,
remove_filler, remove_product_claims, remove_irrelevant_entities
فقط جزء آسیب‌دیده را هدف بگیر.
"""


def validator_user(
    user_input: UserInput,
    article_html: str,
    extras_json: str,
) -> str:
    return f"""
ورودی:
{input_brief(user_input)}
نقشه و چک‌لیست کمکی:
{extras_json}
محتوا:
{article_html}
"""


def revision_system(user_input: UserInput | None = None) -> str:
    extra = ""
    if user_input and user_input.is_simple:
        extra = "\nحالت ساده را به راهنمای جامع تبدیل نکن. FAQ اضافه نکن و متن را باد نکن."
    return CORE_SYSTEM + f"""

نسخه پرامپت: {REVISION_V2}
فقط جزء مشخص‌شده را اصلاح کن. بقیه را حفظ کن.
هدینگ قفل‌شده را عوض نکن مگر action برابر revise_architecture باشد.
خروجی مدل Content است.{extra}
"""


def revision_user(
    user_input: UserInput,
    article_html: str,
    article_markdown: str,
    issues_json: str,
    weak_sections: list[str],
    heading_json: str,
    target_words: int,
    locks_json: str | None = None,
    action: str = "revise_passages",
    instructions: str = "",
    topic_map_json: str = "",
) -> str:
    return f"""
ورودی:
{input_brief(user_input)}
نوع اصلاح هدفمند: {action}
دستور اصلاح:
{instructions}
بخش‌های نیازمند اصلاح: {weak_sections}
ایرادها:
{issues_json}
ContentMap:
{topic_map_json}
HeadingPlan:
{heading_json}
قفل‌ها:
{locks_json or "ندارد"}
ترجیح طول: {target_words}
HTML فعلی:
{article_html}
Markdown فعلی:
{article_markdown}
"""
