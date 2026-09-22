"""Production process entry: optional migrations, then Streamlit on $PORT."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _migrate_if_configured() -> None:
    if os.getenv("RUN_MIGRATIONS", "1").strip() not in {"1", "true", "TRUE", "yes"}:
        return
    from src.persistence.database import get_database_url

    if not get_database_url():
        return
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        check=False,
    )
    if completed.returncode != 0:
        print("Database migration failed.", file=sys.stderr)
        raise SystemExit(1)


def main() -> None:
    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    _migrate_if_configured()
    port = os.environ.get("PORT", "8080")
    os.execv(
        sys.executable,
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "serve.py",
            "--server.port",
            port,
            "--server.address",
            "0.0.0.0",
            "--server.headless",
            "true",
            "--browser.gatherUsageStats",
            "false",
            "--server.fileWatcherType",
            "none",
        ],
    )


if __name__ == "__main__":
    main()
