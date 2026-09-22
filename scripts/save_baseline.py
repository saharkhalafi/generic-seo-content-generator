"""Save a deterministic baseline SEO box from the mocked pipeline (no live Gemini)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.exporters import seo_box_to_json
from src.pipeline import SeoBoxPipeline
from src.storage import Store
from tests.conftest import sample_input
from tests.test_pipeline_storage import FakeClient

FIXTURE = ROOT / "tests" / "fixtures" / "clip_story_existing.txt"
OUT_DIR = ROOT / "data" / "baselines"


def main() -> None:
    existing = FIXTURE.read_text(encoding="utf-8") if FIXTURE.exists() else ""
    user = sample_input(existing_content=existing, box_style="full")
    store = Store(ROOT / "data" / "baseline_capture.sqlite")
    box = SeoBoxPipeline(FakeClient(), store=store).run(user)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "baseline_version": "1.0.0",
        "input": user.model_dump(),
        "export": box.export_payload(),
        "seo_score": box.seo_score,
        "status": box.status,
        "word_count": box.word_count,
        "h1": box.h1,
        "revision_count": box.revision_count,
    }
    out_path = OUT_DIR / "clip_story_full.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "clip_story_full_raw.json").write_text(seo_box_to_json(box), encoding="utf-8")
    print(f"Baseline saved: {out_path}")
    print(f"SEO score: {box.seo_score} | status: {box.status} | words: {box.word_count}")


if __name__ == "__main__":
    main()
