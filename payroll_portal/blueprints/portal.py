from __future__ import annotations

import json
import secrets
from typing import Optional

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from sqlalchemy.orm import Session

from payroll_shared.models import Company, FieldPref, MonthlyPayroll

from ..app.extensions import db_session
from ..dao import companies as companies_dao, payrolls as payrolls_dao
from ..services import companies as company_service
from ..services.extra_fields import add_extra_field, ensure_defaults
from ..services.payroll import (
    build_columns_for_company,
    current_year_month,
    has_meaningful_data,
    insurance_settings,
    load_field_prefs,
    parse_rows,
)
from ..services.persistence import sync_normalized_rows
from ..services.rate_limit import limiter, portal_login_key


bp = Blueprint("portal", __name__, template_folder="../templates")


def _get_session() -> Session:
    return db_session()


def _company_required(slug: str):
    cid = session.get("company_id")
    cslug = session.get("company_slug")
    if not cid or cslug != slug:
        return redirect(url_for("portal.login", slug=slug))
    return None


def _load_company(session_db: Session, slug: str) -> Optional[Company]:
    return companies_dao.get_by_slug(session_db, slug)


@bp.get("/<slug>/login")
def login(slug: str):
    s = _get_session()
    company = _load_company(s, slug)
    if not company:
        abort(404)
    return render_template("company_login.html", company=company)


@bp.post("/<slug>/login")
def login_post(slug: str):
    s = _get_session()
    company = _load_company(s, slug)
    if not company:
        abort(404)
    code = request.form.get("access_code", "").strip()
    rl = limiter()
    key = portal_login_key(request, slug)
    if not code or not company_service.validate_company_access(s, company, code):
        exceeded = False
        try:
            exceeded = rl.too_many_attempts(key, 300, 5)
        except Exception:
            exceeded = True
        if exceeded:
            flash("시도 횟수가 많습니다. 잠시 후 다시 시도하세요.", "error")
        else:
            flash("접속코드가 올바르지 않습니다.", "error")
        return redirect(url_for("portal.login", slug=slug))
    try:
        rl.reset(key)
    except Exception:
        pass
    session["company_id"] = company.id
    session["company_slug"] = company.slug
    return redirect(url_for("portal.home", slug=slug))


@bp.get("/<slug>/logout")
def logout(slug: str):
    s = _get_session()
    company = _load_company(s, slug)
    if company:
        company_service.ensure_token_key(s, company)
        company.token_key = secrets.token_hex(16)
        s.commit()
    session.pop("company_id", None)
    session.pop("company_slug", None)
    return redirect(url_for("portal.login", slug=slug))


@bp.get("/<slug>")
def home(slug: str):
    guard = _company_required(slug)
    if guard:
        return guard
    s = _get_session()
    company = _load_company(s, slug)
    if not company:
        abort(404)
    cur_y, cur_m = current_year_month()
    year = request.args.get("year", type=int) or cur_y
    records = payrolls_dao.list_for_year(s, company.id, year)
    status = {}
    for rec in records:
        state = "done" if has_meaningful_data(rec.rows_json) else "empty"
        status[int(rec.month)] = {
            "state": state,
            "updated_at": rec.updated_at.strftime("%Y-%m-%d %H:%M:%S") if rec.updated_at else "",
        }
    months = []
    for mm in range(1, 13):
        meta = status.get(mm, {})
        months.append(
            {
                "month": mm,
                "state": meta.get("state", "none"),
                "updated_at": meta.get("updated_at", ""),
                "is_current": (year == cur_y and mm == cur_m),
            }
        )
    return render_template(
        "portal_home.html",
        slug=slug,
        year=year,
        months=months,
        company_name=company.name,
    )


@bp.get("/<slug>/payroll/<int:year>/<int:month>")
def edit_payroll(slug: str, year: int, month: int):
    guard = _company_required(slug)
    if guard:
        return guard
    s = _get_session()
    company = _load_company(s, slug)
    if not company:
        abort(404)
    ensure_defaults(s, company)
    cols, numeric_fields, date_fields, bool_fields, extras = build_columns_for_company(s, company)
    record = payrolls_dao.get_by_month(s, company.id, year, month)
    rows = []
    if record:
        try:
            rows = json.loads(record.rows_json or "[]")
        except Exception:
            rows = []
    if not rows:
        rows = [{}]
    group_map, alias_map, exempt_map, include_map = load_field_prefs(s, company)
    return render_template(
        "payroll_edit.html",
        company_name=company.name,
        slug=slug,
        year=year,
        month=month,
        columns=cols,
        extra_fields=[{"name": ef.name, "label": ef.label, "typ": ef.typ} for ef in extras],
        rows=rows,
        group_map=group_map,
        alias_map=alias_map,
        exempt_map=exempt_map,
        include_map=include_map,
        numeric_fields=numeric_fields,
        date_fields=date_fields,
        bool_fields=bool_fields,
        is_closed=bool(record.is_closed) if record else False,
        insurance_config=insurance_settings(),
        is_admin=session.get("is_admin", False),
    )


@bp.post("/<slug>/payroll/<int:year>/<int:month>")
def save_payroll(slug: str, year: int, month: int):
    guard = _company_required(slug)
    if guard:
        return guard
    s = _get_session()
    company = _load_company(s, slug)
    if not company:
        abort(404)
    cols, numeric_fields, date_fields, bool_fields, _ = build_columns_for_company(s, company)
    rows = parse_rows(request.form, cols, numeric_fields, date_fields, bool_fields)
    record = payrolls_dao.get_by_month(s, company.id, year, month)
    payload = json.dumps(rows, ensure_ascii=False)
    if record is None:
        record = MonthlyPayroll(
            company_id=company.id,
            year=year,
            month=month,
            rows_json=payload,
            is_closed=False,
        )
    else:
        record.rows_json = payload
    payrolls_dao.upsert(s, record)
    sync_normalized_rows(s, record, rows)
    s.commit()
    flash("급여표가 저장되었습니다.", "success")
    return redirect(url_for("portal.edit_payroll", slug=slug, year=year, month=month))


@bp.post("/<slug>/payroll/<int:year>/<int:month>/close")
def close_payroll(slug: str, year: int, month: int):
    guard = _company_required(slug)
    if guard:
        return guard
    if not session.get("is_admin"):
        abort(403)
    s = _get_session()
    company = _load_company(s, slug)
    record = payrolls_dao.get_by_month(s, company.id, year, month)
    if not record:
        flash("먼저 저장하세요.", "error")
        return redirect(url_for("portal.edit_payroll", slug=slug, year=year, month=month))
    record.is_closed = True
    try:
        rows = json.loads(record.rows_json or "[]")
    except Exception:
        rows = []
    sync_normalized_rows(s, record, rows)
    s.commit()
    flash("급여표를 마감했습니다.", "success")
    return redirect(url_for("portal.edit_payroll", slug=slug, year=year, month=month))


@bp.post("/<slug>/payroll/<int:year>/<int:month>/open")
def reopen_payroll(slug: str, year: int, month: int):
    guard = _company_required(slug)
    if guard:
        return guard
    if not session.get("is_admin"):
        abort(403)
    s = _get_session()
    company = _load_company(s, slug)
    record = payrolls_dao.get_by_month(s, company.id, year, month)
    if not record:
        flash("먼저 저장하세요.", "error")
        return redirect(url_for("portal.edit_payroll", slug=slug, year=year, month=month))
    record.is_closed = False
    try:
        rows = json.loads(record.rows_json or "[]")
    except Exception:
        rows = []
    sync_normalized_rows(s, record, rows)
    s.commit()
    flash("급여표 마감을 해제했습니다.", "success")
    return redirect(url_for("portal.edit_payroll", slug=slug, year=year, month=month))


@bp.get("/<slug>/export/<int:year>/<int:month>")
def export_payroll(slug: str, year: int, month: int):
    guard = _company_required(slug)
    if guard:
        return guard
    s = _get_session()
    company = _load_company(s, slug)
    if not company:
        abort(404)
    record = payrolls_dao.get_by_month(s, company.id, year, month)
    if not record:
        flash("내보낼 데이터가 없습니다. 먼저 저장하세요.", "error")
        return redirect(url_for("portal.edit_payroll", slug=slug, year=year, month=month))
    try:
        rows = json.loads(record.rows_json or "[]")
    except Exception:
        rows = []

    from payroll_shared.exporter import build_salesmap_workbook

    cols, _, _, _, _ = build_columns_for_company(s, company)
    group_map, alias_map, _, _ = load_field_prefs(s, company)
    bio = build_salesmap_workbook(
        company_slug=company.slug,
        year=year,
        month=month,
        rows=rows,
        all_columns=cols,
        group_prefs=group_map,
        alias_prefs=alias_map,
    )
    filename = f"{company.slug}_{year}-{month:02d}_세일즈맵.xlsx"
    return send_file(
        bio,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@bp.post("/<slug>/fields/add")
def add_field(slug: str):
    guard = _company_required(slug)
    if guard:
        return guard
    data = request.get_json(silent=True) or {}
    label = data.get("label", "")
    typ = (data.get("typ") or "number").strip()
    s = _get_session()
    company = _load_company(s, slug)
    if not company:
        abort(404)
    try:
        field = add_extra_field(s, company, label, typ)
        if not field:
            return jsonify({"ok": False, "error": "항목을 추가할 수 없습니다."}), 400
        return jsonify(
            {
                "ok": True,
                "field": {"name": field.name, "label": field.label, "typ": field.typ},
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.get("/<slug>/fields/calc-config")
def get_calc_config(slug: str):
    guard = _company_required(slug)
    if guard:
        return guard
    s = _get_session()
    company = _load_company(s, slug)
    if not company:
        abort(404)
    _, _, _, include = load_field_prefs(s, company)
    return jsonify({"ok": True, "include": include})


@bp.post("/<slug>/fields/calc-config")
def save_calc_config(slug: str):
    guard = _company_required(slug)
    if guard:
        return guard
    data = request.get_json(silent=True) or {}
    inc = data.get("include") or {}
    nhis = inc.get("nhis") if isinstance(inc, dict) else {}
    ei = inc.get("ei") if isinstance(inc, dict) else {}
    if not isinstance(nhis, dict) or not isinstance(ei, dict):
        return jsonify({"ok": False, "error": "잘못된 형식"}), 400
    s = _get_session()
    company = _load_company(s, slug)
    if not company:
        abort(404)
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
    return jsonify({"ok": True})


@bp.get("/<slug>/fields/exempt-config")
def get_exempt_config(slug: str):
    guard = _company_required(slug)
    if guard:
        return guard
    s = _get_session()
    company = _load_company(s, slug)
    if not company:
        abort(404)
    _, _, ex, _ = load_field_prefs(s, company)
    return jsonify({"ok": True, "exempt": ex})


@bp.post("/<slug>/fields/exempt-config")
def save_exempt_config(slug: str):
    guard = _company_required(slug)
    if guard:
        return guard
    data = request.get_json(silent=True) or {}
    raw = data.get("exempt") or data.get("ov") or {}
    if not isinstance(raw, dict):
        return jsonify({"ok": False, "error": "잘못된 형식"}), 400
    s = _get_session()
    company = _load_company(s, slug)
    if not company:
        abort(404)
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
    return jsonify({"ok": True})
