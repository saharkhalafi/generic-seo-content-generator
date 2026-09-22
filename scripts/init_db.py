#!/usr/bin/env python
"""Initialize PostgreSQL schema via Alembic."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit("Migration failed. Ensure DATABASE_URL is set in .env")
    print("Database migrations applied.")


if __name__ == "__main__":
    main()
