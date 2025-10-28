from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_meta_endpoint_fields():
    app = create_app()
    client = TestClient(app)
    r = client.get("/api/meta")
    assert r.status_code == 200
    data = r.json()
    assert "app_version" in data
    assert "git_sha" in data
    assert "build_ts" in data

