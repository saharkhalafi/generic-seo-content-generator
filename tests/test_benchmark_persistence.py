from __future__ import annotations

import pytest

from src.persistence.postgres_repository import PostgresRunRepository


def test_save_benchmark_run_no_db(monkeypatch):
    """Repository method exists and accepts expected payload shape."""
    repo = PostgresRunRepository()
    monkeypatch.setattr(
        "src.persistence.postgres_repository.session_scope",
        lambda: (_ for _ in ()).throw(RuntimeError("no db")),
    )
    with pytest.raises(RuntimeError):
        repo.save_benchmark_run(
            benchmark_id="abc",
            case_key="clip_story",
            mode="pipeline",
            run_id=None,
            metrics={"seo_score": 90},
        )
