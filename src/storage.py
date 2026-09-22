from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src.config import DATA_DIR, get_settings
from src.persian import normalize_fa, similarity
from src.schemas import CannibalizationWarning, FinalSEOBox, UserInput

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    url TEXT DEFAULT '',
    category_type TEXT DEFAULT '',
    website_name TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS keyword_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER,
    primary_keyword TEXT NOT NULL,
    primary_normalized TEXT NOT NULL,
    secondary_json TEXT DEFAULT '[]',
    semantic_json TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY(category_id) REFERENCES categories(id)
);
CREATE TABLE IF NOT EXISTS seo_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER,
    created_at TEXT NOT NULL,
    model TEXT DEFAULT '',
    prompt_versions TEXT DEFAULT '{}',
    input_json TEXT NOT NULL,
    score INTEGER DEFAULT 0,
    revision_count INTEGER DEFAULT 0,
    status TEXT DEFAULT '',
    FOREIGN KEY(category_id) REFERENCES categories(id)
);
CREATE TABLE IF NOT EXISTS seo_outputs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    output_json TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES seo_runs(id)
);
CREATE TABLE IF NOT EXISTS validation_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    validation_json TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES seo_runs(id)
);
CREATE TABLE IF NOT EXISTS keyword_registry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER,
    category_name TEXT NOT NULL,
    website_name TEXT DEFAULT '',
    primary_keyword TEXT NOT NULL,
    primary_normalized TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(category_id) REFERENCES categories(id)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: Path | None = None) -> None:
        settings = get_settings()
        self.path = Path(path or settings.sqlite_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._init()

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table: str, column: str, declaration: str) -> None:
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            self._ensure_column(conn, "categories", "website_name", "TEXT DEFAULT ''")
            self._ensure_column(conn, "keyword_registry", "website_name", "TEXT DEFAULT ''")

    def save_run(
        self,
        user_input: UserInput,
        box: FinalSEOBox,
        model: str,
        prompt_versions: dict[str, str],
    ) -> int:
        created = _now()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO categories(name, url, category_type, website_name, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    user_input.category_name,
                    user_input.category_url,
                    box.category_type,
                    user_input.website_name,
                    created,
                ),
            )
            category_id = int(cur.lastrowid)
            conn.execute(
                """INSERT INTO keyword_sets(category_id, primary_keyword, primary_normalized, secondary_json, semantic_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    category_id,
                    user_input.primary_keyword,
                    normalize_fa(user_input.primary_keyword),
                    json.dumps(user_input.secondary_keywords, ensure_ascii=False),
                    json.dumps(box.semantic_keywords, ensure_ascii=False),
                    created,
                ),
            )
            conn.execute(
                """INSERT INTO keyword_registry(category_id, category_name, website_name, primary_keyword, primary_normalized, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    category_id,
                    user_input.category_name,
                    user_input.website_name,
                    user_input.primary_keyword,
                    normalize_fa(user_input.primary_keyword),
                    created,
                ),
            )
            cur = conn.execute(
                """INSERT INTO seo_runs(category_id, created_at, model, prompt_versions, input_json, score, revision_count, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    category_id,
                    created,
                    model,
                    json.dumps(prompt_versions, ensure_ascii=False),
                    user_input.model_dump_json(),
                    box.seo_score,
                    box.revision_count,
                    box.status,
                ),
            )
            run_id = int(cur.lastrowid)
            conn.execute(
                "INSERT INTO seo_outputs(run_id, output_json) VALUES (?, ?)",
                (run_id, json.dumps(box.export_payload(), ensure_ascii=False)),
            )
            conn.execute(
                "INSERT INTO validation_results(run_id, validation_json) VALUES (?, ?)",
                (run_id, json.dumps(box.validation, ensure_ascii=False)),
            )
            conn.commit()
            return run_id

    def cannibalization_warnings(
        self,
        category_name: str,
        primary_keyword: str,
        threshold: float,
        website_name: str = "",
    ) -> list[CannibalizationWarning]:
        needle = normalize_fa(primary_keyword)
        site = website_name.strip()
        warnings: list[CannibalizationWarning] = []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT category_name, website_name, primary_keyword, primary_normalized FROM keyword_registry"
            ).fetchall()
            for row in rows:
                stored_site = (row["website_name"] or "").strip()
                if site and stored_site != site:
                    continue
                other_name = row["category_name"]
                if normalize_fa(other_name) == normalize_fa(category_name):
                    continue
                score = similarity(needle, row["primary_normalized"])
                if score >= threshold:
                    warnings.append(
                        CannibalizationWarning(
                            other_category=other_name,
                            other_keyword=row["primary_keyword"],
                            similarity=round(score, 3),
                            message=(
                                f"کلمه کلیدی «{primary_keyword}» به «{row['primary_keyword']}» "
                                f"در دسته «{other_name}» شبیه است (شباهت {score:.2f})."
                            ),
                        )
                    )
        return warnings
