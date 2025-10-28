from __future__ import annotations

from fastapi.testclient import TestClient


def test_admin_login_rejects_cross_origin(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "testpw")
    from app.main import create_app
    app = create_app()
    client = TestClient(app)

    # Obtain CSRF token via GET (same-origin)
    r_get = client.get("/admin/login")
    assert r_get.status_code == 200
    csrf = r_get.cookies.get("portal_csrf")
    assert csrf

    # Submit with valid CSRF but forged Origin
    r = client.post(
        "/admin/login",
        data={"password": "testpw", "csrf_token": csrf},
        headers={"Origin": "https://evil.example"},
        follow_redirects=False,
    )
    assert r.status_code == 403
