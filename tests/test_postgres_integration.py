from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.engine import make_url

from src.persistence.database import get_database_url, get_engine, is_postgres_configured, session_scope
from src.persistence.models import (
    Category,
    HeadingPlanRecord,
    KeywordRegistry,
    Project,
    SeoInput,
    SeoOutput,
    SeoPlanRecord,
    SeoRun,
    ValidationCheck,
    ValidationResult,
)
from src.persistence.postgres_repository import PostgresRunRepository
from src.schemas import FinalSEOBox
from tests.conftest import sample_input

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.integration
def test_postgres_connection_targets_configured_database():
    if not is_postgres_configured():
        pytest.skip("DATABASE_URL not set")
    engine = get_engine()
    assert engine is not None
    expected = make_url(get_database_url()).database
    with engine.connect() as connection:
        current = connection.execute(text("SELECT current_database()")).scalar_one()
    assert current == expected
    assert expected == "content_generator"


@pytest.mark.integration
def test_migrations_keep_existing_rows_and_indexes():
    if not is_postgres_configured():
        pytest.skip("DATABASE_URL not set")
    for _ in range(2):
        completed = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT,
            check=False,
        )
        assert completed.returncode == 0
    engine = get_engine()
    assert engine is not None
    inspector = inspect(engine)
    assert "seo_runs" in inspector.get_table_names()
    assert "ix_seo_runs_status" in {index["name"] for index in inspector.get_indexes("seo_runs")}
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "002_indexes_constraints"

    marker = f"hardening-{uuid.uuid4().hex[:12]}"
    with session_scope() as session:
        project = Project(name=marker)
        session.add(project)
        session.flush()
        project_id = project.id
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        check=False,
    )
    assert completed.returncode == 0
    with session_scope() as session:
        kept = session.get(Project, project_id)
        assert kept is not None
        assert kept.name == marker
        session.delete(kept)


@pytest.mark.integration
def test_postgres_persists_seo_run_roundtrip():
    if not is_postgres_configured():
        pytest.skip("DATABASE_URL not set")
    repository = PostgresRunRepository()
    user = sample_input(website_name=f"site-{uuid.uuid4().hex[:8]}")
    box = FinalSEOBox(
        category=user.category_name,
        primary_keyword=user.primary_keyword,
        h1="عنوان تست",
        content="<h1>عنوان تست</h1><p>متن آزمایشی برای ذخیره.</p>",
        seo_score=88,
        status="good",
        revision_count=1,
        model="gemini-2.5-flash",
        website_name=user.website_name,
        website_description=user.website_description,
    )
    run_id = uuid.uuid4().hex
    repository.save_run(
        run_id=run_id,
        user_input=user,
        box=box,
        model="gemini-2.5-flash",
        prompt_versions={"CONTENT_GENERATOR": "CONTENT_GENERATOR_V2"},
        latency_ms=10,
    )
    detail = repository.get_run_detail(run_id)
    assert detail is not None
    assert detail["run"]["seo_score"] == 88
    assert detail["run"]["revision_count"] == 1
    assert detail["input"]["website_name"] == user.website_name
    with session_scope() as session:
        row = session.scalar(select(SeoRun).where(SeoRun.run_id == run_id))
        assert row is not None
        category_id = row.category_id
        for model in (SeoInput, SeoOutput, SeoPlanRecord, HeadingPlanRecord, ValidationResult, ValidationCheck):
            for child in session.scalars(select(model).where(model.run_id == run_id)).all():
                session.delete(child)
        session.delete(row)
        if category_id is not None:
            for keyword in session.scalars(
                select(KeywordRegistry).where(KeywordRegistry.category_id == category_id)
            ).all():
                session.delete(keyword)
            category = session.get(Category, category_id)
            project_id = category.project_id if category else None
            if category is not None:
                session.delete(category)
            if project_id is not None:
                project = session.get(Project, project_id)
                if project is not None and project.name == user.website_name:
                    session.delete(project)
