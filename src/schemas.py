from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from src.config import (
    DEFAULT_WORD_COUNT,
    max_existing_content_length,
    max_list_items,
    max_request_chars,
    max_topic_length,
    max_website_description_length,
    word_count_bounds,
)

IntentName = Literal[
    "Informational",
    "Commercial",
    "Transactional",
    "Navigational",
    "Mixed",
]
KeywordKind = Literal[
    "exact",
    "variant",
    "semantic",
    "entity",
    "profession",
    "industry",
    "service",
    "intent",
]
KeywordUsage = Literal["MUST_USE", "OPTIONAL", "NOT_RELEVANT"]
KeywordLocation = Literal[
    "H1",
    "H2",
    "H3",
    "Introduction",
    "Body",
    "FAQ",
    "Meta description",
]
HeadingLevel = Literal["H1", "H2", "H3"]
ContentAction = Literal["KEEP", "IMPROVE", "REWRITE", "REMOVE", "ADD"]
Severity = Literal["info", "warning", "fail"]
CheckStatus = Literal["PASS", "WARNING", "FAIL"]
RunStatus = Literal[
    "excellent",
    "good",
    "needs_improvement",
    "revision_required",
    "human_review_required",
]
BoxStyle = Literal["full", "simple"]


class WebsiteContext(BaseModel):
    """Inferred from the short website description inside the existing planning call."""

    website_name: str = ""
    website_description: str = ""
    business_type: str = ""
    audience: str = ""
    products_or_services: list[str] = Field(default_factory=list)
    domain_context: str = ""


class UserInput(BaseModel):
    website_name: str = ""
    website_description: str = ""
    website_context: WebsiteContext | None = None
    category_name: str
    primary_keyword: str
    secondary_keywords: list[str] = Field(default_factory=list)
    industries_professions: list[str] = Field(default_factory=list)
    search_intents: list[str] = Field(default_factory=lambda: ["Commercial", "Informational"])
    target_audience: str = ""
    existing_content: str = ""
    desired_word_count: int = DEFAULT_WORD_COUNT
    category_url: str = ""
    category_type: str = ""
    box_style: BoxStyle = "full"

    @field_validator("website_name", mode="before")
    @classmethod
    def strip_website_name(cls, value: str | None) -> str:
        text = (value or "").strip()
        if len(text) > 120:
            raise ValueError("نام وب‌سایت باید کوتاه‌تر از ۱۲۰ نویسه باشد.")
        return text

    @field_validator("website_description")
    @classmethod
    def strip_website_description(cls, value: str) -> str:
        text = (value or "").strip()
        limit = max_website_description_length()
        if len(text) < 12:
            raise ValueError("توضیح کوتاه وب‌سایت الزامی است (یک تا سه جمله).")
        if len(text) > limit:
            raise ValueError(f"توضیح وب‌سایت باید کوتاه بماند؛ حداکثر {limit} نویسه.")
        return text

    @field_validator("category_name", "primary_keyword")
    @classmethod
    def strip_required(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("این فیلد الزامی است.")
        limit = max_topic_length()
        if len(text) > limit:
            raise ValueError(f"موضوع یا کلمه کلیدی باید کوتاه‌تر از {limit} نویسه باشد.")
        return text

    @field_validator("existing_content", "target_audience", "category_url")
    @classmethod
    def limit_optional_text(cls, value: str) -> str:
        text = (value or "").strip()
        if len(text) > max_existing_content_length():
            raise ValueError(
                f"این فیلد بلندتر از حد مجاز ({max_existing_content_length()} نویسه) است."
            )
        return text

    @field_validator("secondary_keywords", "industries_professions")
    @classmethod
    def limit_lists(cls, value: list[str]) -> list[str]:
        items = [str(item).strip() for item in (value or []) if str(item).strip()]
        cap = max_list_items()
        if len(items) > cap:
            raise ValueError(f"تعداد آیتم‌ها بیشتر از حد مجاز ({cap}) است.")
        topic_limit = max_topic_length()
        for item in items:
            if len(item) > topic_limit:
                raise ValueError(f"هر عبارت باید کوتاه‌تر از {topic_limit} نویسه باشد.")
        return items

    @model_validator(mode="before")
    @classmethod
    def default_words_for_style(cls, data):
        if isinstance(data, dict) and data.get("box_style") == "simple" and "desired_word_count" not in data:
            from src.config import SIMPLE_DEFAULT_WORD_COUNT

            data["desired_word_count"] = SIMPLE_DEFAULT_WORD_COUNT
        return data

    @model_validator(mode="after")
    def word_count_range(self) -> "UserInput":
        low, high = word_count_bounds(self.box_style)
        if self.desired_word_count < low or self.desired_word_count > high:
            label = "ساده" if self.box_style == "simple" else "کامل"
            raise ValueError(f"برای حالت {label} تعداد کلمات باید بین {low} و {high} باشد.")
        blob = " ".join(
            [
                self.website_name,
                self.website_description,
                self.category_name,
                self.primary_keyword,
                self.existing_content,
                self.target_audience,
                self.category_url,
                " ".join(self.secondary_keywords),
                " ".join(self.industries_professions),
            ]
        )
        limit = max_request_chars()
        if len(blob) > limit:
            raise ValueError(f"حجم درخواست بیشتر از حد مجاز ({limit} نویسه) است.")
        return self

    @property
    def is_simple(self) -> bool:
        return self.box_style == "simple"


class ExistingBlock(BaseModel):
    heading: str = ""
    level: str = ""
    summary: str = ""
    action: ContentAction = "IMPROVE"
    reason: str = ""


class ExistingContentAnalysis(BaseModel):
    current_h1: str = ""
    current_h2s: list[str] = Field(default_factory=list)
    current_h3s: list[str] = Field(default_factory=list)
    existing_primary_keywords: list[str] = Field(default_factory=list)
    existing_secondary_keywords: list[str] = Field(default_factory=list)
    semantic_terms: list[str] = Field(default_factory=list)
    important_claims: list[str] = Field(default_factory=list)
    product_features: list[str] = Field(default_factory=list)
    internal_links: list[str] = Field(default_factory=list)
    repetitions: list[str] = Field(default_factory=list)
    thin_sections: list[str] = Field(default_factory=list)
    outdated_claims: list[str] = Field(default_factory=list)
    seo_weaknesses: list[str] = Field(default_factory=list)
    missing_topics: list[str] = Field(default_factory=list)
    missing_search_intent: list[str] = Field(default_factory=list)
    heading_problems: list[str] = Field(default_factory=list)
    blocks: list[ExistingBlock] = Field(default_factory=list)
    useful_facts_to_preserve: list[str] = Field(default_factory=list)
    summary: str = ""


class KeywordItem(BaseModel):
    term: str
    kind: KeywordKind
    usage: KeywordUsage
    locations: list[KeywordLocation] = Field(default_factory=list)
    notes: str = ""


class SearchIntent(BaseModel):
    primary_intent: str = ""
    secondary_intents: list[str] = Field(default_factory=list)
    user_jobs_to_be_done: list[str] = Field(default_factory=list)
    questions_to_answer: list[str] = Field(default_factory=list)
    commercial_signals: list[str] = Field(default_factory=list)
    informational_signals: list[str] = Field(default_factory=list)
    transactional_signals: list[str] = Field(default_factory=list)
    how_content_should_satisfy_intent: str = ""


class IndustryUse(BaseModel):
    name: str
    relevance: Literal["USE", "OPTIONAL", "SKIP"] = "OPTIONAL"
    role: str = ""
    reason: str = ""


class SemanticTopic(BaseModel):
    topic: str
    why: str = ""
    heading_worthy: bool = True
    priority: Literal["core", "supporting", "optional"] = "supporting"


class ContentMap(BaseModel):
    core_topic: str
    topic_interpretation: str = ""
    category_type: str = ""
    primary_search_intent: str = ""
    secondary_intents: list[str] = Field(default_factory=list)
    user_questions: list[str] = Field(default_factory=list)
    semantic_topics: list[SemanticTopic] = Field(default_factory=list)
    related_concepts: list[str] = Field(default_factory=list)
    industry_uses: list[IndustryUse] = Field(default_factory=list)
    relevant_keyword_variants: list[str] = Field(default_factory=list)
    relevant_entities: list[str] = Field(default_factory=list)
    product_relevance: str = ""
    product_mention_policy: Literal["minimal", "supporting_section", "brand_page"] = "supporting_section"
    commercial_opportunities: list[str] = Field(default_factory=list)
    topics_to_exclude: list[str] = Field(default_factory=list)
    recommended_word_count: int = DEFAULT_WORD_COUNT
    length_rationale: str = ""


class SEOPlan(BaseModel):
    category: str = ""
    category_type: str = ""
    primary_keyword: str
    secondary_keywords: list[str] = Field(default_factory=list)
    keyword_variants: list[str] = Field(default_factory=list)
    semantic_keywords: list[str] = Field(default_factory=list)
    related_entities: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    professions: list[str] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
    use_cases: list[str] = Field(default_factory=list)
    search_intent: SearchIntent = Field(default_factory=SearchIntent)
    keyword_map: list[KeywordItem] = Field(default_factory=list)
    user_questions: list[str] = Field(default_factory=list)
    content_gaps: list[str] = Field(default_factory=list)
    potential_faq_topics: list[str] = Field(default_factory=list)
    recommended_internal_link_topics: list[str] = Field(default_factory=list)
    recommended_heading_topics: list[str] = Field(default_factory=list)
    topics_to_exclude: list[str] = Field(default_factory=list)
    recommended_word_count: int = DEFAULT_WORD_COUNT
    strategy_summary: str = ""
    commercial_placement: str = ""
    heading_topics_from_map: list[str] = Field(default_factory=list)


class HeadingNode(BaseModel):
    level: HeadingLevel
    text: str
    purpose: str = ""
    parent_h2: Optional[str] = None
    related_intents: list[str] = Field(default_factory=list)
    related_keywords: list[str] = Field(default_factory=list)
    locked: bool = False


class HeadingPlan(BaseModel):
    h1: str
    headings: list[HeadingNode] = Field(default_factory=list)
    architecture_rationale: str = ""
    why_not_generic_template: str = ""
    category_specificity_notes: str = ""


class FaqItem(BaseModel):
    question: str
    answer: str


class FAQ(BaseModel):
    items: list[FaqItem] = Field(default_factory=list)


class InternalLinkSuggestion(BaseModel):
    anchor: str
    suggested_url: str
    topic: str = ""
    reason: str = ""
    placement: str = ""
    url_verified: bool = False


class Metadata(BaseModel):
    seo_title: str = ""
    meta_description: str = ""
    url_slug: str = ""
    preserve_existing_url: bool = False
    title_character_count: int = 0
    description_character_count: int = 0


class Content(BaseModel):
    h1: str
    article_html: str
    article_markdown: str = ""
    introduction_html: str = ""
    cta: str = ""
    faqs: list[FaqItem] = Field(default_factory=list)
    metadata: Metadata = Field(default_factory=Metadata)
    internal_links: list[InternalLinkSuggestion] = Field(default_factory=list)
    word_count: int = 0
    notes: str = ""


class ChecklistItem(BaseModel):
    code: str
    category: str
    title: str
    status: CheckStatus
    message: str
    recommendation: str = ""
    hard_fail: bool = False
    target: str = ""


class ValidationIssue(BaseModel):
    code: str
    severity: Severity
    message: str
    target: str = ""
    suggestion: str = ""


class CategoryScore(BaseModel):
    name: str
    weight: float
    score: int
    status: CheckStatus


class Validation(BaseModel):
    overall_score: int = 0
    band: str = ""
    category_scores: dict[str, int] = Field(default_factory=dict)
    category_details: list[CategoryScore] = Field(default_factory=list)
    checks: list[ChecklistItem] = Field(default_factory=list)
    hard_fails: list[str] = Field(default_factory=list)
    failed_checks: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    weak_sections: list[str] = Field(default_factory=list)
    revision_required: bool = False
    passed: bool = False
    summary: str = ""


class LLMQualitativeReview(BaseModel):
    intent_score: int = 80
    content_quality_score: int = 80
    persian_score: int = 80
    product_score: int = 80
    trust_score: int = 80
    topic_content_ratio: float = 0.8
    commercial_content_ratio: float = 0.2
    brand_overuse: bool = False
    semantic_coverage: int = 80
    search_intent_coverage: int = 80
    keyword_naturalness: int = 80
    filler_ratio: float = 0.0
    issues: list[ChecklistItem] = Field(default_factory=list)
    weak_sections: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    hallucination_detected: bool = False
    revision_action: Literal[
        "none",
        "revise_architecture",
        "revise_passages",
        "reduce_brand",
        "add_semantic_topics",
        "remove_filler",
        "remove_product_claims",
        "remove_irrelevant_entities",
    ] = "none"
    revision_targets: list[str] = Field(default_factory=list)
    revision_instructions: str = ""
    summary: str = ""


class CannibalizationWarning(BaseModel):
    other_category: str
    other_keyword: str
    similarity: float
    message: str


class FinalSEOBox(BaseModel):
    category: str
    category_type: str = ""
    primary_keyword: str
    secondary_keywords: list[str] = Field(default_factory=list)
    semantic_keywords: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    search_intent: dict = Field(default_factory=dict)
    seo_strategy: dict = Field(default_factory=dict)
    meta_title: str = ""
    meta_description: str = ""
    slug: str = ""
    h1: str = ""
    headings: list[dict] = Field(default_factory=list)
    content: str = ""
    content_markdown: str = ""
    faq: list[FaqItem] = Field(default_factory=list)
    internal_links: list[InternalLinkSuggestion] = Field(default_factory=list)
    cta: str = ""
    word_count: int = 0
    website_name: str = ""
    website_description: str = ""
    seo_score: int = 0
    validation: dict = Field(default_factory=dict)
    revision_count: int = 0
    status: RunStatus = "revision_required"
    existing_url_preserved: bool = False
    pipeline_notes: list[str] = Field(default_factory=list)
    cannibalization_warnings: list[CannibalizationWarning] = Field(default_factory=list)
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    model: str = ""
    topic_map: dict = Field(default_factory=dict)
    box_style: BoxStyle = "full"

    def export_payload(self) -> dict:
        return {
            "category": self.category,
            "category_type": self.category_type,
            "primary_keyword": self.primary_keyword,
            "secondary_keywords": self.secondary_keywords,
            "semantic_keywords": self.semantic_keywords,
            "industries": self.industries,
            "search_intent": self.search_intent,
            "seo_strategy": self.seo_strategy,
            "meta_title": self.meta_title,
            "meta_description": self.meta_description,
            "slug": self.slug,
            "h1": self.h1,
            "headings": self.headings,
            "content": self.content,
            "faq": [item.model_dump() for item in self.faq],
            "internal_links": [item.model_dump() for item in self.internal_links],
            "website_name": self.website_name,
            "website_description": self.website_description,
            "cta": self.cta,
            "word_count": self.word_count,
            "seo_score": self.seo_score,
            "validation": self.validation,
            "revision_count": self.revision_count,
            "status": self.status,
            "box_style": self.box_style,
        }


class PlanningBundle(BaseModel):
    website_context: WebsiteContext = Field(default_factory=WebsiteContext)
    topic_map: ContentMap
    seo_plan: SEOPlan
    heading_plan: HeadingPlan


class ManualLocks(BaseModel):
    headings: bool = False
    seo_title: bool = False
    meta_description: bool = False
    cta: bool = False


class RunOptions(BaseModel):
    locks: ManualLocks = Field(default_factory=ManualLocks)
    existing_plan: Optional[SEOPlan] = None
    existing_headings: Optional[HeadingPlan] = None
    existing_article: Optional[Content] = None
    skip_existing_analysis: bool = False
    skip_generation: bool = False
    existing_analysis: Optional[ExistingContentAnalysis] = None
    existing_topic_map: Optional[ContentMap] = None


# Backward-compatible aliases used by older modules/tests.
SeoStrategy = SEOPlan
KeywordMap = SEOPlan
IntentAnalysis = SearchIntent
ContentArchitecture = HeadingPlan
MetadataPack = Metadata
GeneratedArticle = Content
SeoBox = FinalSEOBox
ValidationReport = Validation
HeadingValidationResult = Validation
PackagingResult = Content
