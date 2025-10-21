from __future__ import annotations

"""ASGI entrypoint exposing the unified FastAPI application."""

from app.main import create_app


app = create_app()
