from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, FastAPI, Cookie, Depends, Query, HTTPException, Request, UploadFile, File, Form
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from .database import engine, get_db
from core.models import Base, Company, MonthlyPayroll, WithholdingCell, ExtraField, FieldPref
import os
import secrets
import logging
from urllib.parse import quote
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Header
from starlette.exceptions import HTTPException as StarletteHTTPException
from werkzeug.security import generate_password_hash
from core.fields import cleanup_duplicate_extra_fields
from core.rate_limit import get_admin_rate_limiter
from core.settings import get_settings
from core.alembic_utils import ensure_up_to_date
from core.services import companies as company_service
from core.services.auth import (
    authenticate_admin,
    authenticate_company,
    extract_token,
    issue_admin_token,
    issue_company_token,
)
from core.services.payroll import (
    compute_deductions as compute_deductions_service,
    compute_withholding_tax as compute_withholding_tax_service,
)
from .schemas import (
    AdminCompaniesResponse,
    AdminCompanyCreateResponse,
    AdminCompanyResetResponse,
    ClientLogPayload,
    CompanySummary,
    FieldAddRequest,
    FieldAddResponse,
    FieldCalcConfigRequest,
    FieldCalcConfigResponse,
    FieldCalcInclude,
    PayrollCalcRequest,
    PayrollCalcResponse,
    FieldExemptConfigRequest,
    FieldExemptConfigResponse,
    FieldExemptEntry,
    FieldGroupConfigRequest,
    FieldGroupConfigResponse,
    FieldInfo,
    FieldDeleteRequest,
    HealthResponse,
    PayrollRowsResponse,
    SimpleOkResponse,
    WithholdingImportResponse,
    WithholdingResponse,
    WithholdingYearsResponse,
)


ADMIN_COOKIE_NAME = "admin_token"
PORTAL_COOKIE_NAME = "portal_token"


load_dotenv()  # .env 자동 로드(개발 편의)

@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if settings.payroll_auto_apply_ddl:
        # Create tables if not exist (for POC). In production use Alembic.
        Base.metadata.create_all(bind=engine)
    else:
        logging.getLogger("payroll_api").info(
            "PAYROLL_AUTO_APPLY_DDL=0: skipping automatic DDL. Ensure Alembic migrations have been applied."
        )
    if settings.enforce_alembic_migrations:
        if settings.payroll_auto_apply_ddl:
            logging.getLogger("payroll_api").warning(
                "PAYROLL_ENFORCE_ALEMBIC=1 while PAYROLL_AUTO_APPLY_DDL=1; skipping migration check."
            )
        else:
            ensure_up_to_date(engine)
    yield


router = APIRouter()


def _format_error_payload(detail: object, code: Optional[str] = None) -> dict:
    if isinstance(detail, dict):
        message = detail.get("error") or detail.get("detail") or str(detail)
        code = code or detail.get("code")
    else:
        message = str(detail or "")
    payload = {"ok": False, "error": message or "error"}
    if code:
        payload["code"] = str(code)
    return payload


def register_exception_handlers(target) -> None:
    async def http_exception_handler(request, exc: StarletteHTTPException):
        payload = _format_error_payload(exc.detail)
        return JSONResponse(status_code=exc.status_code, content=payload)

    async def validation_exception_handler(request, exc: RequestValidationError):
        payload = {
            "ok": False,
            "error": "validation_error",
            "code": "validation_error",
            "details": exc.errors(),
        }
        return JSONResponse(status_code=422, content=payload)

    target.add_exception_handler(StarletteHTTPException, http_exception_handler)
    target.add_exception_handler(RequestValidationError, validation_exception_handler)


# CORS for dev/proxy scenarios
@router.get("/healthz", response_model=HealthResponse)
def healthz(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"ok": True, "status": "healthy"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/livez', response_model=SimpleOkResponse)
def livez():
    return SimpleOkResponse()

@router.get('/readyz', response_model=HealthResponse)
def readyz(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def get_company_by_slug(db: Session, slug: str) -> Optional[Company]:
    return db.query(Company).filter(Company.slug == slug).first()


@router.get("/portal/{slug}/api/withholding", response_model=WithholdingResponse)
@router.get("/api/portal/{slug}/withholding", response_model=WithholdingResponse)
def api_withholding(
    slug: str,
    year: int = Query(..., description="연도"),
    dep: int = Query(..., description="부양가족수"),
    wage: int = Query(..., description="월보수(과세표준)"),
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
    x_api_token: Optional[str] = Header(None),
    token: Optional[str] = None,
    portal_cookie: Optional[str] = Cookie(None, alias=PORTAL_COOKIE_NAME),
):
    require_company(slug, db, authorization, x_api_token, token, portal_cookie)
    tax = compute_withholding_tax_service(db, year, dep, wage)
    return {
        "ok": True,
        "year": year,
        "dep": dep,
        "wage": wage,
        "tax": int(tax),
        "local_tax": int(round((tax or 0) * 0.1)),
    }


# ------------------------------
# Client log collector
# ------------------------------

logger = logging.getLogger("payroll_api.client_log")


@router.post('/client-log', response_model=SimpleOkResponse)
async def client_log(
    request: Request,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
    x_admin_token: Optional[str] = Header(None),
    x_api_token: Optional[str] = Header(None),
    token: Optional[str] = None,
    admin_cookie: Optional[str] = Cookie(None, alias=ADMIN_COOKIE_NAME),
    portal_cookie: Optional[str] = Cookie(None, alias=PORTAL_COOKIE_NAME),
    payload: Optional[ClientLogPayload] = Body(default=None),
):
    # Accept either admin token or company token (with revocation check)
    admin_tok = extract_token(authorization, x_admin_token, None, admin_cookie)
    who: Optional[str] = None
    if admin_tok and authenticate_admin(admin_tok):
        who = 'admin'
    else:
        company_tok = extract_token(authorization, x_api_token, token, portal_cookie)
        if company_tok:
            company = authenticate_company(db, None, company_tok)
            if company:
                who = f"company:{company.slug}"
    if not who:
        raise HTTPException(status_code=403, detail="forbidden")
    # Read payload
    data = payload.dict() if payload else {}
    def _clip(v, n=2000):
        try:
            s = str(v or '')
            return s if len(s) <= n else s[:n]
        except Exception:
            return ''
    level = (data.get('level') or 'error').lower()
    if level not in {'debug', 'info', 'warning', 'error', 'critical'}:
        level = 'error'
    max_stack = int(os.environ.get("CLIENT_LOG_STACK_MAX", "4000") or 4000)
    max_msg = int(os.environ.get("CLIENT_LOG_MESSAGE_MAX", "2000") or 2000)
    max_url = int(os.environ.get("CLIENT_LOG_URL_MAX", "512") or 512)
    max_ua = int(os.environ.get("CLIENT_LOG_UA_MAX", "512") or 512)
    out = {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "who": who,
        "lvl": level,
        "msg": _clip(data.get('message'), max_msg),
        "url": _clip(data.get('url'), max_url),
        "ua": _clip(data.get('ua'), max_ua),
        "line": data.get('line') or '',
        "col": data.get('col') or '',
        "stack": _clip(data.get('stack'), max_stack),
        "kind": data.get('kind') or 'onerror',
    }
    try:
        ip = getattr(request.client, 'host', None)
        if not ip:
            forwarded = request.headers.get('x-forwarded-for', '')
            ip = forwarded.split(',')[0].strip() if forwarded else 'unknown'
    except Exception:
        ip = 'unknown'
    max_attempts = int(os.environ.get("CLIENT_LOG_RL_MAX", "120") or 120)
    window_sec = int(os.environ.get("CLIENT_LOG_RL_WINDOW", "60") or 60)
    limiter = get_admin_rate_limiter()
    key = f"clientlog:{who}:{ip}"
    try:
        if limiter.too_many_attempts(key, window_sec, max_attempts):
            raise HTTPException(status_code=429, detail="too_many_client_logs")
    except HTTPException:
        raise
    except Exception:
        pass
    try:
        logger.info("client_log", extra={"client_log": out})
    except Exception:
        try:
            logger.info("client_log %s", json.dumps(out, ensure_ascii=False))
        except Exception:
            pass
    return SimpleOkResponse()


# ------------------------------
# Admin: Withholding table
# ------------------------------

@router.get("/admin/tax/withholding/sample", response_model=WithholdingResponse)
def admin_withholding_sample(
    year: int = Query(...),
    dep: int = Query(...),
    wage: int = Query(...),
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
    x_admin_token: Optional[str] = Header(None),
    admin_cookie: Optional[str] = Cookie(None, alias=ADMIN_COOKIE_NAME),
):
    require_admin(authorization, x_admin_token, None, admin_cookie)
    tax = compute_withholding_tax_service(db, year, dep, wage)
    return {"ok": True, "year": year, "dep": dep, "wage": wage, "tax": int(tax), "local_tax": int(round((tax or 0) * 0.1))}


@router.post("/admin/tax/withholding/import", response_model=WithholdingImportResponse)
async def admin_withholding_import(
    year: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
    x_admin_token: Optional[str] = Header(None),
    admin_cookie: Optional[str] = Cookie(None, alias=ADMIN_COOKIE_NAME),
):
    require_admin(authorization, x_admin_token, None, admin_cookie)
    from openpyxl import load_workbook
    try:
        content = await file.read()
        import io
        wb = load_workbook(io.BytesIO(content), data_only=True)
        ws = wb.active
        header_row_idx = None
        dep_cols = {}
        for r in range(1, 15):
            row_vals = [ws.cell(row=r, column=c).value for c in range(1, ws.max_column+1)]
            tmp = {}
            for c, v in enumerate(row_vals[1:], start=2):
                try:
                    iv = int(str(v).strip().replace(',', ''))
                    tmp[c] = iv
                except Exception:
                    pass
            if len(tmp) >= 2:
                header_row_idx = r
                dep_cols = tmp
                break
        if not header_row_idx:
            raise ValueError("의존가족수 헤더를 찾을 수 없습니다.")
        data: list[dict[str, int]] = []
        for r in range(header_row_idx+1, ws.max_row+1):
            v = ws.cell(row=r, column=1).value
            if v is None:
                continue
            try:
                wage_v = int(float(str(v).replace(',', '').strip()))
            except Exception:
                if data:
                    break
                else:
                    continue
            for c, dep_v in dep_cols.items():
                tv = ws.cell(row=r, column=c).value
                try:
                    tax = int(float(str(tv).replace(',', '').strip())) if tv not in (None, "") else 0
                except Exception:
                    tax = 0
                data.append({"year": year, "dependents": dep_v, "wage": wage_v, "tax": tax})
        if not data:
            raise ValueError("유효한 데이터가 없습니다.")
        inserted = 0
        with db.begin():
            db.query(WithholdingCell).filter(WithholdingCell.year == year).delete(synchronize_session=False)
            db.bulk_insert_mappings(WithholdingCell, data)  # type: ignore[arg-type]
            inserted = len(data)
        return {"ok": True, "year": year, "count": inserted}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/admin/api/withholding/years", response_model=WithholdingYearsResponse)
def admin_withholding_years(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
    x_admin_token: Optional[str] = Header(None),
    admin_cookie: Optional[str] = Cookie(None, alias=ADMIN_COOKIE_NAME),
):
    require_admin(authorization, x_admin_token, None, admin_cookie)
    try:
        rows = db.execute(text("SELECT year, COUNT(1) FROM withholding_cells GROUP BY year ORDER BY year DESC")).all()
        return {"ok": True, "years": [(int(y), int(c)) for (y, c) in rows]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ------------------------------
# Admin: Company management
# ------------------------------

@router.post("/admin/company/new", response_model=AdminCompanyCreateResponse)
async def admin_company_new(
    name: str = Form(...),
    slug: str = Form(...),
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
    x_admin_token: Optional[str] = Header(None),
    admin_cookie: Optional[str] = Cookie(None, alias=ADMIN_COOKIE_NAME),
):
    require_admin(authorization, x_admin_token, None, admin_cookie)
    name = (name or '').strip()
    slug = (slug or '').strip().lower()
    if not name or not slug:
        raise HTTPException(status_code=400, detail="name/slug required")
    if db.query(Company).filter(Company.slug == slug).first():
        raise HTTPException(status_code=400, detail="slug in use")
    access_code = secrets.token_hex(4)
    access_hash = generate_password_hash(access_code)
    comp = Company(name=name, slug=slug, access_hash=access_hash)
    db.add(comp)
    db.commit()
    company_payload = CompanySummary(
        id=comp.id,
        name=comp.name,
        slug=comp.slug,
        created_at=comp.created_at.isoformat() if comp.created_at else None,
    )
    return {"ok": True, "company": company_payload, "access_code": access_code}


@router.post("/admin/company/{company_id}/reset-code", response_model=AdminCompanyResetResponse)
def admin_company_reset_code(
    company_id: int,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
    x_admin_token: Optional[str] = Header(None),
    admin_cookie: Optional[str] = Cookie(None, alias=ADMIN_COOKIE_NAME),
):
    require_admin(authorization, x_admin_token, None, admin_cookie)
    comp = db.get(Company, company_id)
    if not comp:
        raise HTTPException(status_code=404, detail="not found")
    access_code = secrets.token_hex(4)
    comp.access_hash = generate_password_hash(access_code)
    db.commit()
    return {"ok": True, "company_id": comp.id, "access_code": access_code}


@router.get("/admin/companies", response_model=AdminCompaniesResponse)
def admin_companies(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
    x_admin_token: Optional[str] = Header(None),
    admin_cookie: Optional[str] = Cookie(None, alias=ADMIN_COOKIE_NAME),
):
    require_admin(authorization, x_admin_token, None, admin_cookie)
    rows = db.query(Company).order_by(Company.created_at.desc()).all()
    companies = [
        CompanySummary(
            id=c.id,
            name=c.name,
            slug=c.slug,
            created_at=c.created_at.isoformat() if c.created_at else None,
        )
        for c in rows
    ]
    return {"ok": True, "companies": companies}


@router.get("/admin/company/{company_id}/impersonate-token")
def admin_impersonate_token(
    company_id: int,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
    x_admin_token: Optional[str] = Header(None),
    admin_cookie: Optional[str] = Cookie(None, alias=ADMIN_COOKIE_NAME),
):
    # Returns a portal token for the given company
    require_admin(authorization, x_admin_token, None, admin_cookie)
    comp = db.get(Company, company_id)
    if not comp:
        raise HTTPException(status_code=404, detail="not found")
    tok = issue_company_token(db, comp, is_admin=True)
    return {"ok": True, "slug": comp.slug, "token": tok}


# ------------------------------
# Admin: Login (FastAPI-only usage)
# ------------------------------


@router.post("/admin/login")
def admin_login_api(request: Request, password: str = Form(...)):
    if not company_service.verify_admin_password(password):
        # Rate limit by client IP
        try:
            ip = getattr(request.client, 'host', None) or request.headers.get('x-forwarded-for', '').split(',')[0].strip() or 'unknown'
        except Exception:
            ip = 'unknown'
        try:
            max_attempts = int(os.environ.get("ADMIN_LOGIN_RL_MAX", "10") or 10)
            window_sec = int(os.environ.get("ADMIN_LOGIN_RL_WINDOW", "600") or 600)
        except Exception:
            max_attempts = 10
            window_sec = 600
        limiter = get_admin_rate_limiter()
        key = f"fastapi:{ip}"
        try:
            exceeded = limiter.too_many_attempts(key, window_sec, max_attempts)
        except Exception:
            exceeded = True
        if exceeded:
            raise HTTPException(status_code=429, detail="too many attempts")
        raise HTTPException(status_code=403, detail="invalid password")
    try:
        ttl = int(os.environ.get("ADMIN_TOKEN_TTL", "7200") or 7200)
    except Exception:
        ttl = 7200
    try:
        ip = getattr(request.client, 'host', None) or request.headers.get('x-forwarded-for', '').split(',')[0].strip() or 'unknown'
        get_admin_rate_limiter().reset(f"fastapi:{ip}")
    except Exception:
        pass
    tok = issue_admin_token(ttl_seconds=ttl)
    response = JSONResponse({"ok": True, "token": tok, "ttl": ttl})
    response.set_cookie(
        key=ADMIN_COOKIE_NAME,
        value=tok,
        httponly=True,
        samesite="lax",
        secure=bool(os.environ.get("COOKIE_SECURE", "").lower() in {"1", "true", "yes", "on"}),
        max_age=ttl,
    )
    return response


@router.get("/portal/{slug}/payroll/{year}/{month}", response_model=PayrollRowsResponse)
@router.get("/api/portal/{slug}/payroll/{year}/{month}", response_model=PayrollRowsResponse)
def api_get_payroll(
    slug: str,
    year: int,
    month: int,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
    x_api_token: Optional[str] = Header(None),
    token: Optional[str] = None,
    portal_cookie: Optional[str] = Cookie(None, alias=PORTAL_COOKIE_NAME),
):
    company = require_company(slug, db, authorization, x_api_token, token, portal_cookie)
    rec = (
        db.query(MonthlyPayroll)
        .filter(
            MonthlyPayroll.company_id == company.id,
            MonthlyPayroll.year == year,
            MonthlyPayroll.month == month,
        )
        .first()
    )
    if not rec:
        return {"ok": True, "rows": []}
    try:
        rows = json.loads(rec.rows_json or "[]")
    except Exception:
        rows = []
    return {"ok": True, "rows": rows}


@router.post("/portal/{slug}/calc/deductions", response_model=PayrollCalcResponse)
@router.post("/api/portal/{slug}/calc/deductions", response_model=PayrollCalcResponse)
def api_calc_deductions(
    slug: str,
    payload: PayrollCalcRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
    x_api_token: Optional[str] = Header(None),
    token: Optional[str] = None,
    portal_cookie: Optional[str] = Cookie(None, alias=PORTAL_COOKIE_NAME),
):
    company = require_company(slug, db, authorization, x_api_token, token, portal_cookie)
    row = payload.row or {}
    try:
        year = int(payload.year)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid year")
    amounts, metadata = compute_deductions_service(db, company, row, year)
    return PayrollCalcResponse(amounts=amounts, metadata=metadata)


def _looks_like_int(s: str) -> bool:
    try:
        t = s.strip().replace(",", "")
        if t.startswith("-"):
            t = t[1:]
        return t.isdigit()
    except Exception:
        return False


def _parse_value(v: str):
    if v is None:
        return None
    s = str(v).strip()
    if s == "":
        return ""
    low = s.lower()
    if low in {"on", "true", "t", "yes", "y", "1"}:
        return True
    if _looks_like_int(s):
        try:
            return int(s.replace(",", ""))
        except Exception:
            pass
    # leave as string
    return s


def _parse_rows_from_form(form: dict) -> list[dict]:
    bucket: dict[int, dict] = {}
    for k, v in form.items():
        if not k.startswith("rows["):
            continue
        try:
            left, right = k.split("][", 1)
            idx = int(left[5:])
            field = right[:-1]
        except Exception:
            continue
        bucket.setdefault(idx, {})[field] = _parse_value(v)
    rows: list[dict] = []
    for idx in sorted(bucket.keys()):
        row = bucket[idx]
        # skip fully empty rows
        if not any(str(val or "").strip() for val in row.values()):
            continue
        rows.append(row)
    return rows


@router.post("/portal/{slug}/payroll/{year}/{month}", response_model=SimpleOkResponse)
async def api_save_payroll(
    slug: str,
    year: int,
    month: int,
    request: Request,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
    x_api_token: Optional[str] = Header(None),
    portal_cookie: Optional[str] = Cookie(None, alias=PORTAL_COOKIE_NAME),
):
    company = require_company(slug, db, authorization, x_api_token, None, portal_cookie)
    # accept x-www-form-urlencoded or JSON
    rows: list[dict]
    ct = request.headers.get("content-type", "")
    if "application/json" in ct:
        payload = await request.json()
        rows = payload.get("rows") or []
        if not isinstance(rows, list):
            raise HTTPException(status_code=400, detail="invalid payload")
    else:
        form = await request.form()
        rows = _parse_rows_from_form(dict(form))

    rec = (
        db.query(MonthlyPayroll)
        .filter(
            MonthlyPayroll.company_id == company.id,
            MonthlyPayroll.year == year,
            MonthlyPayroll.month == month,
        )
        .first()
    )
    if rec and bool(getattr(rec, "is_closed", False)):
        raise HTTPException(status_code=400, detail="month is closed")
    data = json.dumps(rows, ensure_ascii=False)
    if not rec:
        rec = MonthlyPayroll(company_id=company.id, year=year, month=month, rows_json=data)
        db.add(rec)
    else:
        rec.rows_json = data
    db.commit()
    return SimpleOkResponse()


# ------------------------------
# Fields config (parity with Flask JSON APIs)
# ------------------------------

def _load_include_map(db: Session, company: Company) -> dict[str, dict[str, bool]]:
    rows = db.query(FieldPref).filter(FieldPref.company_id == company.id).all()
    inc: dict[str, dict[str, bool]] = {"nhis": {}, "ei": {}}
    for p in rows:
        if bool(getattr(p, "ins_nhis", False)):
            inc["nhis"][p.field] = True
        if bool(getattr(p, "ins_ei", False)):
            inc["ei"][p.field] = True
    return inc


@router.get("/portal/{slug}/fields/calc-config", response_model=FieldCalcConfigResponse)
@router.get("/api/portal/{slug}/fields/calc-config", response_model=FieldCalcConfigResponse)
def api_get_calc_config(
    slug: str,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
    x_api_token: Optional[str] = Header(None),
    token: Optional[str] = None,
    portal_cookie: Optional[str] = Cookie(None, alias=PORTAL_COOKIE_NAME),
):
    company = require_company(slug, db, authorization, x_api_token, token, portal_cookie)
    include = _load_include_map(db, company)
    return FieldCalcConfigResponse(include=FieldCalcInclude(**include))


@router.post("/portal/{slug}/fields/calc-config", response_model=SimpleOkResponse)
@router.post("/api/portal/{slug}/fields/calc-config", response_model=SimpleOkResponse)
def api_save_calc_config(
    slug: str,
    payload: FieldCalcConfigRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
    x_api_token: Optional[str] = Header(None),
    token: Optional[str] = None,
    portal_cookie: Optional[str] = Cookie(None, alias=PORTAL_COOKIE_NAME),
):
    company = require_company(slug, db, authorization, x_api_token, token, portal_cookie)
    inc = payload.include or {}
    nhis = inc.get("nhis") or {}
    ei = inc.get("ei") or {}
    if not isinstance(nhis, dict) or not isinstance(ei, dict):
        raise HTTPException(status_code=400, detail="invalid payload")
    nhis_keys = {k for k, v in nhis.items() if v}
    ei_keys = {k for k, v in ei.items() if v}
    # Upsert
    for key in nhis_keys | ei_keys:
        pref = db.query(FieldPref).filter(FieldPref.company_id == company.id, FieldPref.field == key).first()
        if not pref:
            pref = FieldPref(company_id=company.id, field=key)
            db.add(pref)
        pref.ins_nhis = key in nhis_keys
        pref.ins_ei = key in ei_keys
    # Reset others
    rows = db.query(FieldPref).filter(FieldPref.company_id == company.id).all()
    for p in rows:
        if p.field not in nhis_keys:
            p.ins_nhis = False
        if p.field not in ei_keys:
            p.ins_ei = False
    db.commit()
    return SimpleOkResponse()


def _base_exemptions_from_env() -> dict:
    try:
        raw = os.environ.get("INS_BASE_EXEMPTIONS", "")
        if not raw:
            return {}
        return json.loads(raw) if isinstance(raw, str) else {}
    except Exception:
        return {}


@router.get("/portal/{slug}/fields/exempt-config", response_model=FieldExemptConfigResponse)
@router.get("/api/portal/{slug}/fields/exempt-config", response_model=FieldExemptConfigResponse)
def api_get_exempt_config(
    slug: str,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
    x_api_token: Optional[str] = Header(None),
    token: Optional[str] = None,
    portal_cookie: Optional[str] = Cookie(None, alias=PORTAL_COOKIE_NAME),
):
    company = require_company(slug, db, authorization, x_api_token, token, portal_cookie)
    rows = db.query(FieldPref).filter(FieldPref.company_id == company.id).all()
    ex: dict[str, FieldExemptEntry] = {}
    for p in rows:
        if bool(getattr(p, "exempt_enabled", False)) or int(getattr(p, "exempt_limit", 0) or 0) > 0:
            ex[p.field] = FieldExemptEntry(enabled=bool(p.exempt_enabled), limit=int(p.exempt_limit or 0))
    return FieldExemptConfigResponse(exempt=ex, base=_base_exemptions_from_env())


@router.post("/portal/{slug}/fields/exempt-config", response_model=SimpleOkResponse)
@router.post("/api/portal/{slug}/fields/exempt-config", response_model=SimpleOkResponse)
def api_save_exempt_config(
    slug: str,
    payload: FieldExemptConfigRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
    x_api_token: Optional[str] = Header(None),
    token: Optional[str] = None,
    portal_cookie: Optional[str] = Cookie(None, alias=PORTAL_COOKIE_NAME),
):
    company = require_company(slug, db, authorization, x_api_token, token, portal_cookie)
    raw = payload.exempt or {}
    for field, conf in raw.items():
        enabled = bool(conf.enabled)
        limit = int(conf.limit or 0)
        pref = db.query(FieldPref).filter(FieldPref.company_id == company.id, FieldPref.field == field).first()
        if not pref:
            pref = FieldPref(company_id=company.id, field=field)
            db.add(pref)
        pref.exempt_enabled = enabled
        pref.exempt_limit = limit
    db.commit()
    return SimpleOkResponse()


@router.post("/portal/{slug}/fields/add", response_model=FieldAddResponse)
@router.post("/api/portal/{slug}/fields/add", response_model=FieldAddResponse)
def api_add_field(
    slug: str,
    payload: FieldAddRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
    x_api_token: Optional[str] = Header(None),
    token: Optional[str] = None,
    portal_cookie: Optional[str] = Cookie(None, alias=PORTAL_COOKIE_NAME),
):
    company = require_company(slug, db, authorization, x_api_token, token, portal_cookie)
    label = payload.label.strip()
    typ = payload.typ.strip()
    if not label:
        raise HTTPException(status_code=400, detail="label required")
    # Prevent dup by label per company (best-effort)
    existing = db.query(ExtraField).filter(ExtraField.company_id == company.id, ExtraField.label == label).first()
    if existing:
        field_info = FieldInfo(name=existing.name, label=existing.label, typ=existing.typ)
        return FieldAddResponse(field=field_info, existed=True)
    # Generate unique name from label
    base = label
    name = base
    i = 1
    while db.query(ExtraField).filter(ExtraField.company_id == company.id, ExtraField.name == name).first():
        i += 1
        name = f"{base}_{i}"
    ef = ExtraField(company_id=company.id, name=name, label=label, typ=typ)
    db.add(ef)
    db.commit()
    try:
        cleanup_duplicate_extra_fields(db, company)
    except Exception:
        pass
    return FieldAddResponse(field=FieldInfo(name=ef.name, label=ef.label, typ=ef.typ))


@router.post("/portal/{slug}/fields/delete", response_model=SimpleOkResponse)
@router.post("/api/portal/{slug}/fields/delete", response_model=SimpleOkResponse)
def api_delete_field(
    slug: str,
    payload: FieldDeleteRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
    x_api_token: Optional[str] = Header(None),
    token: Optional[str] = None,
    portal_cookie: Optional[str] = Cookie(None, alias=PORTAL_COOKIE_NAME),
):
    company = require_company(slug, db, authorization, x_api_token, token, portal_cookie)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    ef = db.query(ExtraField).filter(ExtraField.company_id == company.id, ExtraField.name == name).first()
    if not ef:
        raise HTTPException(status_code=404, detail="not found")
    db.delete(ef)
    db.commit()
    return SimpleOkResponse()


@router.post("/portal/{slug}/fields/group-config", response_model=FieldGroupConfigResponse)
@router.post("/api/portal/{slug}/fields/group-config", response_model=FieldGroupConfigResponse)
def api_save_group_config(
    slug: str,
    payload: FieldGroupConfigRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
    x_api_token: Optional[str] = Header(None),
    token: Optional[str] = None,
    portal_cookie: Optional[str] = Cookie(None, alias=PORTAL_COOKIE_NAME),
):
    company = require_company(slug, db, authorization, x_api_token, token, portal_cookie)
    group_map = payload.map or {}
    alias_map = payload.alias or {}
    for field, grp in group_map.items():
        grp = (grp or "none").strip()
        pref = db.query(FieldPref).filter(FieldPref.company_id == company.id, FieldPref.field == field).first()
        if not pref:
            pref = FieldPref(company_id=company.id, field=field, group=grp)
            db.add(pref)
        else:
            pref.group = grp
    for field, alias in alias_map.items():
        alias = (alias or "").strip()
        pref = db.query(FieldPref).filter(FieldPref.company_id == company.id, FieldPref.field == field).first()
        if not pref:
            pref = FieldPref(company_id=company.id, field=field, alias=alias)
            db.add(pref)
        else:
            pref.alias = alias
    db.commit()
    try:
        cleanup_duplicate_extra_fields(db, company)
    except Exception:
        pass
    return FieldGroupConfigResponse()


# ------------------------------
# Close / Open month
# ------------------------------

@router.post("/portal/{slug}/payroll/{year}/{month}/close", response_model=SimpleOkResponse)
def api_close_month(
    slug: str,
    year: int,
    month: int,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
    x_api_token: Optional[str] = Header(None),
    portal_cookie: Optional[str] = Cookie(None, alias=PORTAL_COOKIE_NAME),
):
    company = require_company(slug, db, authorization, x_api_token, None, portal_cookie)
    rec = (
        db.query(MonthlyPayroll)
        .filter(
            MonthlyPayroll.company_id == company.id,
            MonthlyPayroll.year == year,
            MonthlyPayroll.month == month,
        )
        .first()
    )
    if not rec:
        rec = MonthlyPayroll(company_id=company.id, year=year, month=month, rows_json="[]", is_closed=True)
        db.add(rec)
    else:
        rec.is_closed = True
    db.commit()
    return SimpleOkResponse()


@router.post("/portal/{slug}/payroll/{year}/{month}/open", response_model=SimpleOkResponse)
def api_open_month(
    slug: str,
    year: int,
    month: int,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
    x_api_token: Optional[str] = Header(None),
    portal_cookie: Optional[str] = Cookie(None, alias=PORTAL_COOKIE_NAME),
):
    company = require_company(slug, db, authorization, x_api_token, None, portal_cookie)
    rec = (
        db.query(MonthlyPayroll)
        .filter(
            MonthlyPayroll.company_id == company.id,
            MonthlyPayroll.year == year,
            MonthlyPayroll.month == month,
        )
        .first()
    )
    if rec:
        rec.is_closed = False
        db.commit()
    return SimpleOkResponse()


# ------------------------------
# Export (basic workbook)
# ------------------------------
@router.get("/portal/{slug}/export/{year}/{month}")
def api_export(
    slug: str,
    year: int,
    month: int,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
    x_api_token: Optional[str] = Header(None),
    token: Optional[str] = None,
    portal_cookie: Optional[str] = Cookie(None, alias=PORTAL_COOKIE_NAME),
):
    company = require_company(slug, db, authorization, x_api_token, token, portal_cookie)
    rec = (
        db.query(MonthlyPayroll)
        .filter(
            MonthlyPayroll.company_id == company.id,
            MonthlyPayroll.year == year,
            MonthlyPayroll.month == month,
        )
        .first()
    )
    if not rec:
        raise HTTPException(status_code=400, detail="no data to export")
    try:
        rows = json.loads(rec.rows_json or "[]")
    except Exception:
        rows = []
    # Build workbook identical to Flask export using shared exporter
    from core.exporter import build_salesmap_workbook
    from core.schema import DEFAULT_COLUMNS
    # Build all_columns = DEFAULT + extras
    extras = db.query(ExtraField).filter(ExtraField.company_id == company.id).order_by(ExtraField.position.asc(), ExtraField.id.asc()).all()
    all_columns = list(DEFAULT_COLUMNS) + [(e.name, e.label, e.typ or 'number') for e in extras]
    # group/alias prefs
    rows_pref = db.query(FieldPref).filter(FieldPref.company_id == company.id).all()
    gp = {}
    ap = {}
    for p in rows_pref:
        if p.group and p.group != "none":
            gp[p.field] = p.group
        if p.alias:
            ap[p.field] = p.alias
    bio = build_salesmap_workbook(
        company_slug=company.slug,
        year=year,
        month=month,
        rows=rows,
        all_columns=all_columns,
        group_prefs=gp,
        alias_prefs=ap,
    )
    filename = f"{company.slug}_{year}-{month:02d}_세일즈맵.xlsx"
    encoded = quote(filename)
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"}
    return StreamingResponse(
        bio,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )
def require_company(
    slug: str,
    db: Session,
    authorization: Optional[str] = None,
    x_api_token: Optional[str] = None,
    token: Optional[str] = None,
    portal_cookie: Optional[str] = None,
) -> Company:
    tok = extract_token(authorization, x_api_token, token, portal_cookie)
    if not tok:
        raise HTTPException(status_code=403, detail="missing token")
    company = authenticate_company(db, slug, tok)
    if not company:
        if not get_company_by_slug(db, slug):
            raise HTTPException(status_code=404, detail="company not found")
        raise HTTPException(status_code=403, detail="invalid token")
    return company


def create_app() -> FastAPI:
    application = FastAPI(title="Payroll API (FastAPI)", lifespan=lifespan)

    origins_env = (os.environ.get("API_CORS_ORIGINS") or "").strip()
    if origins_env:
        origins = [o.strip() for o in origins_env.split(",") if o.strip()]
    else:
        api_base = (os.environ.get("API_BASE_URL") or "").strip()
        if api_base:
            origins = [api_base]
        else:
            origins = [
                "http://localhost:5000",
                "http://127.0.0.1:5000",
                "http://localhost:8000",
                "http://127.0.0.1:8000",
            ]

    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(router)
    register_exception_handlers(application)
    return application


app = create_app()
# Simple helper to expose withholding tax computation for tests and internal callers
def compute_withholding_tax(
    db: Session, *, year: int, dependents: int, wage: int
) -> int:
    return int(compute_withholding_tax_service(db, year, dependents, wage) or 0)
# Lightweight admin guard usable both in FastAPI routes and direct calls
def require_admin(
    authorization: Optional[str] = None,
    x_admin_token: Optional[str] = None,
    query_token: Optional[str] = None,
    admin_cookie: Optional[str] = None,
) -> None:
    tok = extract_token(authorization, x_admin_token, query_token, admin_cookie)
    if not tok or not authenticate_admin(tok):
        raise HTTPException(status_code=403, detail="forbidden")
