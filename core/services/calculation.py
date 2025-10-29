from __future__ import annotations

from decimal import ROUND_DOWN, ROUND_HALF_DOWN, ROUND_HALF_UP, ROUND_UP, Decimal
import datetime as dt

from sqlalchemy.orm import Session

from core.models import Company

from .payroll import (
    build_columns_for_company,
    compute_withholding_tax,
    insurance_settings,
    load_field_prefs,
)
from .policy import get_policy

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


def _round_amount_cfg(amount: int | Decimal, cfg: dict[str, object], *, step_key: str = "round_to", mode_key: str = "rounding", default_step: int = 10, default_mode: str = "round") -> int:
    try:
        val = Decimal(amount)
    except Exception:
        val = Decimal(0)
    step_val = cfg.get(step_key)
    try:
        step = int(float(str(step_val))) if step_val is not None else default_step
    except Exception:
        step = default_step
    mode = str(cfg.get(mode_key) or default_mode)
    return _round_amount(val, step, mode)


def proration_factor_for_month(row: dict, *, year: int | None = None, month: int | None = None) -> tuple[int, int]:
    """표준 일할 계수 산출(입사/퇴사/휴직 반영).

    - 월 구간은 행 내 '월 시작일'/'월 말일'이 있으면 우선 사용, 없으면 year/month로 달의 1~말일.
    - 상여 등 비정규 항목은 일할에서 제외하는 정책은 호출부에서 처리.
    """
    from core.utils.dates import parse_date_flex
    import calendar

    # Determine month span
    s_val = row.get("월 시작일")
    e_val = row.get("월 말일")
    s_date = parse_date_flex(s_val)
    e_date = parse_date_flex(e_val)
    if not s_date or not e_date or s_date > e_date:
        if year is None or month is None:
            today = dt.date.today()
            y, m = today.year, today.month
        else:
            y, m = int(year), int(month)
        s_date = dt.date(y, m, 1)
        e_date = dt.date(y, m, calendar.monthrange(y, m)[1])

    def overlap_days(a1: dt.date, a2: dt.date, b1: dt.date, b2: dt.date) -> int:
        s = max(a1, b1)
        e = min(a2, b2)
        if e < s:
            return 0
        return (e - s).days + 1

    total = (e_date - s_date).days + 1
    join = parse_date_flex(row.get("입사일"))
    leave = parse_date_flex(row.get("퇴사일"))
    act_s = max(s_date, join) if join else s_date
    act_e = min(e_date, leave) if leave else e_date
    if act_e < act_s:
        return 0, total
    days = (act_e - act_s).days + 1
    leave_s = parse_date_flex(row.get("휴직일"))
    leave_e = parse_date_flex(row.get("휴직종료일")) or e_date if leave_s else None
    if leave_s:
        days -= overlap_days(act_s, act_e, max(s_date, leave_s), min(e_date, leave_e))
        days = max(0, days)
    return days, total


def _selected_base(values: dict[str, int], selected: dict[str, bool], exemptions: dict[str, int]) -> int:
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


def _default_base(values: dict[str, int], earnings: set[str], exemptions: dict[str, int]) -> int:
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
    row: dict[str, object],
    year: int,
) -> tuple[dict[str, int], dict[str, object]]:
    cols, _, _, _, extras = build_columns_for_company(session, company)
    group_map, alias_map, exempt_map, include_map = load_field_prefs(session, company)
    # Load defaults then override by per-company/year policy if present
    insurance = insurance_settings()
    try:
        pol = get_policy(session, company.id, year)
        for k in ("nps", "nhis", "ei"):
            if isinstance(pol.get(k), dict):
                insurance[k].update(pol[k])
        if isinstance(pol.get("local_tax"), dict):
            # consumed below when computing local tax
            pass
    except Exception:
        pass

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
    values: dict[str, int] = {}
    for key, val in (row or {}).items():
        values[key] = _to_int(val)

    # Build exemptions map (field -> limit)
    exemptions: dict[str, int] = {}
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

    def calc_amount(cfg: dict[str, object], rate_key: str, base: int) -> int:
        cfg = cfg or {}
        base_d = Decimal(max(0, base))
        min_base = cfg.get("min_base")
        max_base = cfg.get("max_base")
        if min_base is not None:
            try:
                base_d = max(base_d, Decimal(str(min_base)))
            except Exception:
                pass
        if max_base is not None:
            try:
                base_d = min(base_d, Decimal(str(max_base)))
            except Exception:
                pass
        try:
            rate = Decimal(str(cfg.get(rate_key, 0) or 0))
        except Exception:
            rate = Decimal(0)
        raw = base_d * rate
        step_val = cfg.get("round_to")
        try:
            step = int(float(str(step_val))) if step_val is not None else 10
        except Exception:
            step = 10
        mode = str(cfg.get("rounding") or "round")
        return _round_amount(raw, step, mode)

    nps_cfg = insurance.get("nps", {})
    nhis_cfg = insurance.get("nhis", {})
    ei_cfg = insurance.get("ei", {})

    national_pension = calc_amount(nps_cfg, "rate", base_np)
    health_insurance = calc_amount(nhis_cfg, "rate", base_nhis)

    try:
        ltc_rate = Decimal(str(nhis_cfg.get("ltc_rate", 0.1295)))
    except Exception:
        ltc_rate = Decimal("0.1295")
    ltc_step = int(nhis_cfg.get("ltc_round_to") or nhis_cfg.get("round_to") or 10)
    ltc_mode = str(nhis_cfg.get("ltc_rounding") or nhis_cfg.get("rounding") or "round")
    long_term_care = _round_amount(Decimal(health_insurance) * ltc_rate, ltc_step, ltc_mode)

    employment_insurance = calc_amount(ei_cfg, "rate", base_ei)

    dependents = _to_int(row.get("부양가족수") or row.get("부양 가족수") or 1)
    wage = default_base
    income_tax = compute_withholding_tax(session, year, dependents, wage)
    # 지방소득세 라운딩 규칙: 설정(TAX_LOCAL_*) 기반으로 고정
    # Prefer policy local_tax config if available
    _pol_local = {}
    try:
        pol = get_policy(session, company.id, year)
        _pol_local = pol.get("local_tax") or {}
    except Exception:
        _pol_local = {}
    tax_cfg = {
        "rate": Decimal(str((_pol_local.get("rate") if isinstance(_pol_local, dict) else 0.1) or 0.1)),
        "round_to": int((_pol_local.get("round_to") if isinstance(_pol_local, dict) else 10) or 10),
        "rounding": str((_pol_local.get("rounding") if isinstance(_pol_local, dict) else "round") or "round"),
    }
    local_raw = Decimal(income_tax or 0) * Decimal(str(tax_cfg.get("rate", Decimal("0.1"))))
    local_tax = _round_amount_cfg(local_raw, tax_cfg)

    metadata: dict[str, object] = {
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
