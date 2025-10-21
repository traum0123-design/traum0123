from __future__ import annotations

import io
import json
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from core.exporter import build_salesmap_workbook
from core.models import Company, MonthlyPayroll
from core.services import companies as company_service
from core.services.extra_fields import add_extra_field, ensure_defaults
from core.services.payroll import (
    build_columns_for_company,
    compute_withholding_tax,
    current_year_month,
    has_meaningful_data,
    insurance_settings,
    load_field_prefs,
    parse_rows,
)
from core.services.persistence import sync_normalized_rows
from core.services.auth import authenticate_admin, authenticate_company, extract_token, issue_company_token
from payroll_api.database import get_db
from payroll_portal.services.rate_limit import limiter, portal_login_key

router = APIRouter(prefix="/portal", tags=["portal"])

TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "payroll_portal" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

PORTAL_COOKIE_NAME = "portal_token"
ADMIN_COOKIE_NAME = "admin_token"
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "").strip().lower() in {"1", "true", "yes", "on"}


def _get_portal_token(request: Request) -> Optional[str]:
    cookie_token = request.cookies.get(PORTAL_COOKIE_NAME)
    header_token = request.headers.get("X-API-Token")
    authorization = request.headers.get("Authorization")
    return extract_token(authorization, header_token, None, cookie_token)


def _require_company(request: Request, slug: str, db: Session) -> Optional[Company]:
    token = _get_portal_token(request)
    if not token:
        return None
    return authenticate_company(db, slug, token)


def _is_admin(request: Request) -> bool:
    token = extract_token(
        request.headers.get("Authorization"),
        request.headers.get("X-Admin-Token"),
        None,
        request.cookies.get(ADMIN_COOKIE_NAME),
    )
    if not token:
        return False
    return authenticate_admin(token)


def _base_context(request: Request, company: Optional[Company] = None) -> dict:
    def _url_for(name: str, **params):
        target = name
        if target == "static":
            filename = params.pop("filename", None)
            path_value = params.pop("path", None)
            static_path = filename or path_value or ""
            return request.app.url_path_for("static", path=static_path)
        return request.url_for(target, **params)

    return {
        "request": request,
        "session": {
            "is_admin": _is_admin(request),
            "company_slug": company.slug if company else None,
        },
        "csrf_token": lambda: "",
        "csp_nonce": lambda: "",
        "get_flashed_messages": lambda **_: [],
        "url_for": _url_for,
    }


@router.get("/{slug}/login", response_class=HTMLResponse, name="portal.login")
def login_page(request: Request, slug: str, db: Session = Depends(get_db), error: Optional[str] = None):
    company = company_service.find_company_by_slug(db, slug)
    if not company:
        raise HTTPException(status_code=404, detail="company not found")
    message = error or request.query_params.get("error")
    context = _base_context(request, company=None)
    context.update({
        "company": company,
        "error": message,
    })
    return templates.TemplateResponse("company_login.html", context)


@router.post("/{slug}/login", name="portal.login_post")
def login_action(request: Request, slug: str, db: Session = Depends(get_db), access_code: str = Form(...)):
    company = company_service.find_company_by_slug(db, slug)
    if not company:
        raise HTTPException(status_code=404, detail="company not found")
    rl = limiter()
    key = portal_login_key(request, slug)
    if not access_code or not company_service.validate_company_access(db, company, access_code):
        exceeded = False
        try:
            exceeded = rl.too_many_attempts(key, 300, 5)
        except Exception:
            exceeded = True
        if exceeded:
            return RedirectResponse(url=f"/portal/{slug}/login?error=too_many_attempts", status_code=303)
        return RedirectResponse(url=f"/portal/{slug}/login?error=invalid_code", status_code=303)
    try:
        rl.reset(key)
    except Exception:
        pass
    token = issue_company_token(db, company)
    response = RedirectResponse(url=f"/portal/{slug}", status_code=303)
    response.set_cookie(
        key=PORTAL_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
    )
    return response


@router.get("/{slug}/logout", name="portal.logout")
def logout(request: Request, slug: str, db: Session = Depends(get_db)):
    company = company_service.find_company_by_slug(db, slug)
    if company:
        company_service.ensure_token_key(db, company)
    response = RedirectResponse(url=f"/portal/{slug}/login", status_code=303)
    response.delete_cookie(PORTAL_COOKIE_NAME, path="/")
    return response


@router.get("/{slug}", response_class=HTMLResponse, name="portal.home")
def portal_home(request: Request, slug: str, db: Session = Depends(get_db)):
    company = _require_company(request, slug, db)
    if not company:
        return RedirectResponse(url=f"/portal/{slug}/login", status_code=303)
    cur_y, cur_m = current_year_month()
    year = request.query_params.get("year")
    try:
        year = int(year) if year else cur_y
    except Exception:
        year = cur_y
    records = (
        db.query(MonthlyPayroll)
        .filter(MonthlyPayroll.company_id == company.id, MonthlyPayroll.year == year)
        .all()
    )
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
    context = _base_context(request, company)
    context.update(
        {
            "slug": slug,
            "year": year,
            "months": months,
            "company_name": company.name,
        }
    )
    return templates.TemplateResponse("portal_home.html", context)


@router.get("/{slug}/payroll/{year}/{month}", response_class=HTMLResponse, name="portal.edit_payroll")
def edit_payroll(request: Request, slug: str, year: int, month: int, db: Session = Depends(get_db)):
    company = _require_company(request, slug, db)
    if not company:
        return RedirectResponse(url=f"/portal/{slug}/login", status_code=303)
    ensure_defaults(db, company)
    cols, numeric_fields, date_fields, bool_fields, extras = build_columns_for_company(db, company)
    record = (
        db.query(MonthlyPayroll)
        .filter(
            MonthlyPayroll.company_id == company.id,
            MonthlyPayroll.year == year,
            MonthlyPayroll.month == month,
        )
        .first()
    )


@router.post("/{slug}/payroll/{year}/{month}", name="portal.save_payroll")
async def save_payroll(request: Request, slug: str, year: int, month: int, db: Session = Depends(get_db)):
    company = _require_company(request, slug, db)
    if not company:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    cols, numeric_fields, date_fields, bool_fields, _ = build_columns_for_company(db, company)
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        payload = await request.json()
        rows = payload.get("rows") or []
        if not isinstance(rows, list):
            return JSONResponse({"ok": False, "error": "invalid payload"}, status_code=400)
    else:
        form = await request.form()
        rows = parse_rows(form, cols, numeric_fields, date_fields, bool_fields)

    record = (
        db.query(MonthlyPayroll)
        .filter(
            MonthlyPayroll.company_id == company.id,
            MonthlyPayroll.year == year,
            MonthlyPayroll.month == month,
        )
        .first()
    )

    if record and bool(getattr(record, "is_closed", False)):
        return JSONResponse({"ok": False, "error": "month is closed"}, status_code=400)

    payload_json = json.dumps(rows, ensure_ascii=False)
    if record is None:
        record = MonthlyPayroll(
            company_id=company.id,
            year=year,
            month=month,
            rows_json=payload_json,
            is_closed=False,
        )
        db.add(record)
    else:
        record.rows_json = payload_json

    sync_normalized_rows(db, record, rows)
    db.commit()
    return {"ok": True}


@router.post("/{slug}/payroll/{year}/{month}/close", name="portal.close_payroll")
def close_payroll(request: Request, slug: str, year: int, month: int, db: Session = Depends(get_db)):
    if not _is_admin(request):
        return JSONResponse({"ok": False, "error": "admin required"}, status_code=403)
    company = _require_company(request, slug, db)
    if not company:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    record = (
        db.query(MonthlyPayroll)
        .filter(
            MonthlyPayroll.company_id == company.id,
            MonthlyPayroll.year == year,
            MonthlyPayroll.month == month,
        )
        .first()
    )
    if not record:
        return JSONResponse({"ok": False, "error": "not found"}, status_code=400)
    record.is_closed = True
    try:
        rows = json.loads(record.rows_json or "[]")
    except Exception:
        rows = []
    sync_normalized_rows(db, record, rows)
    db.commit()
    return {"ok": True}


@router.post("/{slug}/payroll/{year}/{month}/open", name="portal.reopen_payroll")
def reopen_payroll(request: Request, slug: str, year: int, month: int, db: Session = Depends(get_db)):
    if not _is_admin(request):
        return JSONResponse({"ok": False, "error": "admin required"}, status_code=403)
    company = _require_company(request, slug, db)
    if not company:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    record = (
        db.query(MonthlyPayroll)
        .filter(
            MonthlyPayroll.company_id == company.id,
            MonthlyPayroll.year == year,
            MonthlyPayroll.month == month,
        )
        .first()
    )
    if not record:
        return JSONResponse({"ok": False, "error": "not found"}, status_code=400)
    record.is_closed = False
    try:
        rows = json.loads(record.rows_json or "[]")
    except Exception:
        rows = []
    sync_normalized_rows(db, record, rows)
    db.commit()
    return {"ok": True}


@router.get("/{slug}/export/{year}/{month}", name="portal.export_payroll")
def export_payroll(slug: str, year: int, month: int, request: Request, db: Session = Depends(get_db)):
    company = _require_company(request, slug, db)
    if not company:
        return RedirectResponse(url=f"/portal/{slug}/login", status_code=303)
    record = (
        db.query(MonthlyPayroll)
        .filter(
            MonthlyPayroll.company_id == company.id,
            MonthlyPayroll.year == year,
            MonthlyPayroll.month == month,
        )
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="payroll not found")
    try:
        rows = json.loads(record.rows_json or "[]")
    except Exception:
        rows = []
    cols, _, _, _, extras = build_columns_for_company(db, company)
    all_cols = cols + [(ef.name, ef.label, ef.typ) for ef in extras]
    group_map, alias_map, _, _ = load_field_prefs(db, company)
    workbook = build_salesmap_workbook(
        company_slug=company.slug,
        year=year,
        month=month,
        rows=rows,
        all_columns=all_cols,
        group_prefs=group_map,
        alias_prefs=alias_map,
    )
    filename = f"{company.slug}_{year:04d}_{month:02d}_salesmap.xlsx"
    headers = {
        "Content-Disposition": f"attachment; filename=\"{filename}\"",
    }
    return StreamingResponse(workbook, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers=headers)
    rows = []
    if record:
        try:
            rows = json.loads(record.rows_json or "[]")
        except Exception:
            rows = []
    if not rows:
        rows = [{}]
    group_map, alias_map, exempt_map, include_map = load_field_prefs(db, company)
    context = _base_context(request, company)
    context.update(
        {
            "company_name": company.name,
            "slug": slug,
            "year": year,
            "month": month,
            "columns": cols,
            "extra_fields": [{"name": ef.name, "label": ef.label, "typ": ef.typ} for ef in extras],
            "rows": rows,
            "group_map": group_map,
            "alias_map": alias_map,
            "exempt_map": exempt_map,
            "include_map": include_map,
            "numeric_fields": numeric_fields,
            "date_fields": date_fields,
            "bool_fields": bool_fields,
            "is_closed": bool(record.is_closed) if record else False,
            "insurance_config": insurance_settings(),
        }
    )
    return templates.TemplateResponse("payroll_edit.html", context)
