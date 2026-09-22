from __future__ import annotations

from src.config import MAX_WORD_COUNT, MIN_WORD_COUNT, SIMPLE_MAX_WORD_COUNT, SIMPLE_MIN_WORD_COUNT
from src.product import website_context_prompt
from src.prompts import CORE_SYSTEM, input_brief
from src.prompts.versions import CONTENT_GENERATOR_V2
from src.schemas import UserInput


def content_system(user_input: UserInput | None = None) -> str:
    simple = bool(user_input and user_input.is_simple)
    if simple:
        length = f"بازهٔ قابل قبول حدود {SIMPLE_MIN_WORD_COUNT} تا {SIMPLE_MAX_WORD_COUNT} کلمه است."
        shape = """
شکل نگارش حالت ساده:
پاراگراف‌های کوتاه و روان. حداکثر یک فهرست گلوله‌ای در صورت سود.
FAQ ننویس؛ faqs را خالی بگذار.
CTA اگر هست غیرتهاجمی و نزدیک پایان باشد.
برند را موضوع مقاله نکن؛ نزدیک پایان به‌عنوان راه انجام کار ذکر کن.
"""
    else:
        length = f"بازهٔ قابل قبول حدود {MIN_WORD_COUNT} تا {MAX_WORD_COUNT} است."
        shape = """
HTML ساده: article با h1, h2, h3, p, ul, li. جدول فقط در صورت نیاز واقعی به مقایسه.
دقیقاً یک h1. FAQ چهار تا شش سوال بر اساس user_questions همین موضوع.
CTA فقط اگر نیت تجاری/تراکنشی آن را توجیه کند؛ غیرتهاجمی.
"""
    return CORE_SYSTEM + f"""

نسخه پرامپت: {CONTENT_GENERATOR_V2}
محتوای فارسی صفحه دسته را بر اساس ContentMap و HeadingPlan بنویس.
استراتژی سئو را خودت از نو نساز و ترتیب/موضوع هدینگ را عوض نکن.
هر بخش باید واقعاً به هدینگ خودش پاسخ بدهد.

اولویت نگارش:
1) موضوع هسته و نیت جستجو
2) سوالات کاربر و موضوعات معنایی
3) مفاهیم مرتبط
4) صنعت/کاربرد فقط اگر در ContentMap برای آن USE آمده و اطلاعات مفیدی می‌افزاید
5) محصول فقط طبق product_mention_policy و commercial_placement

تعداد کلمات هدف ترجیح است، نه سهمیه. {length}
پرکننده اضافه نکن. مفید را قطع نکن.
{shape}
article_markdown را خالی بگذار؛ از HTML ساخته می‌شود.
introduction_html و notes را خالی بگذار مگر لازم باشد.
اصطلاحات انگلیسی رایج جستجو را فقط در صورت سودمندی طبیعی به کار ببر.
""" + "\n" + website_context_prompt(user_input)


def content_user(
    user_input: UserInput,
    topic_map_json: str,
    plan_json: str,
    heading_json: str,
    existing_summary: str | None,
    target_words: int,
    locks_json: str | None = None,
) -> str:
    existing = existing_summary or "محتوای فعلی نیست."
    locks = locks_json or "قفل دستی نیست."
    return f"""
ورودی:
{input_brief(user_input)}
ترجیح طول (نه اجبار عددی): حدود {target_words} کلمه
ContentMap:
{topic_map_json}
SEOPlan:
{plan_json}
HeadingPlan (لازم‌الاجرا):
{heading_json}
خلاصه محتوای فعلی برای KEEP/IMPROVE:
{existing}
قفل‌های دستی:
{locks}
"""
