from __future__ import annotations

from src.config import SIMPLE_MAX_WORD_COUNT, SIMPLE_MIN_WORD_COUNT
from src.prompts import CORE_SYSTEM, input_brief
from src.prompts.versions import PLANNING_BUNDLE_V2
from src.schemas import UserInput


def planning_bundle_system(user_input: UserInput | None = None) -> str:
    simple = bool(user_input and user_input.is_simple)
    if simple:
        shape = f"""
حالت ساده:
- recommended_word_count بین {SIMPLE_MIN_WORD_COUNT} و {SIMPLE_MAX_WORD_COUNT}؛ معمولاً حدود ۵۰۰.
- حداکثر ۲–۳ موضوع heading_worthy.
- H1 کوتاه و موضوع‌محور. فقط ۲–۳ H2. H3 و FAQ نساز.
- potential_faq_topics خالی.
- برند در commercial_placement فقط پاراگراف پایانی.
"""
    else:
        shape = """
حالت کامل:
- recommended_word_count بین ۷۰۰ و ۱۵۰۰ بر اساس پیچیدگی موضوع.
- FAQ چهار تا شش موضوع مرتبط.
- از قالب ثابت چیست/مزایا/انواع/نحوه استفاده به‌عنوان معماری پیش‌فرض پرهیز کن.
"""
    return CORE_SYSTEM + f"""

نسخه پرامپت: {PLANNING_BUNDLE_V2}
در یک خروجی PlanningBundle بساز: website_context + topic_map + seo_plan + heading_plan.
محتوای مقاله را ننویس.
website_context را در همین فراخوانی از توضیح کوتاه وب‌سایت استنباط کن. فراخوانی جدا برای طبقه‌بندی وب‌سایت نساز.
website_name و website_description را از ورودی کپی کن.
business_type، audience، products_or_services و domain_context را فقط اگر از توضیح کاربر برمی‌آیند پر کن.
صنعت، محصول یا خدمت را از پیش فرض نکن. اگر توضیح کافی نیست، آن فیلد را خالی بگذار.

topic_map:
- core_topic موضوع واقعی است، نه برند.
- صنایع پیش‌فرض OPTIONAL؛ USE فقط اگر ارزش متمایز دارند.
- product_mention_policy معمولاً supporting_section یا minimal.

seo_plan باید از topic_map پیروی کند، آن را عوض نکند.
MUST_USE فقط برای موضوع هسته. heading_topics_from_map از semantic_topics با heading_worthy.

heading_plan:
- دقیقاً یک H1 موضوع‌محور، بدون برند.
- اولین آیتم headings باید H1 باشد.
- کیورد را در هدینگ‌ها ننشان.
{shape}
"""


def planning_bundle_user(user_input: UserInput, existing_summary: str | None) -> str:
    existing = existing_summary or "محتوای فعلی نیست."
    return f"""
ورودی:
{input_brief(user_input)}

خلاصه محتوای فعلی:
{existing}

کلمه کلیدی را کورکورانه موضوع ندان. از دسته، کلمات فرعی، نیت و محتوای فعلی موضوع هسته را استخراج کن.
"""
