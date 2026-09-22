from src.persian import contains_term, count_words, similarity
from src.scoring import evaluate, heading_duplicates, keyword_density, validate_metadata
from src.validators import validate_headings_locally
from tests.conftest import sample_article, sample_headings, sample_html, sample_input, sample_plan, sample_topic_map


def test_word_count_bounds():
    short = sample_article(article_html="<h1>قالب استوری اینستاگرام</h1><p>کوتاه</p>")
    result = evaluate(user_input=sample_input(), plan=sample_plan(), headings=sample_headings(), article=short)
    assert "too_short" in result.hard_fails or "too_short" in result.failed_checks


def test_h1_count_and_hierarchy():
    plan = sample_headings()
    local = validate_headings_locally(plan, sample_input())
    assert local.passed
    broken = sample_headings()
    broken.headings = [item for item in broken.headings if item.level != "H1"]
    broken.headings = [item for item in broken.headings if item.level == "H3"]
    local2 = validate_headings_locally(broken, sample_input())
    assert not local2.passed


def test_heading_similarity_flags_duplicates():
    dupes = heading_duplicates(["قالب استوری برای فروشگاه‌ها", "قالب استوری برای فروشگاه‌ها"])
    assert dupes
    assert similarity("قالب استوری فروشگاه", "ویدئو دندانپزشکی کلینیک") < 0.5


def test_primary_keyword_and_stuffing():
    html = sample_html()
    assert contains_term(html, "قالب استوری اینستاگرام")
    stuffed = ("قالب استوری اینستاگرام " * 80) + sample_html(words=200)
    density = keyword_density(stuffed, "قالب استوری اینستاگرام")
    assert density > 0.05
    article = sample_article(article_html=f"<h1>قالب استوری اینستاگرام</h1><p>{stuffed}</p>")
    result = evaluate(user_input=sample_input(), plan=sample_plan(), headings=sample_headings(), article=article)
    assert any(code.startswith("keyword_stuffing") for code in result.failed_checks + result.hard_fails)


def test_metadata_and_slug():
    article = sample_article()
    issues = validate_metadata(article.metadata, "قالب استوری اینستاگرام", "https://example.com/story/")
    assert issues == []
    empty = sample_article()
    empty.metadata.seo_title = ""
    empty.metadata.meta_description = ""
    result = evaluate(user_input=sample_input(), plan=sample_plan(), headings=sample_headings(), article=empty)
    assert "missing_title" in result.hard_fails
    assert "missing_meta" in result.hard_fails


def test_faq_and_internal_links():
    article = sample_article()
    article.faqs = []
    article.internal_links = []
    result = evaluate(user_input=sample_input(), plan=sample_plan(), headings=sample_headings(), article=article)
    assert "faq_count" in result.failed_checks
    assert "internal_links" in result.warnings or "internal_links" in result.failed_checks


def test_simple_style_allows_short_copy_without_faq():
    from src.persian import count_words
    from src.schemas import HeadingNode, HeadingPlan

    body = ("استوری برای ثبت لحظه و تعامل در شبکه‌های اجتماعی استفاده می‌شود. " * 40)
    html = f"""
    <article>
      <h1>قالب استوری</h1>
      <p>قالب استوری اینستاگرام برای ساخت استوری با قالب آماده به کار می‌رود. {body}</p>
      <h2>چرا استوری در شبکه‌های اجتماعی مهم است؟</h2>
      <p>{body}</p>
      <h2>مزایای استوری هدفمند برای کسب‌وکار</h2>
      <ul>
        <li>ماندگار شدن معرفی محصول در ذهن مخاطب</li>
        <li>آماده‌سازی سریع بدون طراحی از صفر</li>
      </ul>
      <p>برای آماده‌کردن استوری می‌توانید به نمونه مراجعه کنید و متن و تصویر را در قالب آماده جایگزین کنید.</p>
    </article>
    """
    headings = HeadingPlan(
        h1="قالب استوری",
        headings=[
            HeadingNode(level="H1", text="قالب استوری"),
            HeadingNode(level="H2", text="چرا استوری در شبکه‌های اجتماعی مهم است؟"),
            HeadingNode(level="H2", text="مزایای استوری هدفمند برای کسب‌وکار"),
        ],
    )
    article = sample_article(article_html=html)
    article.faqs = []
    article.internal_links = []
    article.word_count = count_words(html)
    result = evaluate(
        user_input=sample_input(box_style="simple", desired_word_count=500),
        plan=sample_plan(),
        headings=headings,
        article=article,
        content_map=sample_topic_map(),
    )
    assert "too_short" not in result.hard_fails
    assert "too_short" not in result.failed_checks
    faq = next(item for item in result.checks if item.code == "faq_count")
    assert faq.status in {"PASS", "WARNING"}
    h1 = next(item for item in result.checks if item.code == "h1_topic")
    assert h1.status == "PASS"


def test_product_feature_accuracy():
    html = sample_html() + "<p>تضمین ۱۰۰٪ نتیجه برای هر مشتری</p>"
    article = sample_article(article_html=html)
    result = evaluate(user_input=sample_input(), plan=sample_plan(), headings=sample_headings(), article=article)
    assert "forbidden_claim" in result.hard_fails or "forbidden_claim" in result.failed_checks


def test_persian_filler_and_half_space():
    html = sample_html() + "<p>در دنیای امروز بدون شک می شود گفت لازم به ذکر است.</p>"
    article = sample_article(article_html=html)
    result = evaluate(user_input=sample_input(), plan=sample_plan(), headings=sample_headings(), article=article)
    codes = {item.code: item.status for item in result.checks}
    assert codes.get("ai_filler") in {"WARNING", "FAIL"}
    assert codes.get("half_space") in {"WARNING", "FAIL", "PASS"}


def test_brand_overuse_and_optional_industry():
    html = sample_html()
    branded = html.replace("<h1>", "<h1>نمونه ")
    branded = branded + ("<p>نمونه نمونه نمونه</p>" * 12)
    article = sample_article(article_html=branded)
    result = evaluate(
        user_input=sample_input(),
        plan=sample_plan(),
        headings=sample_headings(),
        article=article,
        content_map=sample_topic_map(),
    )
    assert "brand_overuse" in result.failed_checks or "brand_overuse" in {item.code for item in result.checks if item.status != "PASS"}
    from src.schemas import IndustryUse

    skipped = sample_topic_map()
    skipped.industry_uses = [IndustryUse(name="نامرتبط", relevance="SKIP", reason="بی‌ربط")]
    html2 = sample_html() + "<p>نامرتبط در هر پاراگراف نامرتبط نامرتبط</p>"
    result2 = evaluate(
        user_input=sample_input(),
        plan=sample_plan(),
        headings=sample_headings(),
        article=sample_article(article_html=html2),
        content_map=skipped,
    )
    assert any(item.code == "industries_covered" and item.status != "PASS" for item in result2.checks)


def test_word_count_is_range_not_exact_target():
    article = sample_article()
    article.word_count = count_words(article.article_html)
    result = evaluate(user_input=sample_input(desired_word_count=1000), plan=sample_plan(), headings=sample_headings(), article=article)
    assert "word_count_drift" not in result.failed_checks
    assert "word_count_drift" not in result.hard_fails
    article = sample_article()
    article.word_count = count_words(article.article_html)
    result = evaluate(user_input=sample_input(), plan=sample_plan(), headings=sample_headings(), article=article)
    assert set(result.category_scores) == {
        "technical",
        "keyword",
        "intent",
        "content",
        "heading",
        "persian",
        "product",
        "trust",
    }
    assert 0 <= result.overall_score <= 100
    assert result.band in {"Excellent", "Good", "Needs Improvement", "Revision Required"}
