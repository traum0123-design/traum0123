from __future__ import annotations

from fastapi.testclient import TestClient


def test_security_headers_present_on_root_redirect():
    from app.main import create_app
    app = create_app()
    client = TestClient(app)
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (301, 302, 303, 307, 308)
    # Basic hardening headers added by middleware
    assert r.headers.get("x-frame-options") == "DENY"
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert r.headers.get("content-security-policy-report-only")
