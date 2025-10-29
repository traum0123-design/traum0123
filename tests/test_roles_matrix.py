from __future__ import annotations

import itertools
from fastapi.testclient import TestClient


def setup_env(monkeypatch):
    from core.db import init_database, get_sessionmaker
    from sqlalchemy.orm import Session
    from core.models import Company
    import datetime as dt
    import secrets
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("PAYROLL_AUTO_APPLY_DDL", "1")
    monkeypatch.setenv("SECRET_KEY", "secret")
    init_database(auto_apply_ddl=True)
    SessionLocal = get_sessionmaker()
    slug = f"demo_{secrets.token_hex(2)}"
    with SessionLocal() as db:  # type: Session
        c = Company(name="Demo", slug=slug, access_hash="x", token_key="tk3", created_at=dt.datetime.now(dt.UTC))
        db.add(c); db.commit(); db.refresh(c)
        return SessionLocal, c.id, c.slug


def tok(company_id: int, slug: str, roles: list[str]):
    from core.auth import make_company_token
    from core.settings import get_settings
    return make_company_token(get_settings().secret_key, company_id, slug, key="tk3", roles=roles)


def test_roles_matrix_read_vs_write(monkeypatch):
    SessionLocal, cid, slug = setup_env(monkeypatch)
    from app.main import create_app
    app = create_app()
    client = TestClient(app)
    roles = {
        "viewer": ["viewer"],
        "mgr": ["payroll_manager"],
        "cadm": ["company_admin"],
        "adm": ["admin"],
    }
    tokens = {k: tok(cid, slug, v) for k, v in roles.items()}

    # Read endpoints (should allow viewer)
    read_paths = [
        f"/api/portal/{slug}/payroll/2025/10",
        f"/api/portal/{slug}/fields/calc-config",
        f"/api/portal/{slug}/fields/exempt-config",
    ]
    for role in roles:
        for path in read_paths:
            r = client.get(path, headers={"X-API-Token": tokens[role]})
            assert r.status_code == 200

    # Write endpoints (should deny viewer)
    write_specs = [
        (f"/api/portal/{slug}/payroll/2025/10", {"rows": [{"사원코드": "E01", "기본급": 1}]}),
        (f"/api/portal/{slug}/fields/calc-config", {"include": {"nhis": {"기본급": True}}}),
        (f"/api/portal/{slug}/fields/exempt-config", {"exempt": {"식대": {"enabled": True, "limit": 200000}}}),
        (f"/api/portal/{slug}/fields/group-config", {"map": {"기본급": "earn"}, "alias": {"기본급": "Base"}}),
        (f"/api/portal/{slug}/fields/add", {"label": "식대", "typ": "number"}),
        (f"/api/portal/{slug}/fields/delete", {"name": "식대"}),
    ]
    for (path, body) in write_specs:
        # viewer denied
        r = client.post(path, headers={"X-API-Token": tokens["viewer"], "Content-Type": "application/json"}, json=body)
        assert r.status_code == 403
        # others allowed (200/201)
        for role in ("mgr", "cadm", "adm"):
            r2 = client.post(path, headers={"X-API-Token": tokens[role], "Content-Type": "application/json"}, json=body)
            assert r2.status_code in (200, 201)

