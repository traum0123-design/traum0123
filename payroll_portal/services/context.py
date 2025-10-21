from __future__ import annotations

import os

from flask import session


def inject_tokens():
    """Inject configuration for templates without exposing bearer tokens."""

    api_base = (os.environ.get("API_BASE_URL") or "/api").strip()
    return {
        "API_BASE_URL": api_base or "/api",
        "API_TOKEN": "",
        "ADMIN_TOKEN": "",
        "is_admin": bool(session.get("is_admin")),
    }

