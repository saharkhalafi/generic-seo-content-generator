"""ASGI entry with /health and /ready. The SEO UI remains app.py."""

from __future__ import annotations

from pathlib import Path

import streamlit as st
from starlette.middleware import Middleware

from src.health import build_routes
from src.security import SecurityHeadersMiddleware

app = st.App(
    str(Path(__file__).resolve().parent / "app.py"),
    routes=build_routes(),
    middleware=[Middleware(SecurityHeadersMiddleware)],
)
