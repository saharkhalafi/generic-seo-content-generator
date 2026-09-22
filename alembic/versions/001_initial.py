"""Initial PostgreSQL schema for production persistence."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category_type", sa.String(128), default=""),
        sa.Column("slug", sa.String(512), default=""),
        sa.Column("url", sa.String(512), default=""),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "seo_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("run_id", sa.String(64), unique=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model", sa.String(128), default=""),
        sa.Column("model_config_json", postgresql.JSONB, nullable=True),
        sa.Column("pipeline_version", sa.String(32), default="1.0.0"),
        sa.Column("prompt_versions", postgresql.JSONB, nullable=True),
        sa.Column("input_hash", sa.String(64), default=""),
        sa.Column("output_hash", sa.String(64), default=""),
        sa.Column("validation_version", sa.String(32), default="1.0.0"),
        sa.Column("seo_score", sa.Integer(), default=0),
        sa.Column("revision_count", sa.Integer(), default=0),
        sa.Column("status", sa.String(64), default=""),
        sa.Column("box_style", sa.String(16), default="full"),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_seo_runs_run_id", "seo_runs", ["run_id"])
    for name, cols in [
        ("seo_inputs", [sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("run_id", sa.String(64), nullable=False), sa.Column("raw_input", postgresql.JSONB, nullable=False), sa.Column("normalized_input", postgresql.JSONB, nullable=True)]),
        ("seo_plans", [sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("run_id", sa.String(64), nullable=False), sa.Column("plan_json", postgresql.JSONB, nullable=False), sa.Column("topic_map_json", postgresql.JSONB, nullable=True)]),
        ("heading_plans", [sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("run_id", sa.String(64), nullable=False), sa.Column("heading_plan_json", postgresql.JSONB, nullable=False)]),
        ("seo_outputs", [sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("run_id", sa.String(64), nullable=False), sa.Column("output_json", postgresql.JSONB, nullable=False)]),
        ("validation_results", [sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("run_id", sa.String(64), nullable=False), sa.Column("overall_score", sa.Integer(), default=0), sa.Column("validation_json", postgresql.JSONB, nullable=False)]),
        ("validation_checks", [sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("run_id", sa.String(64), nullable=False), sa.Column("code", sa.String(128), nullable=False), sa.Column("category", sa.String(64), default=""), sa.Column("status", sa.String(16), default=""), sa.Column("message", sa.Text(), default=""), sa.Column("hard_fail", sa.Boolean(), default=False)]),
        ("revision_runs", [sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("run_id", sa.String(64), nullable=False), sa.Column("revision_number", sa.Integer(), default=1), sa.Column("action", sa.String(64), default=""), sa.Column("score_before", sa.Integer(), nullable=True), sa.Column("score_after", sa.Integer(), nullable=True), sa.Column("details_json", postgresql.JSONB, nullable=True), sa.Column("created_at", sa.DateTime(timezone=True))]),
        ("benchmark_cases", [sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("case_key", sa.String(128), unique=True, nullable=False), sa.Column("case_json", postgresql.JSONB, nullable=False), sa.Column("source", sa.String(128), default="gold_set"), sa.Column("created_at", sa.DateTime(timezone=True))]),
        ("benchmark_runs", [sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("benchmark_id", sa.String(64), unique=True, nullable=False), sa.Column("case_key", sa.String(128), nullable=False), sa.Column("mode", sa.String(32), nullable=False), sa.Column("run_id", sa.String(64), nullable=True), sa.Column("metrics_json", postgresql.JSONB, nullable=True), sa.Column("comparison_json", postgresql.JSONB, nullable=True), sa.Column("regression_flag", sa.String(32), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True))]),
        ("model_calls", [sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("run_id", sa.String(64), nullable=True), sa.Column("provider", sa.String(64), default="vertex"), sa.Column("model", sa.String(128), default=""), sa.Column("operation", sa.String(128), default=""), sa.Column("stage", sa.String(128), default=""), sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True), sa.Column("duration_ms", sa.Integer(), nullable=True), sa.Column("input_tokens", sa.Integer(), nullable=True), sa.Column("output_tokens", sa.Integer(), nullable=True), sa.Column("estimated_cost_usd", sa.Float(), nullable=True), sa.Column("status", sa.String(32), default="success"), sa.Column("retry_count", sa.Integer(), default=0), sa.Column("error_type", sa.String(64), nullable=True), sa.Column("error_message", sa.Text(), nullable=True)]),
        ("pipeline_stages", [sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("run_id", sa.String(64), nullable=False), sa.Column("stage", sa.String(64), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True), sa.Column("duration_ms", sa.Integer(), nullable=True), sa.Column("status", sa.String(32), default="success"), sa.Column("model", sa.String(128), nullable=True), sa.Column("error_type", sa.String(64), nullable=True), sa.Column("error_message", sa.Text(), nullable=True)]),
        ("prompt_versions", [sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("prompt_key", sa.String(128), nullable=False), sa.Column("version", sa.String(64), nullable=False), sa.Column("notes", sa.Text(), default=""), sa.Column("created_at", sa.DateTime(timezone=True))]),
        ("pipeline_versions", [sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("version", sa.String(32), unique=True, nullable=False), sa.Column("notes", sa.Text(), default=""), sa.Column("created_at", sa.DateTime(timezone=True))]),
        ("keyword_registry", [sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True), sa.Column("category_name", sa.String(255), nullable=False), sa.Column("primary_keyword", sa.String(512), nullable=False), sa.Column("primary_normalized", sa.String(512), nullable=False), sa.Column("secondary_keywords", postgresql.JSONB, nullable=True), sa.Column("semantic_keywords", postgresql.JSONB, nullable=True), sa.Column("slug", sa.String(512), default=""), sa.Column("created_at", sa.DateTime(timezone=True)), sa.Column("updated_at", sa.DateTime(timezone=True))]),
        ("feature_image_runs", [sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("seo_run_id", sa.String(64), nullable=True), sa.Column("input_summary", sa.Text(), default=""), sa.Column("prompt_version", sa.String(64), default="FEATURE_IMAGE_V1"), sa.Column("model", sa.String(128), default=""), sa.Column("output_path", sa.String(1024), nullable=True), sa.Column("status", sa.String(32), default="pending"), sa.Column("duration_ms", sa.Integer(), nullable=True), sa.Column("error_message", sa.Text(), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True))]),
        ("human_evaluations", [sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("run_id", sa.String(64), nullable=False), sa.Column("case_key", sa.String(128), nullable=True), sa.Column("reviewer", sa.String(128), default=""), sa.Column("usefulness", sa.Integer(), nullable=True), sa.Column("intent_satisfaction", sa.Integer(), nullable=True), sa.Column("persian_naturalness", sa.Integer(), nullable=True), sa.Column("factual_accuracy", sa.Integer(), nullable=True), sa.Column("heading_quality", sa.Integer(), nullable=True), sa.Column("commercial_usefulness", sa.Integer(), nullable=True), sa.Column("overall_quality", sa.Integer(), nullable=True), sa.Column("notes", sa.Text(), default=""), sa.Column("created_at", sa.DateTime(timezone=True))]),
        ("system_errors", [sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("run_id", sa.String(64), nullable=True), sa.Column("stage", sa.String(64), default=""), sa.Column("error_type", sa.String(64), default="unknown_error"), sa.Column("message", sa.Text(), default=""), sa.Column("details_json", postgresql.JSONB, nullable=True), sa.Column("created_at", sa.DateTime(timezone=True))]),
    ]:
        op.create_table(name, *cols)


def downgrade() -> None:
    for table in reversed([
        "system_errors", "human_evaluations", "feature_image_runs", "keyword_registry",
        "pipeline_versions", "prompt_versions", "pipeline_stages", "model_calls",
        "benchmark_runs", "benchmark_cases", "revision_runs", "validation_checks",
        "validation_results", "seo_outputs", "heading_plans", "seo_plans", "seo_inputs",
        "seo_runs", "categories", "projects",
    ]):
        op.drop_table(table)
