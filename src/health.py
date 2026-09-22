from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.routing import Route


def health_payload() -> dict[str, str]:
    return {"status": "ok"}


def readiness_payload() -> tuple[dict[str, object], int]:
    """Process is ready when required PostgreSQL answers. SQLite-only mode is ready."""
    from src.persistence.database import get_database_url, get_engine

    if not get_database_url():
        return {"status": "ready", "database": "sqlite"}, 200
    engine = get_engine()
    if engine is None:
        return {"status": "not_ready", "database": "unavailable"}, 503
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
    except Exception:
        return {"status": "not_ready", "database": "unavailable"}, 503
    return {"status": "ready", "database": "postgresql"}, 200


def build_routes() -> list[Route]:
    async def health(_request):
        return JSONResponse(health_payload())

    async def ready(_request):
        body, code = readiness_payload()
        return JSONResponse(body, status_code=code)

    return [
        Route("/health", health, methods=["GET"]),
        Route("/ready", ready, methods=["GET"]),
    ]
