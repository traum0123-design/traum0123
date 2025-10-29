from __future__ import annotations

import os

from fastapi.testclient import TestClient


def _seed_company(SessionLocal) -> tuple[int, str]:
    from sqlalchemy.orm import Session
    from core.models import Company
    import datetime as dt
    with SessionLocal() as db:  # type: Session
        c = Company(name="테스트회사", slug="acme", access_hash="x", token_key="key1", created_at=dt.datetime.now(dt.UTC))
        db.add(c)
        db.commit()
        db.refresh(c)
        return c.id, c.slug


def _make_token(company_id: int, slug: str, roles: list[str]) -> str:
    from core.auth import make_company_token
    from core.settings import get_settings
    secret = get_settings().secret_key
    # token_key must match company record for verification to pass
    return make_company_token(secret, company_id, slug, key="key1", roles=roles)


def test_rbac_viewer_cannot_save(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("PAYROLL_AUTO_APPLY_DDL", "1")
    monkeypatch.setenv("SECRET_KEY", "secret")
    from app.main import create_app
    from core.db import init_database, get_sessionmaker

    init_database(auto_apply_ddl=True)
    SessionLocal = get_sessionmaker()
    cid, slug = _seed_company(SessionLocal)

    app = create_app()
    client = TestClient(app)
    viewer = _make_token(cid, slug, roles=["viewer"])
    resp = client.post(
        f"/api/portal/{slug}/payroll/2025/10",
        headers={"X-API-Token": viewer, "Content-Type": "application/json"},
        json={"rows": [{"사원코드": "E01", "사원명": "홍길동", "기본급": 1000000}]},
    )
    assert resp.status_code == 403


def test_rbac_manager_can_save(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("PAYROLL_AUTO_APPLY_DDL", "1")
    monkeypatch.setenv("SECRET_KEY", "secret")
    from app.main import create_app
    from core.db import init_database, get_sessionmaker

    init_database(auto_apply_ddl=True)
    SessionLocal = get_sessionmaker()
    cid, slug = _seed_company(SessionLocal)

    app = create_app()
    client = TestClient(app)
    mgr = _make_token(cid, slug, roles=["payroll_manager"])
    resp = client.post(
        f"/api/portal/{slug}/payroll/2025/10",
        headers={"X-API-Token": mgr, "Content-Type": "application/json"},
        json={"rows": [{"사원코드": "E01", "사원명": "홍길동", "기본급": 1000000}]},
    )
    assert resp.status_code in (200, 201)
    assert resp.json().get("ok") is True

