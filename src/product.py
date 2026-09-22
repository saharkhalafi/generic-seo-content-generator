"""Website-context guardrails. Product facts come from the user's website description."""

from __future__ import annotations

from src.schemas import UserInput, WebsiteContext

# Absolute claims that are unsupported on any legitimate website unless the
# user explicitly wrote them into the website description.
UNSUPPORTED_PRODUCT_CLAIMS = (
    "تضمین ۱۰۰٪",
    "تضمین 100٪",
    "تضمین 100%",
    "رتبه یک جهان",
    "بدون هیچ ریسکی تضمین شده",
)


def seed_website_context(user_input: UserInput) -> WebsiteContext:
    """Copy user-provided website fields into WebsiteContext without an extra model call."""
    current = user_input.website_context or WebsiteContext()
    context = WebsiteContext(
        website_name=(user_input.website_name or current.website_name).strip(),
        website_description=(user_input.website_description or current.website_description).strip(),
        business_type=current.business_type.strip(),
        audience=(user_input.target_audience or current.audience).strip(),
        products_or_services=list(current.products_or_services),
        domain_context=current.domain_context.strip(),
    )
    user_input.website_context = context
    return context


def merge_inferred_context(user_input: UserInput, inferred: WebsiteContext | None) -> WebsiteContext:
    """Fill blanks from the planning bundle. User-written name and description win."""
    current = seed_website_context(user_input)
    inferred = inferred or WebsiteContext()
    context = WebsiteContext(
        website_name=current.website_name or inferred.website_name.strip(),
        website_description=current.website_description or inferred.website_description.strip(),
        business_type=current.business_type or inferred.business_type.strip(),
        audience=current.audience or inferred.audience.strip(),
        products_or_services=list(current.products_or_services or inferred.products_or_services),
        domain_context=current.domain_context or inferred.domain_context.strip(),
    )
    user_input.website_context = context
    if context.audience and not user_input.target_audience.strip():
        user_input.target_audience = context.audience
    return context


def brand_aliases_for(user_input: UserInput | None) -> tuple[str, ...]:
    if user_input is None:
        return ()
    names: list[str] = []
    for value in (
        user_input.website_name,
        user_input.website_context.website_name if user_input.website_context else "",
    ):
        text = (value or "").strip()
        if text and text not in names:
            names.append(text)
    expanded: list[str] = []
    for name in names:
        expanded.append(name)
        if "‌" in name:
            spaced = name.replace("‌", " ")
            if spaced not in expanded:
                expanded.append(spaced)
        if " " in name:
            joined = name.replace(" ", "‌")
            if joined not in expanded:
                expanded.append(joined)
    return tuple(expanded)


def product_guardrail_prompt() -> str:
    return """
وقتی (و فقط وقتی) محصول یا خدمت وب‌سایت به نیت جستجو پاسخ می‌دهد، فقط از WEBSITE CONTEXT استفاده کن.
محصول، خدمت، قیمت، آمار، تضمین یا قابلیت را اختراع نکن.
اگر توضیح وب‌سایت دربارهٔ یک قابلیت ساکت است، آن قابلیت را ننویس.
نام وب‌سایت موضوع مقاله نیست؛ فقط راه‌حل کمکی نزدیک پایان است، آن هم اگر واقعاً مرتبط باشد.
تبلیغ اجباری، کیورد استافینگ و ادعای ساختگی ممنوع است.
""".strip()


def website_context_prompt(user_input: UserInput | None) -> str:
    if user_input is None or not (user_input.website_description or "").strip():
        return "WEBSITE CONTEXT:\nداده نشده است. هیچ صنعت، محصول یا مخاطبی را فرض نکن."
    context = user_input.website_context
    name = (user_input.website_name or (context.website_name if context else "") or "نامشخص").strip()
    lines = [
        "WEBSITE CONTEXT:",
        "website_name: " + name,
        "website_description: " + user_input.website_description.strip(),
    ]
    if context and context.business_type.strip():
        lines.append("business_type: " + context.business_type.strip())
    if context and context.audience.strip():
        lines.append("audience: " + context.audience.strip())
    if context and context.products_or_services:
        lines.append("products_or_services: " + "، ".join(context.products_or_services))
    if context and context.domain_context.strip():
        lines.append("domain_context: " + context.domain_context.strip())
    lines.append(
        "این مقاله برای همین وب‌سایت نوشته می‌شود. اصطلاحات، مخاطب و ارتباط محصول/خدمت را فقط از همین بافت بگیر. "
        "چیزی را که در توضیح وب‌سایت نیست اختراع نکن و تبلیغ اجباری نکن."
    )
    return "\n".join(lines)


def product_facts_for_slots(user_input: UserInput | None = None) -> str:
    return website_context_prompt(user_input)
