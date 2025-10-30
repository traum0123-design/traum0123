from __future__ import annotations

import io
import json
import os
import secrets
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from core.exporter import build_salesmap_workbook
from core.models import Company, MonthlyPayroll
from core.services import companies as company_service
from core.services.auth import (
    authenticate_admin,
    authenticate_company,
    extract_token,
    issue_company_token,
)
from core.services.extra_fields import add_extra_field, ensure_defaults
from core.settings import get_settings
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
from payroll_api.database import get_db
from payroll_portal.services.rate_limit import limiter, portal_login_key
from payroll_portal.utils.assets import resolve_static, clear_manifest_cache

router = APIRouter(prefix="/portal", tags=["portal"])

TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "payroll_portal" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

PORTAL_COOKIE_NAME = "portal_token"
ADMIN_COOKIE_NAME = "admin_token"
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "").strip().lower() in {"1", "true", "yes", "on"}

CSRF_COOKIE_NAME = "portal_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_MAX_AGE = 60 * 60  # 1 hour


def _ensure_csrf_token(request: Request) -> str:
    # Reuse existing cookie value to avoid rotation across tabs
    existing = request.cookies.get(CSRF_COOKIE_NAME)
    if existing:
        request.state.csrf_token = existing
        return existing
    token = getattr(request.state, "csrf_token", None)
    if not token:
        token = secrets.token_urlsafe(32)
        request.state.csrf_token = token
    return token


def _ensure_csp_nonce(request: Request) -> str:
    nonce = getattr(request.state, "csp_nonce", None)
    if not nonce:
        nonce = secrets.token_urlsafe(16)
        request.state.csp_nonce = nonce
    return nonce


def _apply_template_security(request: Request, response):
    csrf_token = _ensure_csrf_token(request)
    nonce = _ensure_csp_nonce(request)
    # Keep cookie stable and not accessible to JS
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=(request.cookies.get(CSRF_COOKIE_NAME) or csrf_token),
        max_age=CSRF_MAX_AGE,
        secure=COOKIE_SECURE,
        samesite="Lax",
        httponly=True,
        path="/",
    )
    csp_value = response.headers.get("Content-Security-Policy")
    policy = f"script-src 'self' 'nonce-{nonce}'; object-src 'none'; base-uri 'self'"
    if csp_value:
        response.headers["Content-Security-Policy"] = csp_value
    else:
        response.headers["Content-Security-Policy"] = policy
    return response


def _verify_csrf(request: Request, token: str | None = None) -> None:
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME) or ""
    header_token = request.headers.get(CSRF_HEADER_NAME) or ""
    body_token = (token or "").strip()
    if not cookie_token:
        raise HTTPException(status_code=403, detail="missing csrf cookie")

    # Same-origin check: prefer Origin, fall back to Referer when present
    origin = (request.headers.get("origin") or "").strip()
    if origin:
        expected = f"{request.url.scheme}://{request.url.netloc}"
        if origin != expected:
            raise HTTPException(status_code=403, detail="invalid origin")
    else:
        referer = (request.headers.get("referer") or "").strip()
        if referer:
            ref = urlparse(referer)
            if ref.scheme != request.url.scheme or ref.netloc != request.url.netloc:
                raise HTTPException(status_code=403, detail="invalid referer")

    def _matches(candidate: str) -> bool:
        return bool(candidate) and secrets.compare_digest(candidate, cookie_token)

    if _matches(body_token):
        return
    if _matches(header_token):
        return
    raise HTTPException(status_code=403, detail="invalid csrf token")


def _get_portal_token(request: Request) -> str | None:
    cookie_token = request.cookies.get(PORTAL_COOKIE_NAME)
    header_token = request.headers.get("X-API-Token")
    authorization = request.headers.get("Authorization")
    return extract_token(authorization, header_token, None, cookie_token)


def _require_company(request: Request, slug: str, db: Session) -> Company | None:
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


def _base_context(request: Request, company: Company | None = None) -> dict:
    def _url_for(name: str, **params):
        target = name
        if target == "static":
            filename = params.pop("filename", None)
            path_value = params.pop("path", None)
            static_path = filename or path_value or ""
            try:
                # In dev, auto-reload manifest so newly built assets are picked up without restart
                if (getattr(get_settings(), 'app_version', 'dev') or 'dev') == 'dev':
                    clear_manifest_cache()
            except Exception:
                pass
            mapped = resolve_static(static_path)
            return request.app.url_path_for("static", path=mapped)
        return request.url_for(target, **params)

    return {
        "request": request,
        "session": {
            "is_admin": _is_admin(request),
            "company_slug": company.slug if company else None,
        },
        "csrf_token": lambda: _ensure_csrf_token(request),
        "csp_nonce": lambda: _ensure_csp_nonce(request),
        "app_version": getattr(get_settings(), "app_version", "dev"),
        "get_flashed_messages": lambda **_: [],
        "url_for": _url_for,
    }


@router.get("/{slug}/login", response_class=HTMLResponse, name="portal.login")
def login_page(request: Request, slug: str, db: Session = Depends(get_db), error: str | None = None):
    company = company_service.find_company_by_slug(db, slug)
    if not company:
        raise HTTPException(status_code=404, detail="company not found")
    message = error or request.query_params.get("error")
    context = _base_context(request, company=None)
    context.update({
        "company": company,
        "error": message,
    })
    response = templates.TemplateResponse("company_login.html", context)
    return _apply_template_security(request, response)


@router.post("/{slug}/login", name="portal.login_post")
def login_action(request: Request, slug: str, db: Session = Depends(get_db), access_code: str = Form(...), csrf_token: str | None = Form(None)):
    _verify_csrf(request, csrf_token)
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
    year_q = request.query_params.get("year")
    try:
        year_int = int(year_q) if year_q else cur_y
    except Exception:
        year_int = cur_y
    records = (
        db.query(MonthlyPayroll)
        .filter(MonthlyPayroll.company_id == company.id, MonthlyPayroll.year == year_int)
        .all()
    )
    status = {}
    for rec in records:
        state = "closed" if bool(getattr(rec, "is_closed", False)) else ("saved" if has_meaningful_data(rec.rows_json) else "none")
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
                "is_current": (year_int == cur_y and mm == cur_m),
            }
        )
    context = _base_context(request, company)
    context.update(
        {
            "slug": slug,
            "year": year_int,
            "months": months,
            "company_name": company.name,
        }
    )
    response = templates.TemplateResponse("portal_home.html", context)
    return _apply_template_security(request, response)


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
    rows = []
    if record:
        try:
            rows = json.loads(record.rows_json or "[]")
        except Exception:
            rows = []
    if not rows:
        rows = [{}]
    # Auto-prefill only when there is no record at all (first visit for the month)
    auto_prefill = record is None
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
            "portal_home_url": str(request.url_for("portal.home", slug=slug)),
            "save_url": str(request.url_for("portal.save_payroll", slug=slug, year=year, month=month)),
            "is_admin": _is_admin(request),
            "auto_prefill": auto_prefill,
        }
    )
    response = templates.TemplateResponse("payroll_edit.html", context)
    return _apply_template_security(request, response)


@router.post("/{slug}/payroll/{year}/{month}", name="portal.save_payroll")
async def save_payroll(request: Request, slug: str, year: int, month: int, db: Session = Depends(get_db)):
    company = _require_company(request, slug, db)
    if not company:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    cols, numeric_fields, date_fields, bool_fields, _ = build_columns_for_company(db, company)
    content_type = (request.headers.get("content-type", "") or "").lower()
    if "application/json" in content_type:
        # JSON payloads must send X-CSRF-Token header
        _verify_csrf(request)
        payload = await request.json()
        rows = payload.get("rows") or []
        if not isinstance(rows, list):
            return JSONResponse({"ok": False, "error": "invalid payload"}, status_code=400)
    else:
        form = await request.form()
        _verify_csrf(request, form.get("csrf_token"))
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
        db.flush()
    else:
        record.rows_json = payload_json

    sync_normalized_rows(db, record, rows)
    db.commit()
    return {"ok": True}


@router.post("/{slug}/payroll/{year}/{month}/close", name="portal.close_payroll")
def close_payroll(request: Request, slug: str, year: int, month: int, db: Session = Depends(get_db), csrf_token: str | None = Form(None)):
    _verify_csrf(request, csrf_token)
    if not _is_admin(request):
        return JSONResponse({"ok": False, "error": "admin required"}, status_code=403)
    # As admin, allow without requiring portal token
    company = company_service.find_company_by_slug(db, slug) or _require_company(request, slug, db)
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
def reopen_payroll(request: Request, slug: str, year: int, month: int, db: Session = Depends(get_db), csrf_token: str | None = Form(None)):
    _verify_csrf(request, csrf_token)
    if not _is_admin(request):
        return JSONResponse({"ok": False, "error": "admin required"}, status_code=403)
    # As admin, allow without requiring portal token
    company = company_service.find_company_by_slug(db, slug) or _require_company(request, slug, db)
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
    # Deprecate portal export path in favor of API path, preserve auth via 307
    resp = RedirectResponse(url=f"/api/portal/{slug}/export/{year}/{month}", status_code=307)
    resp.headers["Deprecation"] = "true"
    resp.headers["Link"] = f"</api/portal/{slug}/export/{year}/{month}>; rel=\"successor-version\""
    return resp
