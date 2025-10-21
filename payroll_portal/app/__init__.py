from __future__ import annotations

import os

from flask import Flask

from payroll_shared.settings import get_settings, reset_settings_cache

from .csrf import register_csrf
from .extensions import init_extensions, db_session
from .security import register_security


def create_app() -> Flask:
    reset_settings_cache()
    settings = get_settings()

    from .. import models  # noqa: F401  # ensure models are registered

    template_folder = os.path.join(os.path.dirname(__file__), "..", "templates")
    static_folder = os.path.join(os.path.dirname(__file__), "..", "static")

    app = Flask(
        __name__,
        template_folder=template_folder,
        static_folder=static_folder,
    )
    app.config.update(
        SECRET_KEY=settings.secret_key,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PAYROLL_AUTO_APPLY_DDL=settings.payroll_auto_apply_ddl,
    )

    init_extensions(app)
    register_security(app)
    register_csrf(app)

    from ..blueprints.admin import bp as admin_bp
    from ..blueprints.portal import bp as portal_bp
    from ..blueprints.api import bp as api_bp

    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(portal_bp, url_prefix="/portal")
    app.register_blueprint(api_bp, url_prefix="/api")

    # Backward-compatible health endpoints without /api prefix
    api_views = app.view_functions
    health = api_views.get("api.healthz")
    live = api_views.get("api.livez")
    ready = api_views.get("api.readyz")
    client_log = api_views.get("api.client_log")
    if health:
        app.add_url_rule("/healthz", endpoint="healthz", view_func=health)
    if live:
        app.add_url_rule("/livez", endpoint="livez", view_func=live)
    if ready:
        app.add_url_rule("/readyz", endpoint="readyz", view_func=ready)
    if client_log:
        app.add_url_rule("/client-log", endpoint="client_log", view_func=client_log, methods=["POST"])

    from ..services.context import inject_tokens
    SessionScoped = db_session(app)

    @app.before_request
    def reset_scoped_session():
        SessionScoped.remove()

    app.context_processor(inject_tokens)

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        SessionScoped.remove()

    return app


app = create_app()

__all__ = ["create_app", "app"]
