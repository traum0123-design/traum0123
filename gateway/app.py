from __future__ import annotations

"""
Unified ASGI gateway that exposes the Flask portal UI and the FastAPI JSON API
on a single origin. Mounts the existing FastAPI app under `/api` and serves
the Flask application everywhere else through WSGIMiddleware so that one
process can handle both use-cases (local dev & deployment).
"""

from fastapi import FastAPI
from fastapi.middleware.wsgi import WSGIMiddleware

from payroll_api.main import app as api_app
from payroll_portal.app import app as flask_app


def create_app() -> FastAPI:
    gateway = FastAPI(title="Payroll Gateway")
    # All JSON endpoints are exposed under /api
    gateway.mount("/api", api_app)
    # Flask handles the remaining routes (HTML, static, admin portal, etc.)
    gateway.mount("/", WSGIMiddleware(flask_app))
    return gateway


app = create_app()
