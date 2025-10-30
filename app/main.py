from __future__ import annotations

import os
from pathlib import Path
import uuid

from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from payroll_api.main import lifespan as api_lifespan, router as api_router
from payroll_api.main import register_exception_handlers as register_api_exception_handlers
from core.logging_utils import maybe_enable_json_logging, set_request_id
from core.observability import init_sentry

from .routes.admin import router as admin_router
from .routes.admin_closings import router as admin_closings_router
from .routes.portal import router as portal_router
from core.metrics import observe_request, export_prometheus


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
    # Optional observability wiring (no-op if not configured)
    maybe_enable_json_logging()
    init_sentry()
    application = FastAPI(title="Payroll Platform", lifespan=api_lifespan)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=_resolve_cors_origins(),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(api_router, prefix="/api")
    # Ensure API error handlers (problem+json) are registered on the host app
    register_api_exception_handlers(application)
    # Add versioned namespace without breaking existing /api paths
    application.include_router(api_router, prefix="/api/v1")
    application.include_router(portal_router)
    application.include_router(admin_router)
    application.include_router(admin_closings_router)

    static_dir = Path(__file__).resolve().parents[1] / "payroll_portal" / "static"
    if static_dir.exists():
        application.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @application.get("/", include_in_schema=False)
    def root_redirect():
        return RedirectResponse(url="/admin/login", status_code=307)

    @application.middleware("http")
    async def request_id_middleware(request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        set_request_id(rid)
        resp = await call_next(request)
        try:
            resp.headers["X-Request-ID"] = rid
        except Exception:
            pass
        return resp

    @application.middleware("http")
    async def security_headers(request, call_next):
        resp = await call_next(request)
        # Basic hardening headers (non-breaking)
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        resp.headers["Cross-Origin-Resource-Policy"] = "same-site"
        resp.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        resp.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=(), usb=(), payment=()",
        )
        # Introduce CSP in Report-Only and enforce baseline when not set by route
        if "Content-Security-Policy-Report-Only" not in resp.headers:
            resp.headers["Content-Security-Policy-Report-Only"] = "default-src 'self'; frame-ancestors 'none'"
        if "Content-Security-Policy" not in resp.headers:
            resp.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'"
        # HSTS only when the request is over HTTPS (direct or via proxy header)
        xf_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
        scheme = (request.url.scheme or "").lower()
        if (scheme == "https" or xf_proto == "https") and "strict-transport-security" not in resp.headers:
            resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        return resp

    @application.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        import time
        t0 = time.perf_counter()
        try:
            response = await call_next(request)
            status = getattr(response, "status_code", 200) or 200
        except Exception:
            status = 500
            raise
        finally:
            t1 = time.perf_counter()
            dur = max(0.0, t1 - t0)
            # prefer named route; fallback to path
            handler = getattr(getattr(request, "scope", {}).get("route", None), "name", None) or request.url.path
            observe_request(str(handler), str(request.method), int(status), float(dur))
        return response

    @application.get("/metrics", include_in_schema=False)
    async def metrics():
        text = export_prometheus()
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(text, media_type="text/plain; version=0.0.4; charset=utf-8")

    @application.middleware("http")
    async def _csrf_origin_guard(request: Request, call_next):
        # API에서 쿠키 인증을 사용하는 쓰기 요청에 대해 ORIGIN/REFERER 검사만 공통 적용
        try:
            unsafe = request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}
            path = request.url.path or ""
            has_cookie = bool(request.cookies.get("admin_token") or request.cookies.get("portal_token"))
            if unsafe and has_cookie and path.startswith("/api"):
                origin = (request.headers.get("origin") or "").strip()
                if origin:
                    expected = f"{request.url.scheme}://{request.url.netloc}"
                    if origin != expected:
                        from fastapi import HTTPException
                        raise HTTPException(status_code=403, detail="invalid origin")
                else:
                    referer = (request.headers.get("referer") or "").strip()
                    if referer:
                        from urllib.parse import urlparse
                        ref = urlparse(referer)
                        if ref.scheme != request.url.scheme or ref.netloc != request.url.netloc:
                            from fastapi import HTTPException
                            raise HTTPException(status_code=403, detail="invalid referer")
                # CSRF token requirement: for cookie-auth writes to /api, require X-CSRF-Token match cookie
                xsrf = (request.headers.get("x-csrf-token") or request.headers.get("X-CSRF-Token") or "").strip()
                csrf_cookie = request.cookies.get("portal_csrf") or ""
                if csrf_cookie:
                    from secrets import compare_digest
                    if not xsrf or not compare_digest(xsrf, csrf_cookie):
                        from fastapi import HTTPException
                        raise HTTPException(status_code=403, detail="invalid csrf token")
        except Exception:
            pass
        return await call_next(request)

    # Inject OpenAPI enrichments (Idempotency-Key + examples)
    def custom_openapi():
        if application.openapi_schema:
            return application.openapi_schema
        openapi_schema = get_openapi(
            title=application.title,
            version="1.0.0",
            description="Payroll Portal & API",
            routes=application.routes,
        )
        comps = openapi_schema.setdefault("components", {})
        params = comps.setdefault("parameters", {})
        params.setdefault(
            "IdempotencyKey",
            {
                "name": "Idempotency-Key",
                "in": "header",
                "required": False,
                "schema": {"type": "string"},
                "description": "Provide to make mutation requests idempotent.",
            },
        )
        schemas = comps.setdefault("schemas", {})
        schemas.setdefault(
            "ProblemDetails",
            {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "title": {"type": "string"},
                    "status": {"type": "integer"},
                    "detail": {"type": "string"},
                    "instance": {"type": "string"},
                    "request_id": {"type": "string"},
                },
            },
        )
        try:
            paths = openapi_schema.get("paths", {})
            for path, ops in list(paths.items()):
                if not isinstance(ops, dict):
                    continue
                for method, op in list(ops.items()):
                    if method.lower() not in {"post", "put", "patch", "delete"}:
                        continue
                    params_list = op.setdefault("parameters", [])
                    has_idem = any(p.get("$ref") == "#/components/parameters/IdempotencyKey" or p.get("name") == "Idempotency-Key" for p in params_list if isinstance(p, dict))
                    if not has_idem:
                        params_list.append({"$ref": "#/components/parameters/IdempotencyKey"})
                    responses = op.setdefault("responses", {})
                    for code in ("400", "401", "403", "404", "409"):
                        if code not in responses:
                            responses[code] = {
                                "description": "Error",
                                "content": {
                                    "application/problem+json": {
                                        "schema": {"$ref": "#/components/schemas/ProblemDetails"}
                                    }
                                },
                            }
            # Targeted examples for required endpoints (both /api and /api/v1 prefixes are included by router)
            def set_example(path: str, method: str, example: dict):
                if path in paths and method in paths[path]:
                    op = paths[path][method]
                    (op.setdefault("responses", {}).setdefault("200", {}).setdefault("content", {}).setdefault("application/json", {}).setdefault("example", example))

            def set_param_example(path: str, method: str, name: str, value):
                if path in paths and method in paths[path]:
                    for prm in paths[path][method].get("parameters", []):
                        if prm.get("name") == name:
                            prm.setdefault("example", value)

            # Admin companies page
            set_param_example("/api/v1/admin/companies/page", "get", "limit", 20)
            set_param_example("/api/v1/admin/companies/page", "get", "order", "desc")
            set_param_example("/api/v1/admin/companies/page", "get", "cursor", "eyJpZCI6MiwgImNyZWF0ZWRfYXQiOiAiMjAyNS0wMS0wMlQwMDowMDowMFoifQ==")
            set_example(
                "/api/v1/admin/companies/page",
                "get",
                {"ok": True, "items": [{"id": 2, "name": "베타", "slug": "beta"}], "has_more": False},
            )
            # Extra fields page
            set_example(
                "/api/v1/admin/company/{company_id}/extra-fields/page",
                "get",
                {"ok": True, "items": [{"id": 1, "name": "식대", "label": "식대", "typ": "number", "position": 10}], "has_more": False},
            )
            # Payrolls page with year filter
            set_param_example("/api/v1/admin/company/{company_id}/payrolls/page", "get", "year", 2025)
            set_example(
                "/api/v1/admin/company/{company_id}/payrolls/page",
                "get",
                {"ok": True, "items": [{"id": 10, "year": 2025, "month": 10, "is_closed": False}], "has_more": False},
            )
            # Reset code / rotate token key / impersonate
            set_example(
                "/api/v1/admin/company/{company_id}/reset-code",
                "post",
                {"ok": True, "company_id": 1, "access_code": "1a2b3c4d"},
            )
            set_example(
                "/api/v1/admin/company/{company_id}/rotate-token-key",
                "post",
                {"ok": True},
            )
            set_example(
                "/api/v1/admin/company/{company_id}/impersonate-token",
                "get",
                {"ok": True, "slug": "acme", "token": "eyJhbGciOi..."},
            )
        except Exception:
            pass

        application.openapi_schema = openapi_schema
        return application.openapi_schema

    application.openapi = custom_openapi
    
    return application


app = create_app()
