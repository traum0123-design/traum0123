from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy.orm import Session

from core.models import PolicySetting

DEFAULT_POLICY = {
    "nps": {},
    "nhis": {},
    "ei": {},
    "local_tax": {"rate": 0.1, "round_to": 10, "rounding": "round"},
    "proration": {"exclude_bonus": True},
}


def get_policy(session: Session, company_id: int | None, year: int | None) -> dict[str, Any]:
    """Load policy for a company/year, fallback to global (company_id is NULL), then defaults.
    A simple last-write-wins record per (company_id, year).
    """
    q = session.query(PolicySetting).order_by(PolicySetting.id.desc())
    if company_id is not None:
        row = (
            q.filter(PolicySetting.company_id == int(company_id), PolicySetting.year == int(year or 0)).first()
            or q.filter(PolicySetting.company_id.is_(None), PolicySetting.year == int(year or 0)).first()
        )
    else:
        row = q.filter(PolicySetting.company_id.is_(None), PolicySetting.year == int(year or 0)).first()
    base = json.loads(json.dumps(DEFAULT_POLICY))
    if not row:
        return base
    try:
        d = json.loads(row.policy_json or "{}")
        if isinstance(d, dict):
            base.update(d)
    except Exception:
        pass
    return base

