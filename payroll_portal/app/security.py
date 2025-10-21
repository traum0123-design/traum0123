from __future__ import annotations

import os
import secrets
from typing import Callable

from flask import Flask, Response, g, request


def register_security(app: Flask) -> None:
    app.wsgi_app = _proxy_fix(app.wsgi_app)

    @app.before_request
    def _inject_nonce():
        g.csp_nonce = secrets.token_urlsafe(16)

    enable_csp = os.environ.get("PORTAL_ENABLE_CSP", "").strip().lower() in {"1", "true", "yes", "on"}

    if enable_csp:
        @app.after_request
        def _set_headers(resp: Response):
            nonce = getattr(g, "csp_nonce", "")
            api_base = (os.environ.get("API_BASE_URL") or "/api").strip()
            script_src = ["'self'", "'unsafe-inline'"]
            if nonce:
                script_src.append(f"'nonce-{nonce}'")
                script_src.append("'strict-dynamic'")
            connect_src = ["'self'"]
            if api_base and api_base not in {"/", ""}:
                connect_src.append(api_base)
            csp_parts = [
                "default-src 'self'",
                "style-src 'self' 'unsafe-inline'",
                f"script-src {' '.join(script_src)}",
                f"connect-src {' '.join(connect_src)}",
            ]
            resp.headers.setdefault("Content-Security-Policy", "; ".join(csp_parts))
            resp.headers.setdefault("X-Content-Type-Options", "nosniff")
            resp.headers.setdefault("X-Frame-Options", "DENY")
            resp.headers.setdefault("Referrer-Policy", "same-origin")
            resp.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
            return resp

    @app.context_processor
    def _security_context():
        return {"csp_nonce": lambda: getattr(g, "csp_nonce", "")}


def _proxy_fix(wsgi_app: Callable):
    try:
        from werkzeug.middleware.proxy_fix import ProxyFix

        return ProxyFix(wsgi_app, x_proto=1, x_host=1)
    except Exception:
        return wsgi_app
