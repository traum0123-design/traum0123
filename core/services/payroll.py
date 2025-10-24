from __future__ import annotations

import datetime as dt
import json
import os
from typing import Dict, Iterable, List, Tuple

from sqlalchemy.orm import Session

from core.models import Company, ExtraField, FieldPref, MonthlyPayroll, WithholdingCell
from core.schema import (
    DEFAULT_BOOL_FIELDS,
    DEFAULT_COLUMNS,
    DEFAULT_DATE_FIELDS,
    DEFAULT_NUMERIC_FIELDS,
)
from core.utils.dates import parse_date_flex

from .extra_fields import ensure_defaults, normalize_label


def _env_float(key: str, default: float | None) -> float | None:
    try:
        val = os.environ.get(key)
        if val is None or val == "":
            return default
        return float(val)
    except Exception:
        return default


def _env_int(key: str, default: int | None) -> int | None:
    try:
        val = os.environ.get(key)
        if val is None or val == "":
            return default
        return int(val)
    except Exception:
        return default


def _env_str(key: str, default: str) -> str:
    val = os.environ.get(key)
    if val is None or val == "":
        return default
    return val


INSURANCE_CONFIG = {
    "base_exemptions": {
        "식대": 200_000,
        "자가운전보조금": 200_000,
    },
    "nps": {
        "rate": _env_float("INS_NPS_RATE", 0.045),
        "min_base": _env_float("INS_NPS_MIN_BASE", None),
        "max_base": _env_float("INS_NPS_MAX_BASE", None),
        "round_to": _env_int("INS_NPS_ROUND_TO", 10),
        "rounding": _env_str("INS_NPS_ROUNDING", "round"),
    },
    "nhis": {
        "rate": _env_float("INS_NHIS_RATE", 0.03545),
        "min_base": _env_float("INS_NHIS_MIN_BASE", None),
        "max_base": _env_float("INS_NHIS_MAX_BASE", None),
        "round_to": _env_int("INS_NHIS_ROUND_TO", 10),
        "rounding": _env_str("INS_NHIS_ROUNDING", "round"),
        "ltc_rate": _env_float("INS_LTC_RATE", 0.1295),
        "ltc_round_to": _env_int("INS_LTC_ROUND_TO", 10),
        "ltc_rounding": _env_str("INS_LTC_ROUNDING", "round"),
    },
    "ei": {
        "rate": _env_float("INS_EI_RATE", 0.009),
        "min_base": _env_float("INS_EI_MIN_BASE", None),
        "max_base": _env_float("INS_EI_MAX_BASE", None),
        "round_to": _env_int("INS_EI_ROUND_TO", 10),
        "rounding": _env_str("INS_EI_ROUNDING", "round"),
    },
}

try:
    ex_raw = os.environ.get("INS_BASE_EXEMPTIONS")
    if ex_raw:
        parsed = json.loads(ex_raw)
        if isinstance(parsed, dict):
            INSURANCE_CONFIG["base_exemptions"] = parsed
except Exception:
    pass


def current_year_month() -> Tuple[int, int]:
    today = dt.date.today()
    return today.year, today.month


def build_columns_for_company(
    session: Session,
    company: Company,
) -> Tuple[
    List[Tuple[str, str, str]],
    set[str],
    set[str],
    set[str],
    List[ExtraField],
]:
    ensure_defaults(session, company)
    base_cols = list(DEFAULT_COLUMNS)
    numeric_fields = set(DEFAULT_NUMERIC_FIELDS)
    date_fields = set(DEFAULT_DATE_FIELDS)
    bool_fields = set(DEFAULT_BOOL_FIELDS)

    extras = _sorted_unique_extras(session, company)
    for ef in extras:
        base_cols.append((ef.name, ef.label, ef.typ))
        if ef.typ == "number":
            numeric_fields.add(ef.name)
        elif ef.typ == "date":
            date_fields.add(ef.name)
    return base_cols, numeric_fields, date_fields, bool_fields, extras


def _sorted_unique_extras(session: Session, company: Company) -> List[ExtraField]:
    rows: List[ExtraField] = (
        session.query(ExtraField)
        .filter(ExtraField.company_id == company.id)
        .order_by(ExtraField.position.asc(), ExtraField.id.asc())
        .all()
    )
    deduped: List[ExtraField] = []
    seen: set[str] = set()
    for ef in rows:
        norm = normalize_label(ef.label)
        if norm in seen:
            continue
        seen.add(norm)
        deduped.append(ef)
    return deduped


def load_field_prefs(session: Session, company: Company):
    prefs = (
        session.query(FieldPref)
        .filter(FieldPref.company_id == company.id)
        .all()
    )
    group_map: Dict[str, str] = {}
    alias_map: Dict[str, str] = {}
    # Start with base exemptions from config (enabled if limit > 0)
    exempt_map: Dict[str, dict] = {}
    from typing import cast
    base_ex = cast(dict[str, object], INSURANCE_CONFIG.get("base_exemptions", {}) or {})
    for name, limit in base_ex.items():
        try:
            limit_val = int(float(str(limit or 0)))
        except Exception:
            limit_val = 0
        if limit_val <= 0:
            continue
        exempt_map[name] = {"enabled": True, "limit": limit_val}
    include_map: Dict[str, dict] = {"nhis": {}, "ei": {}}
    for pref in prefs:
        if pref.group and pref.group != "none":
            group_map[pref.field] = pref.group
        if pref.alias:
            alias_map[pref.field] = pref.alias
        limit_raw = getattr(pref, "exempt_limit", 0)
        try:
            limit_val = int(limit_raw or 0)
        except Exception:
            limit_val = 0
        enabled = bool(getattr(pref, "exempt_enabled", False) and limit_val > 0)
        existing = exempt_map.get(pref.field)
        if not enabled and limit_val <= 0 and existing:
            # Preserve configured base exemptions unless an explicit override exists.
            pass
        else:
            # Always send back the entry even if disabled so that clients can honour explicit override
            exempt_map[pref.field] = {"enabled": enabled, "limit": limit_val}
        if getattr(pref, "ins_nhis", False):
            include_map["nhis"][pref.field] = True
        if getattr(pref, "ins_ei", False):
            include_map["ei"][pref.field] = True
    return group_map, alias_map, exempt_map, include_map


def compute_withholding_tax(
    session: Session,
    year: int,
    dependents: int,
    wage: int,
) -> int:
    row = (
        session.query(WithholdingCell)
        .filter(
            WithholdingCell.year == year,
            WithholdingCell.dependents == dependents,
            WithholdingCell.wage <= wage,
        )
        .order_by(WithholdingCell.wage.desc())
        .first()
    )
    return int(row.tax) if row else 0


def compute_deductions(
    session: Session,
    company: Company,
    row: dict,
    year: int,
):
    """Wrapper to keep legacy import paths working for deduction calculations."""
    from .calculation import compute_deductions as _compute_deductions

    return _compute_deductions(session, company, row, year)


def parse_rows(
    form_data,
    allowed_columns: Iterable[Tuple[str, str, str]],
    numeric_fields: set[str],
    date_fields: set[str],
    bool_fields: set[str],
) -> List[dict]:
    bucket: Dict[int, dict] = {}
    allowed = {col[0] for col in allowed_columns}

    for key, value in form_data.items():
        if not key.startswith("rows["):
            continue
        try:
            left, right = key.split("][", 1)
            idx = int(left[5:])
            field = right[:-1]
        except Exception:
            continue
        if field not in allowed:
            continue
        bucket.setdefault(idx, {})[field] = value

    rows: List[dict] = []
    for idx in sorted(bucket.keys()):
        row = bucket[idx]
        if not any(str(v).strip() for v in row.values()):
            continue
        for f in numeric_fields:
            if f in row:
                row[f] = _parse_int(row.get(f))
        for f in bool_fields:
            if f in row:
                row[f] = _parse_bool(row.get(f))
        for f in date_fields:
            if f in row:
                parsed = parse_date_flex(row.get(f))
                row[f] = parsed.isoformat() if parsed else ""
        rows.append(row)
    return rows


def _parse_int(value) -> int:
    if value in (None, ""):
        return 0
    s = str(value).strip().replace(",", "")
    if not s:
        return 0
    try:
        return int(float(s))
    except Exception:
        return 0


def _parse_bool(value) -> bool:
    if value is None:
        return False
    s = str(value).strip().lower()
    return s in {"true", "1", "y", "yes", "on", "t", "예", "체크"}


def has_meaningful_data(rows_json: str) -> bool:
    try:
        rows = json.loads(rows_json or "[]")
    except Exception:
        return False
    for row in rows or []:
        if str(row.get("사원명", "")).strip() or str(row.get("사원코드", "")).strip():
            return True
        for value in row.values():
            try:
                val = int(float(str(value).replace(",", "").strip()))
                if val != 0:
                    return True
            except Exception:
                continue
    return False


def insurance_settings() -> dict:
    return json.loads(json.dumps(INSURANCE_CONFIG))
