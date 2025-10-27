from __future__ import annotations

from starlette.requests import Request

from core.rate_limit import get_admin_rate_limiter


def client_ip(request: Request) -> str:
    """Best-effort client IP extraction compatible with Starlette.

    - Prefer X-Forwarded-For first value when present.
    - Fall back to Request.client.host (Starlette) instead of non-existent remote_addr.
    """
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    try:
        client = request.client
        if client is None:
            return "unknown"
        # client can be a namedtuple(host, port)
        host = getattr(client, "host", None)
        if host:
            return host
        # fallback tuple-like
        return (client[0] if isinstance(client, (tuple, list)) and client else "unknown") or "unknown"
    except Exception:
        return "unknown"


def admin_login_key(request: Request) -> str:
    return f"admin:{client_ip(request)}"


def portal_login_key(request: Request, slug: str) -> str:
    return f"portal:{slug}:{client_ip(request)}"


def limiter():
    return get_admin_rate_limiter()
