import streamlit as st

from src.config import get_settings, postgres_enabled
from src.persistence.factory import get_run_store

st.set_page_config(page_title="Run History", page_icon="🗂️", layout="wide")
st.title("Run History")

store = get_run_store()
if not postgres_enabled() or not store.postgres:
    st.info(f"PostgreSQL is not configured. Runs are stored in SQLite only ({get_settings().sqlite_path}).")
    st.stop()

runs = store.postgres.list_runs(limit=100)
status_filter = st.selectbox("Status filter", ["all", "excellent", "good", "needs_improvement", "revision_required"])
if status_filter != "all":
    runs = [r for r in runs if r["status"] == status_filter]
st.dataframe(runs, use_container_width=True)

run_id = st.text_input("Inspect run_id")
if run_id:
    detail = store.postgres.get_run_detail(run_id)
    if detail:
        st.json(detail)
    else:
        st.warning("Run not found.")
