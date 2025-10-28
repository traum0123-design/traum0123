from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_portal_export_redirects_to_api(monkeypatch):
    # Use in-memory DB
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ADMIN_PASSWORD", "testpw")

    from core.db import init_database, get_sessionmaker
    from core.models import Company, MonthlyPayroll

    init_database(auto_apply_ddl=True)
    SessionLocal = get_sessionmaker()

    import secrets
    slug = f"legacy-{secrets.token_hex(3)}"
    with SessionLocal() as db:  # type: Session
        c = Company(name="Demo", slug=slug, access_hash="x", token_key="", created_at=dt.datetime.now(dt.UTC))
        db.add(c)
        db.commit()
        db.refresh(c)
        db.add(MonthlyPayroll(company_id=c.id, year=2024, month=5, rows_json="[]"))
        db.commit()

    from app.main import create_app
    app = create_app()
    client = TestClient(app)
    r = client.get(f"/portal/{slug}/export/2024/5", follow_redirects=False)
    assert r.status_code in (301, 302, 303, 307, 308)
    assert r.headers.get("deprecation") == "true"
    loc = r.headers.get("location", "")
    assert loc.endswith(f"/api/portal/{slug}/export/2024/5")
