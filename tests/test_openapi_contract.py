from __future__ import annotations

from fastapi.testclient import TestClient


def test_openapi_has_idempotency_and_problem_examples():
    from app.main import create_app
    app = create_app()
    client = TestClient(app)
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    data = resp.json()
    # Check Idempotency-Key parameter exists for a POST path
    post_ops = []
    for p, ops in (data.get("paths") or {}).items():
        if isinstance(ops, dict) and "post" in ops:
            post_ops.append(ops["post"])
    assert any(any((p.get("$ref") == "#/components/parameters/IdempotencyKey" or p.get("name") == "Idempotency-Key") for p in (op.get("parameters") or [])) for op in post_ops)

    # Check ProblemDetails schema exists
    comps = data.get("components", {})
    assert "ProblemDetails" in (comps.get("schemas") or {})

    # Ensure a known endpoint includes example
    paths = data.get("paths") or {}
    eg = (
        (((paths.get("/admin/company/{company_id}/reset-code") or {}).get("post") or {}).get("responses") or {})
        .get("200", {})
        .get("content", {})
        .get("application/json", {})
        .get("example")
    )
    assert isinstance(eg, dict)

