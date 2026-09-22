import streamlit as st

from src.benchmark.gold_set import load_gold_cases
from src.benchmark.runner import run_case_comparison
from src.config import postgres_enabled
from src.llm import VertexClient
from src.persistence.factory import get_run_store

st.set_page_config(page_title="Benchmark", page_icon="📊", layout="wide")
st.title("Benchmark — Baseline vs Pipeline")

cases = load_gold_cases()
if not cases:
    st.warning("No gold-set cases found in data/gold_set/")
    st.stop()

case_key = st.selectbox("Benchmark case", [c.case_key for c in cases])
use_live = st.checkbox("Use live Vertex (requires ADC)", value=False)
run_clicked = st.button("Run comparison", type="primary")

if run_clicked:
    if use_live:
        client = VertexClient()
    else:
        from tests.test_pipeline_storage import FakeClient

        client = FakeClient()
    with st.spinner("Running pipeline and baseline..."):
        result = run_case_comparison(client, case_key)
    flag = result["regression_flag"]
    pipeline_metrics = result["pipeline_metrics"]
    baseline_metrics = result["baseline_metrics"]
    comparison = result["comparison"]
    st.success(f"Flag: {flag}")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Pipeline")
        st.metric("SEO score", pipeline_metrics["seo_score"])
        st.json(pipeline_metrics)
    with col2:
        st.subheader("Baseline (single prompt)")
        st.metric("SEO score", baseline_metrics["seo_score"])
        st.json(baseline_metrics)
    st.subheader("Comparison")
    st.json(comparison)
    seo_cmp = comparison.get("seo_score", {})
    if seo_cmp:
        st.write(
            f"Improvement: {seo_cmp.get('absolute_improvement')} points "
            f"({seo_cmp.get('relative_improvement_pct')}%)"
        )

st.divider()
st.subheader("Human evaluation (optional)")
if not postgres_enabled() or not get_run_store().postgres:
    st.info("Set DATABASE_URL to store human evaluations.")
else:
    run_id = st.text_input("run_id to evaluate")
    reviewer = st.text_input("Reviewer name", value="reviewer")
    scores = {}
    for key, label in [
        ("usefulness", "Usefulness"),
        ("intent_satisfaction", "Intent satisfaction"),
        ("persian_naturalness", "Persian naturalness"),
        ("factual_accuracy", "Factual accuracy"),
        ("heading_quality", "Heading quality"),
        ("commercial_usefulness", "Commercial usefulness"),
        ("overall_quality", "Overall quality"),
    ]:
        scores[key] = st.slider(label, 1, 5, 3)
    notes = st.text_area("Notes")
    if st.button("Save human evaluation") and run_id:
        get_run_store().postgres.save_human_evaluation(
            run_id=run_id,
            case_key=case_key,
            reviewer=reviewer,
            scores=scores,
            notes=notes,
        )
        st.success("Saved.")
    corr = get_run_store().postgres.human_automation_correlation()
    if corr:
        st.json(corr)
