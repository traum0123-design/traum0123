from __future__ import annotations

import secrets

from flask import Flask, abort, jsonify, request, session


SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def register_csrf(app: Flask) -> None:
    @app.before_request
    def _ensure_csrf_cookie():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)

    @app.before_request
    def _csrf_protect():
        if request.method in SAFE_METHODS:
            return
        token = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
        if not token or token != session.get("csrf_token"):
            return jsonify({"ok": False, "error": "CSRF token missing or invalid"}), 403

    @app.context_processor
    def _csrf_context():
        return {"csrf_token": lambda: session.get("csrf_token", "")}
