from __future__ import annotations

from collections.abc import Callable

from src.config import (
    CANNIBALIZATION_THRESHOLD,
    MAX_CONTENT_REVISIONS,
    default_word_count,
    word_count_bounds,
)
from src.exporters import html_to_markdown, normalize_slug
from src.llm import VertexClient, VertexGenerationError
from src.logutil import log_event
from src.persian import char_count, count_words, extract_headings, strip_html
from src.product import merge_inferred_context, seed_website_context
from src.prompts import compact_headings, compact_seo_plan, compact_topic_map, dump, existing_summary_text
from src.prompts.architecture import heading_planner_system, heading_planner_user
from src.prompts.content import content_system, content_user
from src.prompts.planning import planning_bundle_system, planning_bundle_user
from src.prompts.validation import revision_system, revision_user
from src.prompts.versions import PROMPT_VERSIONS
from src.schemas import (
    Content,
    ContentMap,
    ExistingContentAnalysis,
    FinalSEOBox,
    HeadingPlan,
    IndustryUse,
    LLMQualitativeReview,
    PlanningBundle,
    RunOptions,
    SemanticTopic,
    SEOPlan,
    UserInput,
    Validation,
)
from src.scoring import evaluate, revision_action_from_validation, status_from_score
from src.storage import Store

ProgressCb = Callable[[str, str], None]


class SeoBoxPipeline:
    def __init__(
        self,
        client: VertexClient,
        on_progress: ProgressCb | None = None,
        store: Store | None = None,
    ) -> None:
        self.client = client
        self.on_progress = on_progress or (lambda _stage, _msg: None)
        self.store = store or Store()

    def run(self, user_input: UserInput, options: RunOptions | None = None) -> FinalSEOBox:
        options = options or RunOptions()
        notes: list[str] = []
        revision_count = 0
        seed_website_context(user_input)
        try:
            existing = self._analyze_existing(user_input, options)
            existing_summary = existing_summary_text(existing)
            cannibal = self.store.cannibalization_warnings(
                user_input.category_name,
                user_input.primary_keyword,
                CANNIBALIZATION_THRESHOLD,
                website_name=user_input.website_name,
            )
            if cannibal:
                notes.append(cannibal[0].message)
                self._emit("KEYWORD_REGISTRY", cannibal[0].message)

            topic_map, plan, headings = self._plan_bundle(user_input, existing_summary, options)
            target_words = _clamp_words(
                topic_map.recommended_word_count or plan.recommended_word_count or user_input.desired_word_count,
                user_input.box_style,
            )
            notes.append(f"ترجیح طول بر اساس پیچیدگی موضوع: {target_words}")
            if user_input.is_simple:
                notes.append("حالت SEO Box: ساده")
            notes.append("مسیر سریع: برنامه‌ریزی یک‌مرحله‌ای و اعتبارسنجی محلی")

            if options.skip_generation and options.existing_article is not None:
                self._emit("CONTENT_GENERATION", "تولید محتوا رد شد؛ از نسخه ویرایش‌شده استفاده می‌شود.")
                article = _apply_locks(options.existing_article.model_copy(deep=True), options)
                article.word_count = count_words(article.article_html)
                validation, _qual = self._evaluate(
                    user_input, plan, headings, article, topic_map, cannibal
                )
                revision_count = 0
            else:
                article = self._generate_content(
                    user_input, topic_map, plan, headings, existing_summary, target_words, options
                )
                article = _apply_locks(article, options)
                article, headings, validation, revision_count = self._validate_and_revise(
                    user_input, topic_map, plan, headings, article, existing_summary, target_words, options, cannibal
                )
            box = self._to_box(
                user_input, topic_map, plan, headings, article, validation, revision_count, notes, cannibal
            )
            try:
                self.store.save_run(user_input, box, box.model, PROMPT_VERSIONS)
            except Exception as exc:  # noqa: BLE001
                log_event("STORAGE", "ذخیره SQLite ناموفق بود", category=user_input.category_name, error=str(exc))
                notes.append("ذخیره SQLite انجام نشد.")
                box.pipeline_notes = notes
            self._emit("SEO_BOX", f"بسته نهایی آماده شد. امتیاز {box.seo_score} — {box.status}")
            log_event(
                "FINAL",
                "pipeline complete",
                category=user_input.category_name,
                model=self.client.last_model,
                score=box.seo_score,
                revisions=revision_count,
            )
            return box
        except VertexGenerationError as exc:
            log_event(
                "ERROR",
                "generation failed",
                category=user_input.category_name,
                model=self.client.last_model,
                error=str(exc),
                level=40,
            )
            if "invalid_structured_output" in str(exc):
                raise VertexGenerationError("خروجی ساخت‌یافته نامعتبر بود. مرحله را دوباره اجرا کنید.") from exc
            raise

    def _emit(self, stage: str, message: str) -> None:
        log_event(stage, message, model=getattr(self.client, "last_model", ""))
        self.on_progress(stage, message)

    def _analyze_existing(
        self, user_input: UserInput, options: RunOptions
    ) -> ExistingContentAnalysis | None:
        if options.existing_analysis is not None:
            return options.existing_analysis
        if options.skip_existing_analysis or not user_input.existing_content.strip():
            self._emit("EXISTING_CONTENT", "محتوای فعلی نیست یا قبلاً تحلیل شده.")
            return None
        self._emit("EXISTING_CONTENT", "خلاصهٔ محلی محتوای فعلی...")
        return _existing_content_locally(user_input.existing_content)

    def _plan_bundle(
        self,
        user_input: UserInput,
        existing_summary: str | None,
        options: RunOptions,
    ) -> tuple[ContentMap, SEOPlan, HeadingPlan]:
        topic_map = options.existing_topic_map
        plan = options.existing_plan
        headings = options.existing_headings
        if plan is not None:
            plan = plan.model_copy(deep=True)
            plan.primary_keyword = user_input.primary_keyword
            plan.secondary_keywords = user_input.secondary_keywords
            plan.category = user_input.category_name
            if topic_map is None:
                topic_map = _topic_map_from_plan(plan, user_input)
                self._emit("TOPIC_INTERPRETATION", "نقشهٔ موضوعی از استراتژی موجود ساخته شد.")
            else:
                self._emit("TOPIC_INTERPRETATION", "نقشهٔ موضوعی موجود استفاده شد.")
            self._emit("SEO_STRATEGY", "استراتژی موجود با ورودی ویرایش‌شده به‌روز شد.")
        if headings is not None:
            self._emit("HEADING_PLANNING", "هدینگ موجود حفظ شد.")
        if topic_map is not None and plan is not None and headings is not None:
            return _finalize_plans(user_input, topic_map, plan, headings)
        if topic_map is not None and plan is not None:
            self._emit("HEADING_PLANNING", "معماری هدینگ از نقشهٔ معنایی...")
            headings = self.client.generate_json(
                stage="heading_planning",
                system=heading_planner_system(user_input),
                user=heading_planner_user(
                    user_input, compact_topic_map(topic_map), compact_seo_plan(plan), existing_summary, None
                ),
                schema=HeadingPlan,
                kind="analysis",
                temperature=0.45,
            )
            return _finalize_plans(user_input, topic_map, plan, headings)
        self._emit("SEO_PLANNING", "برنامه‌ریزی یک‌مرحله‌ای موضوع، استراتژی و هدینگ...")
        bundle = self.client.generate_json(
            stage="planning_bundle",
            system=planning_bundle_system(user_input),
            user=planning_bundle_user(user_input, existing_summary),
            schema=PlanningBundle,
            kind="analysis",
            temperature=0.35,
        )
        merge_inferred_context(user_input, bundle.website_context)
        topic_map = topic_map or bundle.topic_map
        plan = plan or bundle.seo_plan
        headings = headings or bundle.heading_plan
        return _finalize_plans(user_input, topic_map, plan, headings)

    def _generate_content(
        self,
        user_input: UserInput,
        topic_map: ContentMap,
        plan: SEOPlan,
        headings: HeadingPlan,
        existing_summary: str | None,
        target_words: int,
        options: RunOptions,
    ) -> Content:
        self._emit("CONTENT_GENERATION", "تولید محتوای موضوع‌محور...")
        article = self.client.generate_json(
            stage="content_generation",
            system=content_system(user_input),
            user=content_user(
                user_input,
                compact_topic_map(topic_map),
                compact_seo_plan(plan),
                compact_headings(headings),
                existing_summary,
                target_words,
                dump(options.locks) if any(options.locks.model_dump().values()) else None,
            ),
            schema=Content,
            kind="content",
            temperature=0.65,
        )
        return _finish_article(article, headings, user_input)

    def _validate_and_revise(
        self,
        user_input: UserInput,
        topic_map: ContentMap,
        plan: SEOPlan,
        headings: HeadingPlan,
        article: Content,
        existing_summary: str | None,
        target_words: int,
        options: RunOptions,
        cannibal,
    ) -> tuple[Content, HeadingPlan, Validation, int]:
        current = article
        current_headings = headings
        revision_count = 0
        validation, qualitative = self._evaluate(
            user_input, plan, current_headings, current, topic_map, cannibal
        )
        for attempt in range(MAX_CONTENT_REVISIONS):
            if not validation.revision_required:
                self._emit("FINAL_VALIDATION", f"امتیاز {validation.overall_score} — قبول")
                break
            revision_count = attempt + 1
            action, instructions, targets = revision_action_from_validation(validation, qualitative)
            self._emit(
                "TARGETED_REVISION",
                f"{revision_count}/{MAX_CONTENT_REVISIONS} — {action} — امتیاز {validation.overall_score}",
            )
            failed = [item.model_dump() for item in validation.checks if item.status == "FAIL"]
            locked = options.locks.model_copy(deep=True)
            locked.headings = True
            current = self.client.generate_json(
                stage="revision",
                system=revision_system(user_input),
                user=revision_user(
                    user_input,
                    current.article_html,
                    current.article_markdown,
                    dump(failed),
                    targets or validation.weak_sections or validation.failed_checks,
                    compact_headings(current_headings),
                    target_words,
                    dump(locked),
                    action,
                    instructions,
                    compact_topic_map(topic_map),
                ),
                schema=Content,
                kind="content",
                temperature=0.45,
            )
            current = _finish_article(current, current_headings, user_input)
            current = _apply_locks(current, options)
            validation, qualitative = self._evaluate(
                user_input, plan, current_headings, current, topic_map, cannibal
            )
        else:
            if validation.revision_required:
                self._emit("HUMAN_REVIEW", "پس از اصلاح هدفمند هنوز به حد نصاب نرسید.")
        return current, current_headings, validation, revision_count

    def _evaluate(
        self,
        user_input: UserInput,
        plan: SEOPlan,
        headings: HeadingPlan,
        article: Content,
        topic_map: ContentMap,
        cannibal,
    ) -> tuple[Validation, LLMQualitativeReview | None]:
        self._emit("LOCAL_VALIDATION", "اعتبارسنجی محلی سئو...")
        cannibal_msgs = [item.message for item in cannibal] if cannibal else []
        validation = evaluate(
            user_input=user_input,
            plan=plan,
            headings=headings,
            article=article,
            qualitative=None,
            cannibalization=cannibal_msgs,
            content_map=topic_map,
        )
        log_event(
            "LOCAL_VALIDATION",
            validation.summary,
            category=user_input.category_name,
            model=self.client.last_model,
            score=validation.overall_score,
        )
        return validation, None

    def _to_box(
        self,
        user_input: UserInput,
        topic_map: ContentMap,
        plan: SEOPlan,
        headings: HeadingPlan,
        article: Content,
        validation: Validation,
        revision_count: int,
        notes: list[str],
        cannibal,
    ) -> FinalSEOBox:
        status = status_from_score(
            validation.overall_score,
            bool(validation.hard_fails),
            revision_count,
            MAX_CONTENT_REVISIONS,
        )
        slug = article.metadata.url_slug
        preserved = bool(user_input.category_url.strip())
        if preserved:
            slug = user_input.category_url.strip()
        return FinalSEOBox(
            category=user_input.category_name,
            category_type=topic_map.category_type or plan.category_type or user_input.category_type,
            primary_keyword=user_input.primary_keyword,
            secondary_keywords=plan.secondary_keywords or user_input.secondary_keywords,
            semantic_keywords=topic_map.related_concepts or plan.semantic_keywords,
            industries=[item.name for item in topic_map.industry_uses if item.relevance == "USE"]
            or plan.industries,
            search_intent=plan.search_intent.model_dump(),
            seo_strategy=plan.model_dump(),
            meta_title=article.metadata.seo_title,
            meta_description=article.metadata.meta_description,
            slug=slug,
            h1=article.h1 or headings.h1,
            headings=[{"level": item.level, "text": item.text} for item in headings.headings],
            content=article.article_html,
            content_markdown=article.article_markdown,
            faq=article.faqs,
            internal_links=article.internal_links,
            cta=article.cta,
            word_count=article.word_count or count_words(article.article_html),
            website_name=user_input.website_name,
            website_description=user_input.website_description,
            seo_score=validation.overall_score,
            validation=validation.model_dump(),
            revision_count=revision_count,
            status=status,  # type: ignore[arg-type]
            existing_url_preserved=preserved,
            pipeline_notes=notes,
            cannibalization_warnings=cannibal,
            prompt_versions=PROMPT_VERSIONS,
            model=self.client.last_model,
            topic_map=topic_map.model_dump(),
            box_style=user_input.box_style,
        )


def _apply_locks(article: Content, options: RunOptions) -> Content:
    previous = options.existing_article
    if options.locks.headings and options.existing_headings is not None:
        article.h1 = options.existing_headings.h1
    if previous is None:
        return article
    if options.locks.seo_title and previous.metadata.seo_title:
        article.metadata.seo_title = previous.metadata.seo_title
    if options.locks.meta_description and previous.metadata.meta_description:
        article.metadata.meta_description = previous.metadata.meta_description
    if options.locks.cta and previous.cta:
        article.cta = previous.cta
    return article


def _clamp_words(value: int, box_style: str = "full") -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default_word_count(box_style)
    low, high = word_count_bounds(box_style)
    return max(low, min(high, number))


def _finish_article(article: Content, headings: HeadingPlan, user_input: UserInput) -> Content:
    if not article.h1:
        article.h1 = headings.h1
    if not (article.article_markdown or "").strip():
        article.article_markdown = html_to_markdown(article.article_html)
    article.word_count = count_words(article.article_html)
    if user_input.category_url.strip():
        article.metadata.url_slug = user_input.category_url.strip()
        article.metadata.preserve_existing_url = True
    else:
        article.metadata.url_slug = normalize_slug(article.metadata.url_slug, "")
    article.metadata.title_character_count = char_count(article.metadata.seo_title)
    article.metadata.description_character_count = char_count(article.metadata.meta_description)
    return article


def _finalize_plans(
    user_input: UserInput, topic_map: ContentMap, plan: SEOPlan, headings: HeadingPlan
) -> tuple[ContentMap, SEOPlan, HeadingPlan]:
    topic_map.core_topic = topic_map.core_topic or user_input.category_name
    topic_map.recommended_word_count = _clamp_words(
        topic_map.recommended_word_count or user_input.desired_word_count,
        user_input.box_style,
    )
    plan.primary_keyword = plan.primary_keyword or user_input.primary_keyword
    plan.category = plan.category or user_input.category_name
    plan.category_type = plan.category_type or topic_map.category_type
    plan.recommended_word_count = _clamp_words(
        topic_map.recommended_word_count or plan.recommended_word_count or user_input.desired_word_count,
        user_input.box_style,
    )
    if not plan.search_intent.primary_intent:
        plan.search_intent.primary_intent = topic_map.primary_search_intent
    if not headings.h1 and headings.headings:
        headings.h1 = next((item.text for item in headings.headings if item.level == "H1"), headings.headings[0].text)
    return topic_map, plan, headings


def _topic_map_from_plan(plan: SEOPlan, user_input: UserInput) -> ContentMap:
    uses = [
        IndustryUse(name=name, relevance="USE", role="use_case")
        for name in (plan.industries or user_input.industries_professions)[:6]
    ]
    topics = [
        SemanticTopic(topic=item, heading_worthy=True, priority="core")
        for item in (plan.heading_topics_from_map or plan.recommended_heading_topics)[:6]
    ]
    return ContentMap(
        core_topic=plan.primary_keyword or user_input.category_name,
        category_type=plan.category_type,
        primary_search_intent=plan.search_intent.primary_intent,
        secondary_intents=plan.search_intent.secondary_intents,
        user_questions=plan.user_questions or plan.search_intent.questions_to_answer,
        semantic_topics=topics,
        related_concepts=plan.semantic_keywords,
        industry_uses=uses,
        recommended_word_count=plan.recommended_word_count or user_input.desired_word_count,
        product_mention_policy="supporting_section",
    )


def _existing_content_locally(raw: str) -> ExistingContentAnalysis:
    text = raw.strip()
    headings = extract_headings(text)
    if not headings:
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("### "):
                headings.append(("H3", stripped[4:].strip()))
            elif stripped.startswith("## "):
                headings.append(("H2", stripped[3:].strip()))
            elif stripped.startswith("# "):
                headings.append(("H1", stripped[2:].strip()))
    h1 = next((item[1] for item in headings if item[0] == "H1"), "")
    h2s = [item[1] for item in headings if item[0] == "H2"][:8]
    h3s = [item[1] for item in headings if item[0] == "H3"][:8]
    plain = strip_html(text)
    return ExistingContentAnalysis(
        current_h1=h1,
        current_h2s=h2s,
        current_h3s=h3s,
        summary=plain[:700],
        useful_facts_to_preserve=[plain[:280]] if plain else [],
    )
