"""Add indexes and non-destructive check/foreign-key constraints.

Existing rows are not deleted or rewritten. New constraints are NOT VALID so
current data is preserved; new writes are checked.
"""

from alembic import op

revision = "002_indexes_constraints"
down_revision = "001_initial"
branch_labels = None
depends_on = None


_INDEXES = (
    ("ix_seo_runs_created_at", "seo_runs", ["created_at"]),
    ("ix_seo_runs_status", "seo_runs", ["status"]),
    ("ix_seo_runs_category_id", "seo_runs", ["category_id"]),
    ("ix_seo_inputs_run_id", "seo_inputs", ["run_id"]),
    ("ix_seo_plans_run_id", "seo_plans", ["run_id"]),
    ("ix_heading_plans_run_id", "heading_plans", ["run_id"]),
    ("ix_seo_outputs_run_id", "seo_outputs", ["run_id"]),
    ("ix_validation_results_run_id", "validation_results", ["run_id"]),
    ("ix_validation_checks_run_id", "validation_checks", ["run_id"]),
    ("ix_revision_runs_run_id", "revision_runs", ["run_id"]),
    ("ix_model_calls_run_id", "model_calls", ["run_id"]),
    ("ix_pipeline_stages_run_id", "pipeline_stages", ["run_id"]),
    ("ix_feature_image_runs_seo_run_id", "feature_image_runs", ["seo_run_id"]),
    ("ix_human_evaluations_run_id", "human_evaluations", ["run_id"]),
    ("ix_system_errors_run_id", "system_errors", ["run_id"]),
    ("ix_keyword_registry_category_name", "keyword_registry", ["category_name"]),
    ("ix_categories_project_id", "categories", ["project_id"]),
    ("ix_categories_name", "categories", ["name"]),
)


def upgrade() -> None:
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns, if_not_exists=True)
    op.execute(
        """
        DO $$ BEGIN
          ALTER TABLE seo_runs
            ADD CONSTRAINT ck_seo_runs_score
            CHECK (seo_score >= 0 AND seo_score <= 100) NOT VALID;
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
          ALTER TABLE seo_runs
            ADD CONSTRAINT ck_seo_runs_revision_count
            CHECK (revision_count >= 0) NOT VALID;
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
          ALTER TABLE seo_runs
            ADD CONSTRAINT fk_seo_runs_category
            FOREIGN KEY (category_id) REFERENCES categories(id)
            ON DELETE SET NULL NOT VALID;
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
          ALTER TABLE categories
            ADD CONSTRAINT fk_categories_project
            FOREIGN KEY (project_id) REFERENCES projects(id)
            ON DELETE SET NULL NOT VALID;
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE categories DROP CONSTRAINT IF EXISTS fk_categories_project")
    op.execute("ALTER TABLE seo_runs DROP CONSTRAINT IF EXISTS fk_seo_runs_category")
    op.execute("ALTER TABLE seo_runs DROP CONSTRAINT IF EXISTS ck_seo_runs_revision_count")
    op.execute("ALTER TABLE seo_runs DROP CONSTRAINT IF EXISTS ck_seo_runs_score")
    for name, table, _columns in reversed(_INDEXES):
        op.drop_index(name, table_name=table, if_exists=True)
