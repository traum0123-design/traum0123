from __future__ import annotations

import os
from typing import Any, Optional


def init_sentry() -> Optional[object]:
    """Initialize Sentry if SENTRY_DSN is set and sentry_sdk is installed.

    Returns the sentry SDK module when initialized, otherwise None.
    """
    dsn = (os.environ.get("SENTRY_DSN") or "").strip()
    if not dsn:
        return None
    try:
        import sentry_sdk  # type: ignore
        from sentry_sdk.integrations.starlette import StarletteIntegration  # type: ignore
    except Exception:
        return None

    def _before_send(event: dict[str, Any], hint: dict[str, Any] | None) -> dict[str, Any] | None:
        # Scrub PII and secrets from request headers
        try:
            req = event.get("request", {})
            hdrs = req.get("headers") or {}
            for k in list(hdrs.keys()):
                kl = str(k).lower()
                if kl in {"authorization", "cookie", "set-cookie", "x-api-token", "x-admin-token"}:
                    hdrs[k] = "[redacted]"
            req["headers"] = hdrs
            event["request"] = req
        except Exception:
            pass
        return event

    sentry_sdk.init(
        dsn=dsn,
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.0") or 0.0),
        environment=os.environ.get("SENTRY_ENV") or os.environ.get("ENV") or "dev",
        integrations=[StarletteIntegration()],
        before_send=_before_send,
    )
    return sentry_sdk

