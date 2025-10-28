from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_admin_login_requires_csrf(monkeypatch):
    # Plaintext password for ease in tests
    monkeypatch.setenv("ADMIN_PASSWORD", "testpw")

    app = create_app()
    client = TestClient(app)

    # First, GET form to receive CSRF cookie
    r_get = client.get("/admin/login")
    assert r_get.status_code == 200
    csrf_cookie = r_get.cookies.get("portal_csrf")
    assert csrf_cookie

    # Missing/invalid CSRF should be rejected
    r_bad = client.post("/admin/login", data={"password": "testpw"}, follow_redirects=False)
    assert r_bad.status_code == 403

    # Correct CSRF should pass and redirect
    r_ok = client.post(
        "/admin/login",
        data={"password": "testpw", "csrf_token": csrf_cookie},
        follow_redirects=False,
    )
    assert r_ok.status_code in (301, 302, 303, 307, 308)
