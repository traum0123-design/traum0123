from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_portal_export_sets_disposition_header(monkeypatch):
    # In-memory DB
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")

    from app.main import create_app
    from core.db import get_sessionmaker, init_database
    from core.models import Company, MonthlyPayroll
    import secrets
    from core.services.auth import issue_company_token

    init_database(auto_apply_ddl=True)
    SessionLocal = get_sessionmaker()
    slug = f"exp-{secrets.token_hex(3)}"
    with SessionLocal() as db:  # type: Session
        company = Company(
            name="테스트회사",
            slug=slug,
            access_hash="x",
            token_key="",
            created_at=dt.datetime.now(dt.timezone.utc),
        )
        db.add(company)
        db.commit()
        db.refresh(company)
        db.add(MonthlyPayroll(company_id=company.id, year=2024, month=5, rows_json="[]"))
        db.commit()
        token = issue_company_token(db, company)

    app = create_app()
    client = TestClient(app)
    resp = client.get(
        f"/portal/{slug}/export/2024/5",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    cd = resp.headers.get("content-disposition", "")
    assert "attachment" in cd.lower()
    assert slug in cd
    assert resp.headers.get("content-type", "").startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
