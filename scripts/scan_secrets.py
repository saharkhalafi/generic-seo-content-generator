"""Fail if source files contain obvious secrets. Does not read .env."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN_ROOTS = ("src", "app.py", "serve.py", "pages", "scripts", "alembic")
PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    re.compile(r"AQ\.[0-9A-Za-z_\-]{20,}"),
)
SKIP_PARTS = {".venv", "__pycache__", ".git"}


def main() -> int:
    findings: list[str] = []
    for name in SCAN_ROOTS:
        path = ROOT / name
        files = [path] if path.is_file() else path.rglob("*")
        for file in files:
            if not file.is_file() or file.suffix not in {".py", ".yml", ".yaml", ".toml", ".ini", ".md"}:
                continue
            if any(part in SKIP_PARTS for part in file.parts):
                continue
            text = file.read_text(encoding="utf-8", errors="ignore")
            for pattern in PATTERNS:
                if pattern.search(text):
                    findings.append(f"{file.relative_to(ROOT)} matches {pattern.pattern}")
    if findings:
        print("\n".join(findings))
        return 1
    print("No obvious secrets in source.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
