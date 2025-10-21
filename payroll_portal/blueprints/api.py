from __future__ import annotations

import datetime as dt
from typing import Optional

import json

from flask import Blueprint, request, session
from sqlalchemy.orm import Session
from sqlalchemy import text

from payroll_shared.fields import cleanup_duplicate_extra_fields
from payroll_shared.models import ExtraField, FieldPref, MonthlyPayroll

from ..app.extensions import db_session
from ..dao import companies as companies_dao, payrolls as payrolls_dao
from ..services.extra_fields import add_extra_field
from ..services.calculation import compute_deductions
from ..services.reporting import monthly_summary
from ..services.payroll import (
    build_columns_for_company,
    compute_withholding_tax,
    load_field_prefs,
)


bp = Blueprint("api", __name__)


def _get_session() -> Session:
    return db_session()


def _auth_company(slug: str):
    cid = session.get("company_id")
    cslug = session.get("company_slug")
    if not cid or cslug != slug:
        return None
    return cid


def _company(session_db: Session, slug: str):
    return companies_dao.get_by_slug(session_db, slug)


@bp.get("/healthz")
def healthz():
    try:
        s = _get_session()
        s.execute(text("SELECT 1"))
        return {"ok": True, "status": "healthy"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500


@bp.get("/livez")
def livez():
    return {"ok": True}


@bp.get("/readyz")
def readyz():
    try:
        s = _get_session()
        s.execute(text("SELECT 1"))
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500


@bp.get("/portal/<slug>/withholding")
def api_withholding(slug: str):
    if not _auth_company(slug):
        return {"ok": False, "error": "unauthorized"}, 401
    year = request.args.get("year", type=int)
    dependents = request.args.get("dep", type=int)
    wage = request.args.get("wage", type=int)
    if year is None or dependents is None or wage is None:
        return {"ok": False, "error": "year/dep/wage 필요"}, 400
    s = _get_session()
    tax = compute_withholding_tax(s, year, dependents, wage)
    return {
        "ok": True,
        "year": year,
        "dep": dependents,
        "wage": wage,
        "tax": int(tax),
        "local_tax": int(round((tax or 0) * 0.1)),
    }


@bp.post("/portal/<slug>/fields/group-config")
def api_group_config(slug: str):
    if not _auth_company(slug):
        return {"ok": False, "error": "unauthorized"}, 401
    data = request.get_json(silent=True) or {}
    group_map = data.get("map") or data.get("group") or {}
    alias_map = data.get("alias") or {}
    if not isinstance(group_map, dict) or not isinstance(alias_map, dict):
        return {"ok": False, "error": "잘못된 형식"}, 400
    s = _get_session()
    company = companies_dao.get_by_slug(s, slug)
    if not company:
        return {"ok": False, "error": "not found"}, 404
    for field, grp in group_map.items():
        grp = (grp or "none").strip()
        pref = (
            s.query(FieldPref)
            .filter(FieldPref.company_id == company.id, FieldPref.field == field)
            .first()
        )
        if not pref:
            pref = FieldPref(company_id=company.id, field=field, group=grp)
            s.add(pref)
        else:
            pref.group = grp
    for field, alias in alias_map.items():
        alias = (alias or "").strip()
        pref = (
            s.query(FieldPref)
            .filter(FieldPref.company_id == company.id, FieldPref.field == field)
            .first()
        )
        if not pref:
            pref = FieldPref(company_id=company.id, field=field, alias=alias)
            s.add(pref)
        else:
            pref.alias = alias
    s.commit()
    cleanup_duplicate_extra_fields(s, company)
    return {"ok": True}


@bp.get("/admin/withholding/sample")
def api_admin_withholding_sample():
    if not session.get("is_admin"):
        return {"ok": False, "error": "unauthorized"}, 401
    year = request.args.get("year", type=int)
    dep = request.args.get("dep", type=int)
    wage = request.args.get("wage", type=int)
    if not (year and dep is not None and wage is not None):
        return {"ok": False, "error": "year/dep/wage 필요"}, 400
    s = _get_session()
    tax = compute_withholding_tax(s, year, dep, wage)
    return {
        "ok": True,
        "year": year,
        "dep": dep,
        "wage": wage,
        "tax": int(tax),
        "local_tax": int(round((tax or 0) * 0.1)),
    }


@bp.get("/portal/<slug>/payroll/<int:year>/<int:month>")
def api_get_payroll(slug: str, year: int, month: int):
    if not _auth_company(slug):
        return {"ok": False, "error": "unauthorized"}, 401
    s = _get_session()
    company = _company(s, slug)
    if not company:
        return {"ok": False, "error": "not found"}, 404
    record = payrolls_dao.get_by_month(s, company.id, year, month)
    if not record:
        return {"ok": True, "rows": []}
    try:
        rows = json.loads(record.rows_json or "[]")
    except Exception:
        rows = []
    return {"ok": True, "rows": rows}


@bp.post("/portal/<slug>/fields/add")
def api_add_field(slug: str):
    if not _auth_company(slug):
        return {"ok": False, "error": "unauthorized"}, 401
    data = request.get_json(silent=True) or {}
    label = (data.get("label") or "").strip()
    typ = (data.get("typ") or "number").strip()
    s = _get_session()
    company = _company(s, slug)
    if not company:
        return {"ok": False, "error": "not found"}, 404
    try:
        field = add_extra_field(s, company, label, typ)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}, 400
    if not field:
        return {"ok": False, "error": "추가 실패"}, 400
    return {"ok": True, "field": {"name": field.name, "label": field.label, "typ": field.typ}}


@bp.post("/portal/<slug>/fields/delete")
def api_delete_field(slug: str):
    if not _auth_company(slug):
        return {"ok": False, "error": "unauthorized"}, 401
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return {"ok": False, "error": "name 필요"}, 400
    s = _get_session()
    company = _company(s, slug)
    if not company:
        return {"ok": False, "error": "not found"}, 404
    field = (
        s.query(ExtraField)
        .filter(ExtraField.company_id == company.id, ExtraField.name == name)
        .first()
    )
    if not field:
        return {"ok": False, "error": "항목을 찾을 수 없습니다."}, 404
    s.delete(field)
    s.commit()
    return {"ok": True}


@bp.get("/portal/<slug>/fields/calc-config")
def api_calc_config(slug: str):
    if not _auth_company(slug):
        return {"ok": False, "error": "unauthorized"}, 401
    s = _get_session()
    company = _company(s, slug)
    if not company:
        return {"ok": False, "error": "not found"}, 404
    _, _, _, include_map = load_field_prefs(s, company)
    return {"ok": True, "include": include_map}


@bp.post("/portal/<slug>/fields/calc-config")
def api_save_calc_config(slug: str):
    if not _auth_company(slug):
        return {"ok": False, "error": "unauthorized"}, 401
    data = request.get_json(silent=True) or {}
    inc = data.get("include") or {}
    nhis = inc.get("nhis") if isinstance(inc, dict) else {}
    ei = inc.get("ei") if isinstance(inc, dict) else {}
    if not isinstance(nhis, dict) or not isinstance(ei, dict):
        return {"ok": False, "error": "잘못된 형식"}, 400
    s = _get_session()
    company = _company(s, slug)
    if not company:
        return {"ok": False, "error": "not found"}, 404
    nhis_keys = {k for k, v in nhis.items() if v}
    ei_keys = {k for k, v in ei.items() if v}
    prefs = (
        s.query(FieldPref)
        .filter(FieldPref.company_id == company.id)
        .all()
    )
    pref_map = {pref.field: pref for pref in prefs}
    for field in nhis_keys | ei_keys:
        pref = pref_map.get(field)
        if not pref:
            pref = FieldPref(company_id=company.id, field=field)
            s.add(pref)
            pref_map[field] = pref
        pref.ins_nhis = field in nhis_keys
        pref.ins_ei = field in ei_keys
    for pref in prefs:
        if pref.field not in nhis_keys:
            pref.ins_nhis = False
        if pref.field not in ei_keys:
            pref.ins_ei = False
    s.commit()
    return {"ok": True}


@bp.get("/portal/<slug>/fields/exempt-config")
def api_exempt_config(slug: str):
    if not _auth_company(slug):
        return {"ok": False, "error": "unauthorized"}, 401
    s = _get_session()
    company = _company(s, slug)
    if not company:
        return {"ok": False, "error": "not found"}, 404
    _, _, ex_map, _ = load_field_prefs(s, company)
    return {"ok": True, "exempt": ex_map}


@bp.post("/portal/<slug>/fields/exempt-config")
def api_save_exempt_config(slug: str):
    if not _auth_company(slug):
        return {"ok": False, "error": "unauthorized"}, 401
    data = request.get_json(silent=True) or {}
    raw = data.get("exempt") or data.get("ov") or {}
    if not isinstance(raw, dict):
        return {"ok": False, "error": "잘못된 형식"}, 400
    s = _get_session()
    company = _company(s, slug)
    if not company:
        return {"ok": False, "error": "not found"}, 404
    for field, conf in raw.items():
        pref = (
            s.query(FieldPref)
            .filter(FieldPref.company_id == company.id, FieldPref.field == field)
            .first()
        )
        if not pref:
            pref = FieldPref(company_id=company.id, field=field)
            s.add(pref)
        enabled = bool((conf or {}).get("enabled"))
        limit = int((conf or {}).get("limit") or 0)
        pref.exempt_enabled = enabled and limit > 0
        pref.exempt_limit = limit if enabled else 0
    s.commit()
    return {"ok": True}


@bp.post("/portal/<slug>/calc/deductions")
def api_calc_deductions(slug: str, year: int = None):
    if not _auth_company(slug):
        return {"ok": False, "error": "unauthorized"}, 401
    data = request.get_json(silent=True) or {}
    row = data.get("row") or {}
    year_value = data.get("year") or year
    if not year_value:
        return {"ok": False, "error": "year 필요"}, 400
    s = _get_session()
    company = _company(s, slug)
    if not company:
        return {"ok": False, "error": "not found"}, 404
    amounts, meta = compute_deductions(s, company, row, int(year_value))
    return {"ok": True, "amounts": amounts, "meta": meta}


@bp.get("/portal/<slug>/reports/monthly-summary")
def api_monthly_summary(slug: str):
    if not _auth_company(slug):
        return {"ok": False, "error": "unauthorized"}, 401
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    if not (year and month):
        return {"ok": False, "error": "year/month 필요"}, 400
    s = _get_session()
    company = _company(s, slug)
    if not company:
        return {"ok": False, "error": "not found"}, 404
    summary = monthly_summary(s, company.id, year, month)
    return {"ok": True, "summary": summary}
