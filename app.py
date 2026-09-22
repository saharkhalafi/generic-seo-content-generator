from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from pydantic import ValidationError

from src.config import (
    INTENT_OPTIONS,
    default_word_count,
    get_settings,
    word_count_bounds,
)
from src.domain.errors import AppError, ErrorCategory, public_error_message
from src.exporters import seo_box_to_html_document, seo_box_to_json, seo_box_to_markdown
from src.llm import VertexAuthError, VertexClient, VertexGenerationError
from src.logutil import setup_logging
from src.orchestration.runner import ProductionSeoOrchestrator
from src.persian import lines_to_list
from src.persistence.factory import get_run_store
from src.schemas import (
    Content,
    FinalSEOBox,
    HeadingNode,
    HeadingPlan,
    ManualLocks,
    Metadata,
    RunOptions,
    SEOPlan,
    UserInput,
)
from src.security import sanitize_html

setup_logging()
logger = logging.getLogger("seo-content")

st.set_page_config(page_title="تولید محتوای سئو", page_icon="📝", layout="wide")
st.markdown(
    """
    <style>
      html, body, [data-testid="stAppViewContainer"] { direction: rtl; }
      .stTextInput input, .stTextArea textarea, .stNumberInput input { direction: rtl; text-align: right; }
      .article-preview { line-height: 1.95; font-size: 1.02rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

def main() -> None:
    st.title("تولید محتوای سئوی فارسی")
    st.caption("برنامه‌ریزی یک‌مرحله‌ای → محتوا → اعتبارسنجی محلی. وب‌سایت و موضوع را خودتان وارد کنید.")
    settings = get_settings()
    cols = st.columns([3, 1])
    with cols[1]:
        if st.button("تست اتصال Gemini"):
            try:
                message = VertexClient().ping()
                st.success(f"اتصال Gemini برقرار شد ({message}) / {settings.project_id}")
            except Exception as exc:  # noqa: BLE001
                st.error(public_error_message(exc))

    tabs = st.tabs(
        ["ورودی", "استراتژی سئو", "برنامه هدینگ", "محتوا", "اعتبارسنجی", "SEO Box نهایی"]
    )
    with tabs[0]:
        _input_tab()
    box: FinalSEOBox | None = st.session_state.get("seo_box")
    if not box:
        for tab in tabs[1:]:
            with tab:
                st.info("ابتدا از تب ورودی بسته را تولید کنید.")
        return
    with tabs[1]:
        _strategy_tab(box)
    with tabs[2]:
        _headings_tab(box)
    with tabs[3]:
        _content_tab(box)
    with tabs[4]:
        _validation_tab(box)
    with tabs[5]:
        _final_tab(box)


def _input_tab() -> None:
    style_label = st.radio(
        "نوع محتوا",
        options=["کامل", "ساده"],
        horizontal=True,
        index=0 if st.session_state.get("box_style_choice", "کامل") == "کامل" else 1,
        help="ساده: متن کوتاه‌تر بدون FAQ. کامل: راهنمای جامع با FAQ.",
        key="box_style_choice",
    )
    box_style = "simple" if style_label == "ساده" else "full"
    min_words, max_words = word_count_bounds(box_style)
    default_words = default_word_count(box_style)
    if box_style == "simple":
        st.caption("حالت ساده متنی کوتاه می‌سازد: مقدمه + چند بخش H2. FAQ ندارد.")
    else:
        st.caption("حالت کامل راهنمای جامع‌تر با FAQ و معماری عمیق‌تر می‌سازد.")
    if "desired_word_count_input" not in st.session_state:
        st.session_state["desired_word_count_input"] = default_words
    elif (
        st.session_state["desired_word_count_input"] < min_words
        or st.session_state["desired_word_count_input"] > max_words
    ):
        st.session_state["desired_word_count_input"] = default_words
    with st.form("seo_box_form"):
        website_name = st.text_input("نام وب‌سایت", placeholder="ExampleShop")
        website_description = st.text_area(
            "این وب‌سایت درباره چیست؟ *",
            placeholder="یک فروشگاه آنلاین لوازم دکوراسیون منزل است که محصولات مدرن و مینیمال ارائه می‌دهد.",
            height=100,
            help="یک تا سه جمله. نوع کسب‌وکار، مخاطب و محصول یا خدمت را از همین توضیح استنباط می‌کنیم.",
        )
        topic = st.text_input("موضوع مقاله / دسته *", placeholder="ایده‌های دکوراسیون اتاق خواب کوچک")
        with st.expander("گزینه‌های بیشتر"):
            primary_keyword = st.text_input(
                "کلمه کلیدی اصلی (اگر با موضوع فرق دارد)",
                placeholder="خالی بماند تا همان موضوع استفاده شود",
            )
            category_url = st.text_input("آدرس فعلی صفحه (اختیاری)", placeholder="https://example.com/bedroom-ideas/")
            word_count = st.number_input(
                "تعداد کلمات هدف",
                min_value=min_words,
                max_value=max_words,
                step=50,
                key="desired_word_count_input",
            )
            secondary_raw = st.text_area("کلمات کلیدی فرعی", placeholder="هر عبارت در یک خط", height=80)
            industries_raw = st.text_area("صنایع / مشاغل", placeholder="فقط اگر باید در مقاله بیایند", height=80)
            intents = st.multiselect(
                "نیت جستجو",
                options=list(INTENT_OPTIONS),
                default=["Commercial", "Informational"],
            )
            audience = st.text_input("مخاطب هدف", placeholder="اگر خالی بماند از توضیح وب‌سایت استنباط می‌شود")
            existing = st.text_area("محتوای فعلی صفحه (اختیاری)", height=140)
        submitted = st.form_submit_button("تولید محتوای سئو", type="primary", use_container_width=True)
    if submitted:
        article_topic = topic.strip()
        keyword = primary_keyword.strip() or article_topic
        try:
            user_input = UserInput(
                website_name=website_name.strip(),
                website_description=website_description.strip(),
                category_name=article_topic,
                primary_keyword=keyword,
                secondary_keywords=lines_to_list(secondary_raw),
                industries_professions=lines_to_list(industries_raw),
                search_intents=intents or ["Commercial", "Informational"],
                target_audience=audience.strip(),
                existing_content=existing.strip(),
                desired_word_count=int(word_count),
                category_url=category_url.strip(),
                box_style=box_style,
            )
        except ValidationError as exc:
            st.error(_format_validation_error(exc))
            return
        _run_pipeline(user_input, RunOptions())


def _strategy_tab(box: FinalSEOBox) -> None:
    st.write(box.seo_strategy.get("strategy_summary", ""))
    primary = st.text_input("کلمه کلیدی اصلی (قابل ویرایش)", value=box.primary_keyword)
    secondary = st.text_area("کلمات فرعی (هر خط یکی)", value="\n".join(box.secondary_keywords), height=120)
    industries = st.text_area("صنایع / مشاغل (هر خط یکی)", value="\n".join(box.industries), height=120)
    st.json(box.search_intent)
    with st.expander("SEOPlan کامل"):
        st.json(box.seo_strategy)
    if st.button("بازتولید با کلمات/صنایع ویرایش‌شده", key="regen_strategy"):
        user_input = _current_input(box)
        user_input.primary_keyword = primary.strip()
        user_input.secondary_keywords = lines_to_list(secondary)
        user_input.industries_professions = lines_to_list(industries)
        plan = SEOPlan.model_validate(box.seo_strategy)
        _run_pipeline(
            user_input,
            RunOptions(
                existing_plan=plan,
                existing_headings=_heading_plan_from_box(box),
                existing_article=_content_from_box(box),
                skip_existing_analysis=True,
            ),
        )


def _headings_tab(box: FinalSEOBox) -> None:
    st.caption("هدینگ‌های ویرایش‌شده در بازتولید بازنویسی خودکار نمی‌شوند.")
    raw = st.text_area("ساختار هدینگ", value=_headings_to_text(box), height=280)
    if st.button("بازتولید محتوا با هدینگ‌های ویرایش‌شده", key="regen_headings"):
        headings = _parse_headings(raw, box.h1)
        user_input = _current_input(box)
        _run_pipeline(
            user_input,
            RunOptions(
                locks=ManualLocks(headings=True),
                existing_plan=SEOPlan.model_validate(box.seo_strategy),
                existing_headings=headings,
                existing_article=_content_from_box(box),
                skip_existing_analysis=True,
            ),
        )


def _content_tab(box: FinalSEOBox) -> None:
    title = st.text_input("عنوان سئو", value=box.meta_title)
    desc = st.text_area("توضیحات متا", value=box.meta_description, height=80)
    cta = st.text_area("CTA", value=box.cta, height=80)
    st.markdown(
        f'<div class="article-preview">{sanitize_html(box.content)}</div>',
        unsafe_allow_html=True,
    )
    if st.button("اعمال عنوان/متا/CTA و اعتبارسنجی مجدد", key="regen_meta"):
        article = _content_from_box(box)
        article.metadata.seo_title = title
        article.metadata.meta_description = desc
        article.cta = cta
        _run_pipeline(
            _current_input(box),
            RunOptions(
                locks=ManualLocks(seo_title=True, meta_description=True, cta=True, headings=True),
                existing_plan=SEOPlan.model_validate(box.seo_strategy),
                existing_headings=_heading_plan_from_box(box),
                existing_article=article,
                skip_existing_analysis=True,
                skip_generation=True,
            ),
        )


def _validation_tab(box: FinalSEOBox) -> None:
    validation = box.validation or {}
    st.metric("امتیاز کل سئو", box.seo_score)
    st.write(f"وضعیت: **{box.status}** | بازه: {validation.get('band', '')} | تعداد اصلاح: {box.revision_count}")
    cats = validation.get("category_scores") or {}
    if cats:
        cols = st.columns(len(cats))
        for col, (name, score) in zip(cols, cats.items(), strict=False):
            col.metric(name, score)
    if box.cannibalization_warnings:
        for warning in box.cannibalization_warnings:
            st.warning(warning.message)
    st.subheader("چک‌لیست")
    for item in validation.get("checks") or []:
        status = item.get("status", "")
        icon = {"PASS": "✅", "WARNING": "⚠️", "FAIL": "❌"}.get(status, "•")
        st.write(f"{icon} **{item.get('title')}** (`{item.get('code')}`) — {item.get('message')}")
        if item.get("recommendation") and status != "PASS":
            st.caption(item["recommendation"])
    failed = validation.get("failed_checks") or []
    if failed:
        st.subheader("موارد ردشده")
        st.write(", ".join(failed))
    recs = validation.get("recommendations") or []
    if recs:
        st.subheader("پیشنهادها")
        for rec in recs:
            st.write(f"- {rec}")
    if box.status == "human_review_required":
        st.error("Human Review Required — پس از ۳ اصلاح هنوز به حد نصاب نرسیده است.")


def _final_tab(box: FinalSEOBox) -> None:
    style_label = "ساده" if box.box_style == "simple" else "کامل"
    st.caption(f"نوع SEO Box: {style_label} — {box.word_count} کلمه")
    st.json(box.export_payload())
    stem = box.primary_keyword.replace(" ", "-")[:40]
    try:
        json_export = seo_box_to_json(box)
        markdown_export = seo_box_to_markdown(box)
        html_export = seo_box_to_html_document(box)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Export failed: %s", type(exc).__name__)
        st.error(public_error_message(AppError(ErrorCategory.EXPORT_ERROR, "خروجی فایل ساخته نشد.")))
        return
    dl = st.columns(3)
    dl[0].download_button("JSON", json_export, file_name=f"{stem}-seo-box.json", mime="application/json")
    dl[1].download_button("Markdown", markdown_export, file_name=f"{stem}-seo-box.md", mime="text/markdown")
    dl[2].download_button("HTML", html_export, file_name=f"{stem}-seo-box.html", mime="text/html")


def _run_pipeline(user_input: UserInput, options: RunOptions) -> None:
    status = st.status("در حال اجرای پایپلاین...", expanded=True)

    def on_progress(stage: str, message: str) -> None:
        status.write(f"**{stage}** — {message}")

    try:
        client = VertexClient()
        box = ProductionSeoOrchestrator(client, store=get_run_store(), on_progress=on_progress).run(
            user_input, options, client_key=_client_key()
        )
        st.session_state["seo_box"] = box
        st.session_state["user_input"] = user_input
        label = "آماده شد" if box.status in {"excellent", "good"} else f"تمام شد — {box.status}"
        status.update(label=label, state="complete")
        st.rerun()
    except VertexAuthError as exc:
        status.update(label="خطای احراز هویت", state="error")
        st.error(public_error_message(exc))
    except VertexGenerationError as exc:
        status.update(label="خطای تولید", state="error")
        st.error(public_error_message(exc))
        logger.error("Generation failed: %s", type(exc).__name__)
    except Exception as exc:  # noqa: BLE001
        status.update(label="خطای پیش‌بینی‌نشده", state="error")
        st.error(public_error_message(exc))
        logger.error("Pipeline failed: %s", type(exc).__name__)


def _client_key() -> str:
    try:
        return st.context.ip_address or "unknown"
    except Exception:  # noqa: BLE001
        return "local"


def _current_input(box: FinalSEOBox) -> UserInput:
    previous = st.session_state.get("user_input")
    if isinstance(previous, UserInput):
        return previous.model_copy(deep=True)
    low, high = word_count_bounds(box.box_style)
    count = box.word_count or default_word_count(box.box_style)
    description = box.website_description.strip() or f"وب‌سایتی دربارهٔ {box.category}."
    return UserInput(
        website_name=box.website_name,
        website_description=description,
        category_name=box.category,
        primary_keyword=box.primary_keyword,
        secondary_keywords=box.secondary_keywords,
        industries_professions=box.industries,
        box_style=box.box_style,
        desired_word_count=min(max(count, low), high),
    )


def _heading_plan_from_box(box: FinalSEOBox) -> HeadingPlan:
    nodes = [
        HeadingNode(level=item.get("level", "H2"), text=item.get("text", ""))
        for item in box.headings
        if item.get("text")
    ]
    if not any(node.level == "H1" for node in nodes) and box.h1:
        nodes = [HeadingNode(level="H1", text=box.h1), *nodes]
    return HeadingPlan(h1=box.h1, headings=nodes, architecture_rationale="edited")


def _content_from_box(box: FinalSEOBox) -> Content:
    return Content(
        h1=box.h1,
        article_html=box.content,
        article_markdown=box.content_markdown,
        cta=box.cta,
        faqs=box.faq,
        metadata=Metadata(
            seo_title=box.meta_title,
            meta_description=box.meta_description,
            url_slug=box.slug,
            preserve_existing_url=box.existing_url_preserved,
        ),
        internal_links=box.internal_links,
        word_count=box.word_count,
    )


def _headings_to_text(box: FinalSEOBox) -> str:
    lines = []
    for item in box.headings:
        lines.append(f"{item.get('level', 'H2')}: {item.get('text', '')}")
    if not lines and box.h1:
        lines.append(f"H1: {box.h1}")
    return "\n".join(lines)


def _parse_headings(raw: str, fallback_h1: str) -> HeadingPlan:
    nodes: list[HeadingNode] = []
    last_h2 = None
    for line in raw.splitlines():
        if ":" not in line:
            continue
        level, text = line.split(":", 1)
        level = level.strip().upper()
        text = text.strip()
        if level not in {"H1", "H2", "H3"} or not text:
            continue
        parent = last_h2 if level == "H3" else None
        if level == "H2":
            last_h2 = text
        nodes.append(HeadingNode(level=level, text=text, parent_h2=parent, locked=True))
    h1 = next((node.text for node in nodes if node.level == "H1"), fallback_h1)
    return HeadingPlan(h1=h1, headings=nodes, architecture_rationale="user-edited")


def _format_validation_error(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = " / ".join(str(item) for item in err.get("loc", []))
        parts.append(f"{loc}: {err.get('msg')}")
    return "ورودی نامعتبر است:\n" + "\n".join(parts)


if __name__ == "__main__":
    main()
