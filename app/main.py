from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

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

    @application.middleware("http")
    async def security_headers(request, call_next):
        resp = await call_next(request)
        # Basic hardening headers (non-breaking)
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        resp.headers["Cross-Origin-Resource-Policy"] = "same-site"
        # Introduce CSP in Report-Only and enforce baseline when not set by route
        if "Content-Security-Policy-Report-Only" not in resp.headers:
            resp.headers["Content-Security-Policy-Report-Only"] = "default-src 'self'; frame-ancestors 'none'"
        if "Content-Security-Policy" not in resp.headers:
            resp.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'"
        # HSTS only when the request is over HTTPS (direct or via proxy header)
        xf_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
        scheme = (request.url.scheme or "").lower()
        if (scheme == "https" or xf_proto == "https") and "strict-transport-security" not in resp.headers:
            resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return resp

    return application


app = create_app()
