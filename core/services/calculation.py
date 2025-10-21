from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, ROUND_HALF_DOWN, ROUND_UP, ROUND_DOWN
from typing import Dict, Tuple

from sqlalchemy.orm import Session

from core.models import Company

from .payroll import build_columns_for_company, compute_withholding_tax, insurance_settings, load_field_prefs

DEDUCTION_FIELDS = {"국민연금", "건강보험", "장기요양보험", "고용보험", "소득세", "지방소득세"}


def _to_int(val) -> int:
    if val in (None, "", 0):
        return 0
    try:
        if isinstance(val, (int, float)):
            return int(val)
        return int(Decimal(str(val).replace(",", "")))
    except Exception:
        return 0


def _round_amount(amount: Decimal, step: int, mode: str) -> int:
    if step <= 0:
        step = 1
    q = Decimal(step)
    scaled = amount / q
    if mode == "floor":
        rounded = scaled.to_integral_value(rounding=ROUND_DOWN)
    elif mode == "ceil":
        rounded = scaled.to_integral_value(rounding=ROUND_UP)
    elif mode == "half_down":
        rounded = scaled.to_integral_value(rounding=ROUND_HALF_DOWN)
    else:
        rounded = scaled.to_integral_value(rounding=ROUND_HALF_UP)
    return int(rounded * q)


def _selected_base(values: Dict[str, int], selected: Dict[str, bool], exemptions: Dict[str, int]) -> int:
    subtotal = 0
    seen = set()
    for field, flag in (selected or {}).items():
        if not flag or field in seen:
            continue
        seen.add(field)
        subtotal += max(0, int(values.get(field, 0)))
    for field, limit in (exemptions or {}).items():
        if selected.get(field):
            val = max(0, int(values.get(field, 0)))
            subtotal -= min(val, limit)
    return max(0, subtotal)


def _default_base(values: Dict[str, int], earnings: set[str], exemptions: Dict[str, int]) -> int:
    base = 0
    for field in earnings:
        if field in DEDUCTION_FIELDS:
            continue
        base += max(0, int(values.get(field, 0)))
    for field, limit in exemptions.items():
        val = max(0, int(values.get(field, 0)))
        base -= min(val, limit)
    return max(0, base)


def compute_deductions(
    session: Session,
    company: Company,
    row: Dict[str, object],
    year: int,
) -> Tuple[Dict[str, int], Dict[str, object]]:
    cols, _, _, _, extras = build_columns_for_company(session, company)
    group_map, alias_map, exempt_map, include_map = load_field_prefs(session, company)
    insurance = insurance_settings()

    # Build earnings/deductions set
    earnings_fields = set()
    deduction_fields = set()
    for name, _, _ in cols:
        grp = group_map.get(name, "none")
        if grp == "earn":
            earnings_fields.add(name)
        elif grp == "deduct":
            deduction_fields.add(name)
    for ef in extras:
        grp = group_map.get(ef.name, "none")
        if grp == "earn":
            earnings_fields.add(ef.name)
        elif grp == "deduct":
            deduction_fields.add(ef.name)

    if not earnings_fields:
        for name, _, _ in cols:
            if name not in DEDUCTION_FIELDS:
                earnings_fields.add(name)

    # Normalize numeric values
    values: Dict[str, int] = {}
    for key, val in (row or {}).items():
        values[key] = _to_int(val)

    # Build exemptions map (field -> limit)
    exemptions: Dict[str, int] = {}
    for field, conf in (exempt_map or {}).items():
        if not conf:
            continue
        if conf.get("enabled"):
            exemptions[field] = max(0, int(conf.get("limit") or 0))

    # When exemptions are defined by label, ensure alias label mapping also counts
    for field, limit in list(exemptions.items()):
        label = alias_map.get(field)
        if label:
            exemptions[label] = limit

    default_base = _default_base(values, earnings_fields, exemptions)

    # National Pension base: prefer explicit field
    base_field = row.get("기준보수월액")
    if base_field is not None:
        base_np = max(0, _to_int(base_field))
    else:
        base_np = default_base

    inc_nhis = include_map.get("nhis", {})
    inc_ei = include_map.get("ei", {})

    base_nhis = _selected_base(values, inc_nhis, exemptions) if inc_nhis else default_base
    base_ei = _selected_base(values, inc_ei, exemptions) if inc_ei else default_base

    def calc_amount(cfg: Dict[str, object], rate_key: str, base: int) -> int:
        cfg = cfg or {}
        base_d = Decimal(max(0, base))
        min_base = cfg.get("min_base")
        max_base = cfg.get("max_base")
        if min_base is not None:
            base_d = max(base_d, Decimal(min_base))
        if max_base is not None:
            base_d = min(base_d, Decimal(max_base))
        rate = Decimal(cfg.get(rate_key, 0) or 0)
        raw = base_d * rate
        step = int(cfg.get("round_to") or 10)
        mode = str(cfg.get("rounding") or "round")
        return _round_amount(raw, step, mode)

    nps_cfg = insurance.get("nps", {})
    nhis_cfg = insurance.get("nhis", {})
    ei_cfg = insurance.get("ei", {})

    national_pension = calc_amount(nps_cfg, "rate", base_np)
    health_insurance = calc_amount(nhis_cfg, "rate", base_nhis)

    ltc_rate = Decimal(nhis_cfg.get("ltc_rate", Decimal("0.1295")))
    ltc_step = int(nhis_cfg.get("ltc_round_to") or nhis_cfg.get("round_to") or 10)
    ltc_mode = str(nhis_cfg.get("ltc_rounding") or nhis_cfg.get("rounding") or "round")
    long_term_care = _round_amount(Decimal(health_insurance) * ltc_rate, ltc_step, ltc_mode)

    employment_insurance = calc_amount(ei_cfg, "rate", base_ei)

    dependents = _to_int(row.get("부양가족수") or row.get("부양 가족수") or 1)
    wage = default_base
    income_tax = compute_withholding_tax(session, year, dependents, wage)
    local_tax = int(round((income_tax or 0) * 0.1))

    metadata = {
        "default_base": default_base,
        "base_national_pension": base_np,
        "base_health_insurance": base_nhis,
        "base_employment_insurance": base_ei,
        "dependents": dependents,
        "wage": wage,
    }

    amounts = {
        "national_pension": national_pension,
        "health_insurance": health_insurance,
        "long_term_care": long_term_care,
        "employment_insurance": employment_insurance,
        "income_tax": income_tax,
        "local_income_tax": local_tax,
    }

    return amounts, metadata
