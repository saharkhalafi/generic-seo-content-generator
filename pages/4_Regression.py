import json
from pathlib import Path

import streamlit as st

from src.benchmark.runner import detect_regression

st.set_page_config(page_title="Regression", page_icon="🧪", layout="wide")
st.title("Regression Detection")

baseline_path = Path("data/baselines/clip_story_full.json")
if not baseline_path.exists():
    st.warning("Baseline not found. Run: python scripts/save_baseline.py")
    st.stop()

baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
st.subheader("Saved baseline (clip_story_full)")
st.metric("Baseline SEO score", baseline.get("seo_score"))
st.json({k: baseline[k] for k in ("seo_score", "status", "word_count", "revision_count") if k in baseline})

current_score = st.number_input("Current run SEO score", min_value=0, max_value=100, value=int(baseline.get("seo_score", 0)))
pipeline_metrics = {"seo_score": current_score}
baseline_metrics = {"seo_score": baseline.get("seo_score", 0)}
flag = detect_regression(pipeline_metrics, baseline_metrics, previous_pipeline=baseline_metrics)
st.write(f"**Result:** {flag}")
