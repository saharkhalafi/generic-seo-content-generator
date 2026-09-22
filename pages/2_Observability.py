import streamlit as st

from src.config import postgres_enabled
from src.domain.errors import redact
from src.persistence.factory import get_run_store

st.set_page_config(page_title="Observability", page_icon="📈", layout="wide")
st.title("Observability Dashboard")

store = get_run_store()
if not postgres_enabled() or not store.postgres:
    st.info("PostgreSQL is not configured. Set DATABASE_URL in .env to enable observability KPIs.")
    st.stop()

summary = store.postgres.observability_summary()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total runs", summary["total_runs"])
c2.metric("Successful", summary["successful_runs"])
c3.metric("Avg SEO score", summary["avg_seo_score"])
c4.metric("Avg latency (ms)", summary["avg_latency_ms"])
st.metric("Validation failure rate", f"{summary['validation_failure_rate'] * 100:.1f}%")
st.metric("Avg revisions", summary["avg_revision_count"])
st.subheader("Score distribution")
st.bar_chart(summary["score_distribution"])
st.subheader("Model usage")
st.json(summary["model_usage"])
st.subheader("Recent errors")
for err in summary["recent_errors"]:
    st.error(f"{err['stage']} — {err['error_type']}: {redact(err['message'])}")
