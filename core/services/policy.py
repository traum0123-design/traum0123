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

# Year-specific default overlays (used when no explicit policy is stored).
# Note: This is a pragmatic fallback so environments without DB/ENV policy
# still apply contemporary bounds. For precise half-year changes (e.g. NPS
# July cycle), prefer setting an explicit policy via /api/admin/policy.
YEAR_DEFAULTS: dict[int, dict] = {
    # 2025 defaults
    2025: {
        # 국민연금 기준소득월액 (2025-07-01 ~ 2026-06-30)
        "nps": {"min_base": 400_000, "max_base": 6_370_000},
        # 건강보험 직장가입자 보수월액 상·하한 (2025-01-01 ~ 2025-12-31, 역산 기준)
        "nhis": {"min_base": 278_984, "max_base": 127_056_982},
        # EI(고용보험): 보험료 산정 상·하한 없음 → 지정 생략
    }
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
    # Apply year-specific defaults when available (shallow overlay per section)
    try:
        y = int(year or 0)
        overlay = YEAR_DEFAULTS.get(y)
        if isinstance(overlay, dict):
            for k, v in overlay.items():
                if isinstance(v, dict):
                    sect = base.get(k) or {}
                    if isinstance(sect, dict):
                        sect.update(v)
                        base[k] = sect
                    else:
                        base[k] = v
                else:
                    base[k] = v
    except Exception:
        pass
    if not row:
        return base
    try:
        d = json.loads(row.policy_json or "{}")
        if isinstance(d, dict):
            base.update(d)
    except Exception:
        pass
    return base
