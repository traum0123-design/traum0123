from __future__ import annotations

from fastapi.testclient import TestClient


def test_meta_endpoint_fields():
    from app.main import create_app
    app = create_app()
    client = TestClient(app)
    r = client.get("/api/meta")
    assert r.status_code == 200
    data = r.json()
    assert "app_version" in data
    assert "git_sha" in data
    assert "build_ts" in data
