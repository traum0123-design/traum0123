from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from payroll_api.main import lifespan as api_lifespan, router as api_router

from .routes.admin import router as admin_router
from .routes.portal import router as portal_router


def _resolve_cors_origins() -> list[str]:
    origins_env = (os.environ.get("API_CORS_ORIGINS") or "").strip()
    if origins_env:
        return [o.strip() for o in origins_env.split(",") if o.strip()]
    api_base = (os.environ.get("API_BASE_URL") or "").strip()
    if api_base:
        return [api_base]
    return [
        "http://localhost:5000",
        "http://127.0.0.1:5000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]


def create_app() -> FastAPI:
    application = FastAPI(title="Payroll Platform", lifespan=api_lifespan)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=_resolve_cors_origins(),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(api_router, prefix="/api")
    application.include_router(portal_router)
    application.include_router(admin_router)

    static_dir = Path(__file__).resolve().parents[1] / "payroll_portal" / "static"
    if static_dir.exists():
        application.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @application.get("/", include_in_schema=False)
    def root_redirect():
        return RedirectResponse(url="/admin/login", status_code=307)

    return application


app = create_app()
