from __future__ import annotations

import json

from src.benchmark.schemas import BenchmarkCase
from src.config import ROOT_DIR

GOLD_DIR = ROOT_DIR / "data" / "gold_set"


def load_gold_cases() -> list[BenchmarkCase]:
    cases: list[BenchmarkCase] = []
    if not GOLD_DIR.exists():
        return cases
    for path in sorted(GOLD_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        existing = data.get("existing_content", "")
        if existing.startswith("See tests/fixtures/"):
            fixture_name = existing.split("/")[-1]
            fixture = ROOT_DIR / "tests" / "fixtures" / fixture_name
            if fixture.exists():
                data["existing_content"] = fixture.read_text(encoding="utf-8")
        cases.append(BenchmarkCase.model_validate(data))
    return cases


def load_case(case_key: str) -> BenchmarkCase | None:
    path = GOLD_DIR / f"{case_key}.json"
    if not path.exists():
        return None
    return BenchmarkCase.model_validate(json.loads(path.read_text(encoding="utf-8")))
