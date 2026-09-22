from __future__ import annotations

import logging
import re
from collections.abc import Iterable

from src.config import (
    HEADING_SIMILARITY_THRESHOLD,
    KEYWORD_STUFFING_FAIL,
    KEYWORD_STUFFING_SEVERE,
    REVISION_SCORE_THRESHOLD,
    SCORE_WEIGHTS,
    hard_max_word_count,
    word_count_bounds,
)
from src.persian import (
    contains_term,
    count_words,
    extract_headings,
    html_to_text,
    normalize_fa,
    similarity,
    strip_html,
)
from src.product import UNSUPPORTED_PRODUCT_CLAIMS, brand_aliases_for
from src.schemas import (
    CategoryScore,
    ChecklistItem,
    CheckStatus,
    Content,
    ContentMap,
    HeadingNode,
    HeadingPlan,
    LLMQualitativeReview,
    Metadata,
    SEOPlan,
    UserInput,
    Validation,
)

logger = logging.getLogger("seo-content")

HARD_FAIL_CODES = {
    "h1_count",
    "html_h1",
    "missing_primary",
    "invalid_hierarchy",
    "h3_orphan",
    "missing_title",
    "missing_meta",
    "empty_content",
    "too_short",
    "too_long",
    "keyword_stuffing_severe",
    "hallucination",
    "forbidden_claim",
    "invalid_structured_output",
    "missing_required_fields",
}

AI_FILLER = (
    "در دنیای امروز",
    "بدون شک",
    "لازم به ذکر است",
    "همانطور که می‌دانید",
    "در این مقاله جامع",
    "به طور کلی می‌توان گفت",
    "بی‌نظیر و منحصربه‌فرد",
    "بهترین انتخاب همیشگی",
)
MARKETING_FILLER = (
    "همین حالا معجزه",
    "تضمین موفقیت",
    "بدون هیچ رقیب",
)
ARABIC_LETTERS = ("ي", "ك")
MEDICAL_FINANCIAL_CLAIMS = (
    "درمان قطعی",
    "تضمین سود",
    "بازگشت سرمایه تضمینی",
    "شفا",
    "بدون عارضه",
)
GENERIC_HEADING_MARKERS = (
    "چیست؟",
    "مزایا",
    "معایب",
    "کاربردها",
    "نحوه استفاده",
    "نتیجه‌گیری",
    "نتیجه گیری",
)


def _item(
    *,
    code: str,
    category: str,
    title: str,
    ok: bool,
    message: str,
    recommendation: str = "",
    warning: bool = False,
    target: str = "",
) -> ChecklistItem:
    if ok and not warning:
        status: CheckStatus = "PASS"
    elif warning and ok:
        status = "WARNING"
    else:
        status = "FAIL"
    return ChecklistItem(
        code=code,
        category=category,
        title=title,
        status=status,
        message=message,
        recommendation=recommendation,
        hard_fail=code in HARD_FAIL_CODES and status == "FAIL",
        target=target,
    )


def extract_introduction(html: str, introduction_html: str = "") -> str:
    if introduction_html.strip():
        return html_to_text(introduction_html)
    text = html or ""
    h1 = re.search(r"</h1>", text, flags=re.I)
    h2 = re.search(r"<h2\b", text, flags=re.I)
    if h1 and h2 and h2.start() > h1.end():
        return html_to_text(text[h1.end() : h2.start()])
    return html_to_text(text)[:400]


def keyword_density(html: str, keyword: str) -> float:
    words = count_words(html)
    if words == 0:
        return 0.0
    haystack = normalize_fa(html)
    needle = normalize_fa(keyword)
    if not needle:
        return 0.0
    return haystack.count(needle) / words


def heading_duplicates(texts: Iterable[str], threshold: float = HEADING_SIMILARITY_THRESHOLD) -> list[tuple[str, str, float]]:
    items = [item.strip() for item in texts if item.strip()]
    found: list[tuple[str, str, float]] = []
    for i, left in enumerate(items):
        for right in items[i + 1 :]:
            score = similarity(left, right)
            if score >= threshold:
                found.append((left, right, score))
    return found


def validate_heading_plan(plan: HeadingPlan, user_input: UserInput) -> list[ChecklistItem]:
    checks: list[ChecklistItem] = []
    headings = list(plan.headings or [])
    h1s = [item for item in headings if item.level == "H1"]
    if plan.h1 and not h1s:
        headings = [HeadingNode(level="H1", text=plan.h1, purpose="عنوان اصلی"), *headings]
        h1s = [headings[0]]
    checks.append(
        _item(
            code="h1_count",
            category="technical",
            title="دقیقاً یک H1",
            ok=len(h1s) == 1,
            message="تعداد H1 درست است." if len(h1s) == 1 else f"تعداد H1 برابر {len(h1s)} است.",
            recommendation="فقط یک H1 نگه دارید.",
        )
    )
    if h1s:
        min_h1 = 6 if user_input.is_simple else 12
        natural = len(h1s[0].text.strip()) >= min_h1
        relevant = contains_term(h1s[0].text, user_input.primary_keyword) or contains_term(
            h1s[0].text, user_input.category_name
        )
        checks.append(
            _item(
                code="h1_topic",
                category="heading",
                title="H1 مرتبط و طبیعی",
                ok=relevant and natural,
                message="H1 موضوع اصلی را نمایندگی می‌کند." if relevant else "H1 موضوع اصلی را نمایندگی نمی‌کند.",
                recommendation="H1 باید کلمه کلیدی یا موضوع دسته را به‌صورت طبیعی داشته باشد.",
                target=h1s[0].text,
            )
        )
    last_h2 = None
    h2_count = 0
    keyword_hits = 0
    generic_hits = 0
    orphan = False
    empty = False
    for node in headings:
        text = node.text.strip()
        if not text:
            empty = True
            continue
        if node.level == "H2":
            last_h2 = text
            h2_count += 1
        elif node.level == "H3":
            if not last_h2:
                orphan = True
        if contains_term(text, user_input.primary_keyword):
            keyword_hits += 1
        if any(marker in text for marker in GENERIC_HEADING_MARKERS):
            generic_hits += 1
    checks.append(
        _item(
            code="h3_orphan" if orphan else "invalid_hierarchy",
            category="technical",
            title="سلسله‌مراتب H1→H2→H3",
            ok=not orphan,
            message="سلسله‌مراتب هدینگ معتبر است." if not orphan else "H3 بدون H2 والد وجود دارد.",
            recommendation="هر H3 باید زیر یک H2 بیاید.",
        )
    )
    checks.append(
        _item(
            code="empty_heading",
            category="heading",
            title="هدینگ خالی",
            ok=not empty,
            message="هدینگ خالی نیست." if not empty else "حداقل یک هدینگ خالی است.",
        )
    )
    dups = heading_duplicates(item.text for item in headings)
    checks.append(
        _item(
            code="near_duplicate",
            category="heading",
            title="عدم تکرار هدینگ",
            ok=not dups,
            message="هدینگ تکراری نیست." if not dups else f"هدینگ نزدیک به هم: {dups[0][0]}",
            recommendation="هدینگ‌های مشابه را ادغام یا بازنویسی کنید.",
        )
    )
    checks.append(
        _item(
            code="h2_coverage",
            category="heading",
            title="پوشش موضوعات در H2",
            ok=h2_count >= 2,
            warning=2 <= h2_count < 3 and not user_input.is_simple,
            message=f"{h2_count} هدینگ H2 وجود دارد.",
            recommendation="موضوعات هسته را با H2 پوشش بده؛ تعداد را برای سئو باد نکن.",
        )
    )
    stuffing = bool(headings) and keyword_hits / max(len(headings), 1) > 0.7
    checks.append(
        _item(
            code="heading_stuffing",
            category="heading",
            title="عدم کیورد استافینگ در هدینگ",
            ok=not stuffing,
            message="تکرار کلمه کلیدی در هدینگ‌ها متعادل است." if not stuffing else "کلمه کلیدی در اکثر هدینگ‌ها تکرار شده.",
        )
    )
    generic = generic_hits >= 3 and h2_count <= 5 and not user_input.is_simple
    checks.append(
        _item(
            code="generic_architecture",
            category="heading",
            title="معماری پویای دسته",
            ok=not generic,
            warning=generic,
            message="ساختار هدینگ اختصاصی دسته است." if not generic else "ساختار به قالب عمومی چیست/مزایا/کاربردها نزدیک است.",
            recommendation="معماری را بر اساس نیت و صنعت همین دسته بسازید.",
        )
    )
    return checks


def evaluate(
    *,
    user_input: UserInput,
    plan: SEOPlan,
    headings: HeadingPlan,
    article: Content,
    qualitative: LLMQualitativeReview | None = None,
    cannibalization: list[str] | None = None,
    content_map: ContentMap | None = None,
) -> Validation:
    html = article.article_html or ""
    intro = extract_introduction(html, article.introduction_html)
    words = article.word_count or count_words(html)
    html_headings = extract_headings(html)
    checks: list[ChecklistItem] = []

    required_ok = bool(user_input.category_name and user_input.primary_keyword and html)
    checks.append(
        _item(
            code="missing_required_fields",
            category="technical",
            title="فیلدهای الزامی",
            ok=required_ok,
            message="ورودی و خروجی اصلی موجود است." if required_ok else "فیلد الزامی خالی است.",
        )
    )
    checks.append(
        _item(
            code="empty_content",
            category="technical",
            title="محتوای غیرخالی",
            ok=bool(strip_html(html)),
            message="محتوا تولید شده است." if html.strip() else "محتوا خالی است.",
        )
    )
    min_words, max_words = word_count_bounds(user_input.box_style)
    hard_max = hard_max_word_count(user_input.box_style)
    too_short = words < min_words
    too_long = words > hard_max
    long_warn = max_words < words <= hard_max
    checks.append(
        _item(
            code="too_short" if too_short else "too_long" if too_long else "word_count",
            category="technical",
            title="طول محتوا بر اساس پوشش موضوع",
            ok=not too_short and not too_long,
            warning=long_warn,
            message=f"تعداد کلمات: {words} (بازهٔ قابل قبول حدود {min_words}–{max_words})",
            recommendation="پرکننده اضافه نکن؛ اگر محتوا مفید است آن را قطع نکن.",
        )
    )

    h1s = [text for level, text in html_headings if level == "H1"]
    checks.append(
        _item(
            code="html_h1",
            category="technical",
            title="یک H1 در HTML",
            ok=len(h1s) == 1,
            message=f"تعداد H1 در HTML: {len(h1s)}",
        )
    )
    checks.extend(validate_heading_plan(headings, user_input))

    title = (article.metadata.seo_title or "").strip()
    desc = (article.metadata.meta_description or "").strip()
    slug = (article.metadata.url_slug or "").strip()
    checks.append(
        _item(
            code="missing_title",
            category="technical",
            title="عنوان سئو",
            ok=bool(title),
            message="عنوان سئو موجود است." if title else "عنوان سئو خالی است.",
        )
    )
    checks.append(
        _item(
            code="missing_meta",
            category="technical",
            title="توضیحات متا",
            ok=bool(desc),
            message="توضیحات متا موجود است." if desc else "توضیحات متا خالی است.",
        )
    )
    title_len_ok = 20 <= len(title) <= 70
    checks.append(
        _item(
            code="title_length",
            category="technical",
            title="طول عنوان سئو",
            ok=title_len_ok,
            warning=bool(title) and not title_len_ok and 15 <= len(title) <= 80,
            message=f"طول عنوان: {len(title)} کاراکتر",
            recommendation="عنوان را حدود ۵۰–۶۰ کاراکتر نگه دارید.",
        )
    )
    desc_len_ok = 70 <= len(desc) <= 180
    checks.append(
        _item(
            code="meta_length",
            category="technical",
            title="طول توضیحات متا",
            ok=desc_len_ok,
            warning=bool(desc) and not desc_len_ok and 50 <= len(desc) <= 200,
            message=f"طول متا: {len(desc)} کاراکتر",
            recommendation="توضیحات را حدود ۱۴۰–۱۶۰ کاراکتر نگه دارید.",
        )
    )
    slug_ok = bool(slug) and (" " not in slug) and (slug.startswith("http") or re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*/?", slug) or "/" in slug)
    checks.append(
        _item(
            code="valid_slug",
            category="technical",
            title="اسلاگ معتبر",
            ok=bool(slug_ok),
            message="اسلاگ معتبر است." if slug_ok else "اسلاگ خالی یا نامعتبر است.",
        )
    )
    if user_input.category_url and not article.metadata.preserve_existing_url:
        checks.append(
            _item(
                code="url_changed",
                category="technical",
                title="حفظ URL موجود",
                ok=False,
                warning=True,
                message="URL موجود باید حفظ شود.",
            )
        )

    core_topic = (content_map.core_topic if content_map else "") or user_input.category_name
    primary_present = contains_term(html, user_input.primary_keyword) or contains_term(html, core_topic)
    checks.append(
        _item(
            code="missing_primary",
            category="keyword",
            title="حضور طبیعی موضوع هسته",
            ok=primary_present,
            message="موضوع هسته در محتوا هست." if primary_present else "موضوع هسته در محتوا دیده نمی‌شود.",
        )
    )
    h1_text = h1s[0] if h1s else article.h1
    topic_in_h1 = contains_term(h1_text, core_topic) or contains_term(h1_text, user_input.primary_keyword) or contains_term(h1_text, user_input.category_name)
    topic_in_intro = contains_term(intro, core_topic) or contains_term(intro, user_input.primary_keyword) or contains_term(intro, user_input.category_name)
    checks.append(
        _item(
            code="primary_in_h1_intro",
            category="keyword",
            title="موضوع هسته در H1 و مقدمه",
            ok=topic_in_h1 and topic_in_intro,
            warning=topic_in_h1 != topic_in_intro,
            message="H1 و مقدمه موضوع را نمایندگی می‌کنند." if topic_in_h1 and topic_in_intro else "موضوع هسته باید در H1/مقدمه طبیعی باشد، نه با کیورد اجباری.",
        )
    )
    must_use = [item.term for item in plan.keyword_map if item.usage == "MUST_USE"]
    used_secondary = sum(1 for term in must_use if contains_term(html, term))
    checks.append(
        _item(
            code="secondary_contextual",
            category="keyword",
            title="استفادهٔ طبیعی از عبارات مرتبط",
            ok=True,
            warning=bool(must_use) and used_secondary == 0,
            message="عبارات MUST_USE در صورت نامرتبط بودن می‌توانند حذف شوند؛ اجبار نیست.",
        )
    )
    variants = (content_map.relevant_keyword_variants if content_map else plan.keyword_variants)
    variants_used = sum(1 for term in variants if contains_term(html, term))
    checks.append(
        _item(
            code="variants_covered",
            category="keyword",
            title="واریانت‌های معنایی در صورت ارتباط",
            ok=True,
            warning=bool(variants) and variants_used == 0,
            message=f"{variants_used} واریانت مرتبط دیده شد.",
        )
    )
    density = keyword_density(html, user_input.primary_keyword)
    severe = density >= KEYWORD_STUFFING_SEVERE
    stuffed = density >= KEYWORD_STUFFING_FAIL
    checks.append(
        _item(
            code="keyword_stuffing_severe" if severe else "keyword_stuffing",
            category="keyword",
            title="عدم کیورد استافینگ",
            ok=not stuffed,
            message=f"چگالی تقریبی کلمه کلیدی: {density:.3f}",
            recommendation="تکرار exact-match را کم کنید و به پوشش نیت توجه کنید.",
        )
    )
    irrelevant = [item.term for item in plan.keyword_map if item.usage == "NOT_RELEVANT"]
    irrelevant_hits = [term for term in irrelevant if contains_term(html, term)]
    checks.append(
        _item(
            code="irrelevant_keywords",
            category="keyword",
            title="نبود کلمات نامرتبط",
            ok=not irrelevant_hits,
            message="کلمات نامرتبط در متن نیست." if not irrelevant_hits else f"عبارات نامرتبط: {', '.join(irrelevant_hits[:3])}",
        )
    )
    if cannibalization:
        checks.append(
            _item(
                code="cannibalization",
                category="keyword",
                title="هشدار هم‌پوشانی کلمه کلیدی",
                ok=True,
                warning=True,
                message=cannibalization[0],
                recommendation="کلمه کلیدی اصلی را متمایز کنید یا صفحات را ادغام کنید.",
            )
        )
    else:
        checks.append(
            _item(
                code="cannibalization",
                category="keyword",
                title="هشدار هم‌پوشانی کلمه کلیدی",
                ok=True,
                message="هم‌پوشانی با دسته دیگر ثبت نشد.",
            )
        )

    use_industries = [item.name for item in (content_map.industry_uses if content_map else []) if item.relevance == "USE"]
    skip_industries = [item.name for item in (content_map.industry_uses if content_map else []) if item.relevance == "SKIP"]
    industry_hits = sum(1 for item in use_industries if contains_term(html, item))
    skipped_hits = [item for item in skip_industries if contains_term(html, item)]
    checks.append(
        _item(
            code="industries_covered",
            category="intent",
            title="صنایع فقط در صورت سود اطلاعاتی",
            ok=not skipped_hits,
            warning=bool(use_industries) and industry_hits == 0,
            message="صنعت نامرتبط در متن نیست." if not skipped_hits else f"صنایع SKIP شده در متن آمده‌اند: {', '.join(skipped_hits[:3])}",
            recommendation="صنعت را فقط به‌عنوان کاربرد/مثال/مخاطب بیاور، نه فهرست کیورد.",
        )
    )
    faq_n = len(article.faqs)
    if user_input.is_simple:
        faq_ok = faq_n <= 2
        faq_message = f"{faq_n} پرسش متداول؛ در حالت ساده FAQ الزامی نیست."
    else:
        faq_ok = 4 <= faq_n <= 6
        faq_message = f"{faq_n} پرسش متداول تولید شد."
    checks.append(
        _item(
            code="faq_count",
            category="intent",
            title="FAQ اختصاصی دسته",
            ok=faq_ok,
            warning=user_input.is_simple and faq_n > 0,
            message=faq_message,
        )
    )
    generic_faq = sum(
        1
        for faq in article.faqs
        if faq.question.strip().endswith("چیست؟") and user_input.category_name not in faq.question
    )
    checks.append(
        _item(
            code="generic_faq",
            category="intent",
            title="FAQ غیرعمومی",
            ok=generic_faq < 3,
            message="سوالات متداول اختصاصی هستند." if generic_faq < 3 else "FAQ بیش از حد عمومی است.",
        )
    )
    informational = "informational" in (content_map.primary_search_intent if content_map else plan.search_intent.primary_intent).lower()
    checks.append(
        _item(
            code="natural_cta",
            category="intent",
            title="CTA فقط در صورت تناسب نیت",
            ok=True,
            warning=not article.cta.strip() and not informational,
            message="CTA در صورت نیت تجاری می‌تواند طبیعی باشد؛ اجبار تبلیغاتی نیست.",
        )
    )
    link_n = len(article.internal_links)
    checks.append(
        _item(
            code="internal_links",
            category="content",
            title="پیشنهاد لینک داخلی",
            ok=user_input.is_simple or link_n >= 1,
            warning=link_n == 0,
            message=f"{link_n} پیشنهاد لینک داخلی.",
        )
    )

    filler_hits = [phrase for phrase in AI_FILLER + MARKETING_FILLER if phrase in html]
    checks.append(
        _item(
            code="ai_filler",
            category="persian",
            title="نبود پرکننده و زبان تبلیغاتی خالی",
            ok=len(filler_hits) < 2,
            warning=len(filler_hits) == 1,
            message="عبارات کلیشه‌ای محدود است." if len(filler_hits) < 2 else f"پرکننده: {', '.join(filler_hits)}",
        )
    )
    aliases = brand_aliases_for(user_input)
    brand_hits = _count_brand_mentions(
        html + " " + article.cta + " " + " ".join(item.text for item in headings.headings),
        aliases,
    )
    brand_in_h1 = any(_count_brand_mentions(text, aliases) for text in ([h1_text] if h1_text else []))
    brand_in_h2 = sum(1 for item in headings.headings if item.level == "H2" and _count_brand_mentions(item.text, aliases))
    policy = content_map.product_mention_policy if content_map else "supporting_section"
    brand_ok = True
    brand_warn = False
    if policy != "brand_page" and brand_in_h1:
        brand_ok = False
    elif policy != "brand_page" and brand_in_h2 >= 2:
        brand_ok = False
    elif words and brand_hits / max(words, 1) > 0.02:
        brand_ok = False
    elif words and brand_hits / max(words, 1) > 0.01:
        brand_warn = True
    if qualitative and qualitative.brand_overuse:
        brand_ok = False
    checks.append(
        _item(
            code="brand_overuse",
            category="content",
            title="برند به‌عنوان موجودیت کمکی",
            ok=brand_ok,
            warning=brand_warn and brand_ok,
            message=f"ذکر برند: {brand_hits} بار؛ H1 برند: {brand_in_h1}؛ H2 برند: {brand_in_h2}",
            recommendation="موضوع را محور کن و برند را به بخش راه‌حل/CTA محدود کن.",
        )
    )
    mismatches = _heading_section_mismatches(html)
    checks.append(
        _item(
            code="heading_section_mismatch",
            category="heading",
            title="پاسخ واقعی هر بخش به هدینگ",
            ok=not mismatches,
            warning=len(mismatches) == 1,
            message="بخش‌ها به هدینگ خود پاسخ می‌دهند." if not mismatches else f"عدم تطابق: {mismatches[0]}",
        )
    )
    table_count = len(re.findall(r"<table", html, flags=re.I))
    checks.append(
        _item(
            code="optional_tables",
            category="content",
            title="جدول فقط در صورت سود اطلاعاتی",
            ok=table_count <= 2,
            warning=table_count > 2,
            message=f"{table_count} جدول در محتوا.",
        )
    )
    arabic_mix = any(letter in (html + article.cta) for letter in ARABIC_LETTERS)
    checks.append(
        _item(
            code="persian_letters",
            category="persian",
            title="یکدستی حروف فارسی",
            ok=not arabic_mix,
            warning=arabic_mix,
            message="حروف عربی/فارسی یکدست است." if not arabic_mix else "حروف عربی ي/ك در متن دیده شد؛ نیم‌فاصله و ی/ک فارسی را یکدست کنید.",
        )
    )
    half_space_issue = "می شود" in html or "می توانید" in html or "نمی توان" in html
    checks.append(
        _item(
            code="half_space",
            category="persian",
            title="نیم‌فاصله",
            ok=not half_space_issue,
            warning=half_space_issue,
            message="نیم‌فاصله در افعال رایج رعایت شده." if not half_space_issue else "مواردی مثل «می شود» بهتر است با نیم‌فاصله نوشته شود.",
        )
    )

    described = (user_input.website_description or "").lower()
    forbidden_hits = [
        claim
        for claim in UNSUPPORTED_PRODUCT_CLAIMS
        if (claim.lower() in html.lower() or claim in html) and claim.lower() not in described
    ]
    checks.append(
        _item(
            code="forbidden_claim",
            category="product",
            title="دقت ادعاهای محصول یا خدمت",
            ok=not forbidden_hits,
            message="ادعای قطعیِ بدون پشتوانه دیده نشد." if not forbidden_hits else f"ادعای بدون پشتوانه: {forbidden_hits[0]}",
        )
    )
    risky = [claim for claim in MEDICAL_FINANCIAL_CLAIMS if claim in html]
    fake_stats = bool(re.search(r"\d{2,3}\s?٪|\d{2,3}\s?درصد", html))
    checks.append(
        _item(
            code="unsupported_claims",
            category="trust",
            title="نبود ادعای پزشکی/مالی بی‌پشتوانه",
            ok=not risky,
            message="ادعای پزشکی/مالی اغراق‌آمیز نیست." if not risky else f"ادعای پرریسک: {risky[0]}",
        )
    )
    checks.append(
        _item(
            code="fake_statistics",
            category="trust",
            title="نبود آمار ساختگی",
            ok=not fake_stats,
            warning=fake_stats,
            message="آمار درصدی مشکوک دیده نشد." if not fake_stats else "درصدهای بدون منبع ممکن است ساختگی باشند. حجم جستجو یا سختی کلمه کلیدی نسازید.",
        )
    )

    if qualitative:
        if qualitative.hallucination_detected:
            checks.append(
                _item(
                    code="hallucination",
                    category="trust",
                    title="توهم محتوایی",
                    ok=False,
                    message="مدل ادعای ساختگی یا توهم را گزارش کرد.",
                )
            )
        if qualitative.search_intent_coverage < 60:
            checks.append(
                _item(
                    code="intent_unsatisfied",
                    category="intent",
                    title="پوشش نیت جستجو",
                    ok=False,
                    message="نیت جستجو به‌قدر کافی برآورده نشده است.",
                    recommendation="معماری یا بخش‌های مرتبط با نیت را اصلاح کن.",
                )
            )
        if qualitative.semantic_coverage < 60:
            checks.append(
                _item(
                    code="semantic_gaps",
                    category="intent",
                    title="پوشش معنایی",
                    ok=False,
                    warning=True,
                    message="موضوعات معنایی ناقص است.",
                )
            )
        if qualitative.commercial_content_ratio > 0.45 and policy != "brand_page":
            checks.append(
                _item(
                    code="commercial_disproportion",
                    category="content",
                    title="تعادل موضوعی/تجاری",
                    ok=False,
                    warning=qualitative.commercial_content_ratio <= 0.6,
                    message=f"نسبت تجاری تقریبی {qualitative.commercial_content_ratio:.2f} با نیت کاربر نمی‌خواند.",
                )
            )
        checks.extend(qualitative.issues)

    by_cat: dict[str, list[ChecklistItem]] = {name: [] for name in SCORE_WEIGHTS}
    for check in checks:
        by_cat.setdefault(check.category, []).append(check)

    category_details: list[CategoryScore] = []
    category_scores: dict[str, int] = {}
    for name, weight in SCORE_WEIGHTS.items():
        items = by_cat.get(name) or []
        if qualitative:
            extra = {
                "intent": qualitative.intent_score,
                "content": qualitative.content_quality_score,
                "persian": qualitative.persian_score,
                "product": qualitative.product_score,
                "trust": qualitative.trust_score,
            }.get(name)
        else:
            extra = None
        numeric = [_status_points(item.status) for item in items]
        if extra is not None:
            numeric.append(max(0, min(100, extra)))
        score = int(round(sum(numeric) / len(numeric))) if numeric else 80
        if any(item.status == "FAIL" and item.hard_fail for item in items):
            cat_status: CheckStatus = "FAIL"
        elif any(item.status != "PASS" for item in items):
            cat_status = "WARNING" if score >= 70 else "FAIL"
        else:
            cat_status = "PASS"
        category_scores[name] = score
        category_details.append(CategoryScore(name=name, weight=weight, score=score, status=cat_status))

    overall = int(round(sum(category_scores[name] * weight for name, weight in SCORE_WEIGHTS.items())))
    hard_fails = [item.code for item in checks if item.hard_fail]
    failed = [item.code for item in checks if item.status == "FAIL"]
    warnings = [item.code for item in checks if item.status == "WARNING"]
    recommendations = [item.recommendation for item in checks if item.status != "PASS" and item.recommendation]
    if qualitative:
        recommendations.extend(qualitative.recommendations)
        weak = list(dict.fromkeys(qualitative.weak_sections))
    else:
        weak = []
    if overall >= 90:
        band = "Excellent"
    elif overall >= 80:
        band = "Good"
    elif overall >= 70:
        band = "Needs Improvement"
    else:
        band = "Revision Required"
    revision_required = overall < REVISION_SCORE_THRESHOLD or bool(hard_fails)
    passed = not revision_required
    return Validation(
        overall_score=overall,
        band=band,
        category_scores=category_scores,
        category_details=category_details,
        checks=checks,
        hard_fails=hard_fails,
        failed_checks=failed,
        warnings=warnings,
        recommendations=list(dict.fromkeys(recommendations)),
        weak_sections=weak,
        revision_required=revision_required,
        passed=passed,
        summary=f"امتیاز {overall} — {band}",
    )


def _count_brand_mentions(text: str, aliases: tuple[str, ...] = ()) -> int:
    haystack = normalize_fa(text).lower()
    total = 0
    for alias in aliases:
        needle = normalize_fa(alias).lower()
        if needle:
            total += haystack.count(needle)
    return total


def _heading_section_mismatches(html: str) -> list[str]:
    parts = re.split(r"(<h2\b[^>]*>.*?</h2>)", html or "", flags=re.I | re.S)
    mismatches: list[str] = []
    for index in range(1, len(parts), 2):
        heading = strip_html(parts[index])
        body = strip_html(parts[index + 1] if index + 1 < len(parts) else "")
        if not heading or count_words(body) < 40:
            continue
        if similarity(heading, body) < 0.06 and not any(
            token in normalize_fa(body) for token in normalize_fa(heading).split() if len(token) > 3
        ):
            mismatches.append(heading)
    return mismatches


def revision_action_from_validation(validation: Validation, qualitative: LLMQualitativeReview | None = None) -> tuple[str, str, list[str]]:
    if qualitative and qualitative.revision_action and qualitative.revision_action != "none":
        return qualitative.revision_action, qualitative.revision_instructions, qualitative.revision_targets or qualitative.weak_sections
    failed = set(validation.failed_checks + validation.hard_fails)
    if {"generic_architecture", "h2_coverage", "intent_unsatisfied"} & failed:
        return "revise_architecture", "معماری را بر اساس نیت و نقشهٔ معنایی اصلاح کن.", validation.weak_sections
    if {"brand_overuse", "commercial_disproportion", "brand_in_h1"} & failed:
        return "reduce_brand", "ذکر برند را کم کن و موضوع را محور قرار بده.", ["commercial"]
    if {"keyword_stuffing", "keyword_stuffing_severe", "heading_stuffing"} & failed:
        return "revise_passages", "تکرار غیرطبیعی کیورد را بازنویسی کن.", validation.weak_sections
    if {"ai_filler"} & failed:
        return "remove_filler", "پرکننده و زبان تبلیغاتی خالی را حذف کن.", validation.weak_sections
    if {"forbidden_claim", "hallucination", "unsupported_claims"} & failed:
        return "remove_product_claims", "ادعاهای تأییدنشده محصول را حذف کن.", ["product"]
    if {"industries_covered", "irrelevant_keywords"} & failed:
        return "remove_irrelevant_entities", "صنایع و عبارات نامرتبط را حذف کن.", []
    if {"semantic_gaps", "heading_section_mismatch"} & failed:
        return "add_semantic_topics", "موضوع معنایی جاافتاده را اضافه کن یا بخش را با هدینگ هم‌خوان کن.", validation.weak_sections
    if validation.revision_required:
        return "revise_passages", "فقط بخش‌های ضعیف را اصلاح کن.", validation.weak_sections
    return "none", "", []


def _status_points(status: CheckStatus) -> int:
    return {"PASS": 100, "WARNING": 62, "FAIL": 18}[status]


def status_from_score(score: int, hard_fail: bool, revision_count: int, max_revisions: int) -> str:
    if hard_fail or score < REVISION_SCORE_THRESHOLD:
        if revision_count >= max_revisions:
            return "human_review_required"
        return "revision_required"
    if score >= 90:
        return "excellent"
    if score >= 80:
        return "good"
    return "needs_improvement"


def validate_metadata(meta: Metadata, primary_keyword: str, category_url: str) -> list:
    from src.schemas import ValidationIssue

    issues = []
    if not meta.seo_title.strip():
        issues.append(ValidationIssue(code="missing_title", severity="fail", message="عنوان سئو خالی است."))
    if not meta.meta_description.strip():
        issues.append(ValidationIssue(code="missing_meta", severity="fail", message="توضیحات متا خالی است."))
    if category_url and not meta.preserve_existing_url:
        issues.append(ValidationIssue(code="url_changed", severity="warning", message="URL موجود حفظ نشده."))
    if primary_keyword and not (
        contains_term(meta.seo_title, primary_keyword) or contains_term(meta.meta_description, primary_keyword)
    ):
        issues.append(
            ValidationIssue(
                code="meta_keyword",
                severity="fail",
                message="کلمه کلیدی اصلی در عنوان یا متا نیست.",
            )
        )
    return issues
