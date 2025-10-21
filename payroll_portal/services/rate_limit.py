from __future__ import annotations

from flask import Request

from payroll_shared.rate_limit import get_admin_rate_limiter


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def admin_login_key(request: Request) -> str:
    return f"admin:{client_ip(request)}"


def portal_login_key(request: Request, slug: str) -> str:
    return f"portal:{slug}:{client_ip(request)}"


def limiter():
    return get_admin_rate_limiter()

