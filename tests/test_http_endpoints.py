from __future__ import annotations

import os

from fastapi.testclient import TestClient


def test_api_healthz_ok(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    from payroll_api.main import create_app

    app = create_app()
    client = TestClient(app)

    resp = client.get("/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True


def test_root_redirects_to_admin_login():
    from app.main import create_app

    app = create_app()
    client = TestClient(app)

    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers.get("location") == "/admin/login"
