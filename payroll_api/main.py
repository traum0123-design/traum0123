from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Depends, Query, HTTPException, Request, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import text

from .database import engine, get_db
from payroll_shared.models import Base, Company, MonthlyPayroll, WithholdingCell, ExtraField, FieldPref
import os
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Header
from payroll_shared.auth import verify_company_token, verify_admin_token
from payroll_shared.fields import cleanup_duplicate_extra_fields
from payroll_shared.rate_limit import get_admin_rate_limiter
from payroll_shared.settings import get_settings
from payroll_shared.alembic_utils import ensure_up_to_date
import secrets
from werkzeug.security import generate_password_hash
from urllib.parse import quote
import logging


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


app = FastAPI(title="Payroll API (FastAPI)", lifespan=lifespan)

# CORS for dev/proxy scenarios
origins_env = (os.environ.get("API_CORS_ORIGINS") or "").strip()
if origins_env:
    _origins = [o.strip() for o in origins_env.split(",") if o.strip()]
else:
    api_base = (os.environ.get("API_BASE_URL") or "").strip()
    if api_base:
        _origins = [api_base]
    else:
        # Safer dev defaults (no wildcard): allow common loopback origins
        _origins = [
            "http://localhost:5000",
            "http://127.0.0.1:5000",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/healthz")
def healthz(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"ok": True, "status": "healthy"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get('/livez')
def livez():
    return {"ok": True}

@app.get('/readyz')
def readyz(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


def get_company_by_slug(db: Session, slug: str) -> Optional[Company]:
    return db.query(Company).filter(Company.slug == slug).first()


def compute_withholding_tax(db: Session, year: int, dependents: int, wage: int) -> int:
    # floor to the largest wage <= given wage
    row = (
        db.query(WithholdingCell)
        .filter(
            WithholdingCell.year == year,
            WithholdingCell.dependents == dependents,
            WithholdingCell.wage <= wage,
        )
        .order_by(WithholdingCell.wage.desc())
        .first()
    )
    return int(row.tax) if row else 0


@app.get("/portal/{slug}/api/withholding")
@app.get("/api/portal/{slug}/withholding")
def api_withholding(
    slug: str,
    year: int = Query(..., description="연도"),
    dep: int = Query(..., description="부양가족수"),
    wage: int = Query(..., description="월보수(과세표준)"),
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
    x_api_token: Optional[str] = Header(None),
    token: Optional[str] = None,
):
    # Auth
    require_company(slug, db, authorization, x_api_token, token)
    tax = compute_withholding_tax(db, year, dep, wage)
    return {"ok": True, "year": year, "dep": dep, "wage": wage, "tax": int(tax), "local_tax": int(round((tax or 0) * 0.1))}

# ------------------------------
# Admin helpers
# ------------------------------

def _extract_admin_token(authorization: Optional[str], x_admin_token: Optional[str], token_qs: Optional[str]) -> Optional[str]:
    if token_qs:
        return token_qs
    if x_admin_token:
        return x_admin_token
    if authorization and authorization.lower().startswith('bearer '):
        return authorization.split(' ', 1)[1].strip()
    return None


def require_admin(authorization: Optional[str] = Header(None), x_admin_token: Optional[str] = Header(None), admin_token: Optional[str] = None):
    tok = _extract_admin_token(authorization, x_admin_token, admin_token)
    if not tok:
        raise HTTPException(status_code=403, detail="missing admin token")
    secret = get_settings().secret_key
    payload = verify_admin_token(secret, tok)
    if not payload:
        raise HTTPException(status_code=403, detail="invalid admin token")
    return True


# ------------------------------
# Client log collector
# ------------------------------

@app.post('/client-log')
async def client_log(request: Request, db: Session = Depends(get_db), authorization: Optional[str] = Header(None), x_admin_token: Optional[str] = Header(None), x_api_token: Optional[str] = Header(None), token: Optional[str] = None):
    # Accept either admin token or company token (with revocation check)
    who = None
    secret = get_settings().secret_key
    # Try admin token first
    a_tok = None
    # Reuse admin extraction logic
    try:
        # This function exists below; re-implement quick extraction here
        if authorization and authorization.lower().startswith('bearer '):
            a_tok = authorization.split(' ', 1)[1].strip()
        if (not a_tok) and x_admin_token:
            a_tok = x_admin_token
    except Exception:
        a_tok = None
    if a_tok:
        if verify_admin_token(secret, a_tok):
            who = 'admin'
    if not who:
        # Company token path
        c_tok = None
        try:
            if authorization and authorization.lower().startswith('bearer '):
                c_tok = authorization.split(' ', 1)[1].strip()
            if (not c_tok) and x_api_token:
                c_tok = x_api_token
            if (not c_tok) and token:
                c_tok = token
        except Exception:
            c_tok = None
        if c_tok:
            payload = verify_company_token(secret, c_tok)
            if payload:
                # Optional revocation check
                try:
                    slug = str(payload.get('slug'))
                    company = get_company_by_slug(db, slug)
                    ckey = (company.token_key or '').strip() if company else ''
                    pkey = str(payload.get('key', '') or '').strip()
                    if ckey and (ckey != pkey):
                        raise HTTPException(status_code=403, detail="token revoked")
                    who = f"company:{company.id}" if company else f"company:{slug}"
                except Exception:
                    who = f"company:{payload.get('cid','?')}"
    if not who:
        raise HTTPException(status_code=403, detail="forbidden")
    # Read payload
    data = await request.json() if request.headers.get('content-type','').startswith('application/json') else {}
    def _clip(v, n=2000):
        try:
            s = str(v or '')
            return s if len(s) <= n else s[:n]
        except Exception:
            return ''
    out = {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "who": who,
        "lvl": data.get('level') or 'error',
        "msg": _clip(data.get('message')),
        "url": _clip(data.get('url'), 512),
        "ua": _clip(data.get('ua'), 512),
        "line": data.get('line') or '',
        "col": data.get('col') or '',
        "stack": _clip(data.get('stack'), 4000),
        "kind": data.get('kind') or 'onerror',
    }
    try:
        print(json.dumps({"client_log": out}, ensure_ascii=False), flush=True)
    except Exception:
        pass
    return {"ok": True}


# ------------------------------
# Admin: Withholding table
# ------------------------------

@app.get("/admin/tax/withholding/sample")
def admin_withholding_sample(year: int = Query(...), dep: int = Query(...), wage: int = Query(...), db: Session = Depends(get_db), authorization: Optional[str] = Header(None), x_admin_token: Optional[str] = Header(None)):
    require_admin(authorization, x_admin_token, None)
    tax = compute_withholding_tax(db, year, dep, wage)
    return {"ok": True, "year": year, "dep": dep, "wage": wage, "tax": int(tax), "local_tax": int(round((tax or 0) * 0.1))}


@app.post("/admin/tax/withholding/import")
async def admin_withholding_import(year: int = Form(...), file: UploadFile = File(...), db: Session = Depends(get_db), authorization: Optional[str] = Header(None), x_admin_token: Optional[str] = Header(None)):
    require_admin(authorization, x_admin_token, None)
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
        data = []
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
                data.append((year, dep_v, wage_v, tax))
        # Replace existing year
        db.query(WithholdingCell).filter(WithholdingCell.year == year).delete()
        for y, dep_v, wage_v, tax in data:
            db.add(WithholdingCell(year=y, dependents=dep_v, wage=wage_v, tax=tax))
        db.commit()
        return {"ok": True, "year": year, "count": len(data)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/admin/api/withholding/years")
def admin_withholding_years(db: Session = Depends(get_db), authorization: Optional[str] = Header(None), x_admin_token: Optional[str] = Header(None)):
    require_admin(authorization, x_admin_token, None)
    try:
        rows = db.execute(text("SELECT year, COUNT(1) FROM withholding_cells GROUP BY year ORDER BY year DESC")).all()
        return {"ok": True, "years": [(int(y), int(c)) for (y, c) in rows]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ------------------------------
# Admin: Company management
# ------------------------------

@app.post("/admin/company/new")
async def admin_company_new(name: str = Form(...), slug: str = Form(...), db: Session = Depends(get_db), authorization: Optional[str] = Header(None), x_admin_token: Optional[str] = Header(None)):
    require_admin(authorization, x_admin_token, None)
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
    return {"ok": True, "company": {"id": comp.id, "name": comp.name, "slug": comp.slug}, "access_code": access_code}


@app.post("/admin/company/{company_id}/reset-code")
def admin_company_reset_code(company_id: int, db: Session = Depends(get_db), authorization: Optional[str] = Header(None), x_admin_token: Optional[str] = Header(None)):
    require_admin(authorization, x_admin_token, None)
    comp = db.get(Company, company_id)
    if not comp:
        raise HTTPException(status_code=404, detail="not found")
    access_code = secrets.token_hex(4)
    comp.access_hash = generate_password_hash(access_code)
    db.commit()
    return {"ok": True, "company_id": comp.id, "access_code": access_code}


@app.get("/admin/companies")
def admin_companies(db: Session = Depends(get_db), authorization: Optional[str] = Header(None), x_admin_token: Optional[str] = Header(None)):
    require_admin(authorization, x_admin_token, None)
    rows = db.query(Company).order_by(Company.created_at.desc()).all()
    return {"ok": True, "companies": [{"id": c.id, "name": c.name, "slug": c.slug, "created_at": c.created_at.isoformat() if c.created_at else ''} for c in rows]}


@app.get("/admin/company/{company_id}/impersonate-token")
def admin_impersonate_token(company_id: int, db: Session = Depends(get_db), authorization: Optional[str] = Header(None), x_admin_token: Optional[str] = Header(None)):
    # Returns a portal token for the given company
    require_admin(authorization, x_admin_token, None)
    comp = db.get(Company, company_id)
    if not comp:
        raise HTTPException(status_code=404, detail="not found")
    from payroll_shared.auth import make_company_token
    secret = get_settings().secret_key
    tok = make_company_token(secret, comp.id, comp.slug, is_admin=True)
    return {"ok": True, "slug": comp.slug, "token": tok}


# ------------------------------
# Admin: Login (FastAPI-only usage)
# ------------------------------


@app.post("/admin/login")
def admin_login_api(request: Request, password: str = Form(...)):
    admin_pw = get_settings().admin_password
    if password != admin_pw:
        # Rate limit by client IP
        try:
            ip = getattr(request.client, 'host', None) or request.headers.get('x-forwarded-for', '').split(',')[0].strip() or 'unknown'
        except Exception:
            ip = 'unknown'
        try:
            max_attempts = int(os.environ.get("ADMIN_LOGIN_RL_MAX", "10") or 10)
            window_sec = int(os.environ.get("ADMIN_LOGIN_RL_WINDOW", "600") or 600)
        except Exception:
            max_attempts = 10; window_sec = 600
        limiter = get_admin_rate_limiter()
        key = f"fastapi:{ip}"
        try:
            exceeded = limiter.too_many_attempts(key, window_sec, max_attempts)
        except Exception:
            exceeded = True
        if exceeded:
            raise HTTPException(status_code=429, detail="too many attempts")
        raise HTTPException(status_code=403, detail="invalid password")
    from payroll_shared.auth import make_admin_token
    secret = get_settings().secret_key
    try:
        ttl = int(os.environ.get("ADMIN_TOKEN_TTL", "7200") or 7200)
    except Exception:
        ttl = 7200
    try:
        ip = getattr(request.client, 'host', None) or request.headers.get('x-forwarded-for', '').split(',')[0].strip() or 'unknown'
        get_admin_rate_limiter().reset(f"fastapi:{ip}")
    except Exception:
        pass
    tok = make_admin_token(secret, ttl_seconds=ttl)
    return {"ok": True, "token": tok, "ttl": ttl}


@app.get("/portal/{slug}/api/payroll/{year}/{month}")
@app.get("/api/portal/{slug}/payroll/{year}/{month}")
def api_get_payroll(slug: str, year: int, month: int, db: Session = Depends(get_db), authorization: Optional[str] = Header(None), x_api_token: Optional[str] = Header(None), token: Optional[str] = None):
    company = require_company(slug, db, authorization, x_api_token, token)
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


@app.post("/portal/{slug}/payroll/{year}/{month}")
async def api_save_payroll(slug: str, year: int, month: int, request: Request, db: Session = Depends(get_db), authorization: Optional[str] = Header(None), x_api_token: Optional[str] = Header(None)):
    company = require_company(slug, db, authorization, x_api_token, None)
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
    return {"ok": True}


# ------------------------------
# Fields config (parity with Flask JSON APIs)
# ------------------------------

def _load_include_map(db: Session, company: Company) -> dict:
    rows = db.query(FieldPref).filter(FieldPref.company_id == company.id).all()
    inc = {"nhis": {}, "ei": {}}
    for p in rows:
        if bool(getattr(p, "ins_nhis", False)):
            inc["nhis"][p.field] = True
        if bool(getattr(p, "ins_ei", False)):
            inc["ei"][p.field] = True
    return inc


@app.get("/portal/{slug}/fields/calc-config")
@app.get("/api/portal/{slug}/fields/calc-config")
def api_get_calc_config(slug: str, db: Session = Depends(get_db)):
    company = get_company_by_slug(db, slug)
    if not company:
        raise HTTPException(status_code=404, detail="company not found")
    include = _load_include_map(db, company)
    return {"ok": True, "include": include}


@app.post("/portal/{slug}/fields/calc-config")
@app.post("/api/portal/{slug}/fields/calc-config")
def api_save_calc_config(slug: str, payload: dict, db: Session = Depends(get_db)):
    company = get_company_by_slug(db, slug)
    if not company:
        raise HTTPException(status_code=404, detail="company not found")
    inc = payload.get("include") or {}
    nhis = (inc.get("nhis") or {}) if isinstance(inc, dict) else {}
    ei = (inc.get("ei") or {}) if isinstance(inc, dict) else {}
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
    return {"ok": True}


def _base_exemptions_from_env() -> dict:
    try:
        raw = os.environ.get("INS_BASE_EXEMPTIONS", "")
        if not raw:
            return {}
        return json.loads(raw) if isinstance(raw, str) else {}
    except Exception:
        return {}


@app.get("/portal/{slug}/fields/exempt-config")
@app.get("/api/portal/{slug}/fields/exempt-config")
def api_get_exempt_config(slug: str, db: Session = Depends(get_db)):
    company = get_company_by_slug(db, slug)
    if not company:
        raise HTTPException(status_code=404, detail="company not found")
    rows = db.query(FieldPref).filter(FieldPref.company_id == company.id).all()
    ex: dict = {}
    for p in rows:
        if bool(getattr(p, "exempt_enabled", False)) or int(getattr(p, "exempt_limit", 0) or 0) > 0:
            ex[p.field] = {"enabled": bool(p.exempt_enabled), "limit": int(p.exempt_limit or 0)}
    return {"ok": True, "exempt": ex, "base": _base_exemptions_from_env()}


@app.post("/portal/{slug}/fields/exempt-config")
@app.post("/api/portal/{slug}/fields/exempt-config")
def api_save_exempt_config(slug: str, payload: dict, db: Session = Depends(get_db)):
    company = get_company_by_slug(db, slug)
    if not company:
        raise HTTPException(status_code=404, detail="company not found")
    raw = payload.get("exempt") or payload.get("ov") or {}
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="invalid payload")
    for field, conf in raw.items():
        enabled = bool((conf or {}).get("enabled"))
        try:
            limit = int((conf or {}).get("limit") or 0)
        except Exception:
            limit = 0
        pref = db.query(FieldPref).filter(FieldPref.company_id == company.id, FieldPref.field == field).first()
        if not pref:
            pref = FieldPref(company_id=company.id, field=field)
            db.add(pref)
        pref.exempt_enabled = enabled
        pref.exempt_limit = limit
    db.commit()
    return {"ok": True}


@app.post("/portal/{slug}/fields/add")
@app.post("/api/portal/{slug}/fields/add")
def api_add_field(slug: str, payload: dict, db: Session = Depends(get_db)):
    company = get_company_by_slug(db, slug)
    if not company:
        raise HTTPException(status_code=404, detail="company not found")
    label = (payload.get("label") or "").strip()
    typ = (payload.get("typ") or "number").strip()
    if not label:
        raise HTTPException(status_code=400, detail="label required")
    # Prevent dup by label per company (best-effort)
    existing = db.query(ExtraField).filter(ExtraField.company_id == company.id, ExtraField.label == label).first()
    if existing:
        return {"ok": True, "field": {"name": existing.name, "label": existing.label, "typ": existing.typ}, "existed": True}
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
    return {"ok": True, "field": {"name": ef.name, "label": ef.label, "typ": ef.typ}}


@app.post("/portal/{slug}/fields/delete")
@app.post("/api/portal/{slug}/fields/delete")
def api_delete_field(slug: str, payload: dict, db: Session = Depends(get_db)):
    company = get_company_by_slug(db, slug)
    if not company:
        raise HTTPException(status_code=404, detail="company not found")
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    ef = db.query(ExtraField).filter(ExtraField.company_id == company.id, ExtraField.name == name).first()
    if not ef:
        raise HTTPException(status_code=404, detail="not found")
    db.delete(ef)
    db.commit()
    return {"ok": True}


@app.post("/portal/{slug}/fields/group-config")
@app.post("/api/portal/{slug}/fields/group-config")
def api_save_group_config(slug: str, payload: dict, db: Session = Depends(get_db)):
    company = get_company_by_slug(db, slug)
    if not company:
        raise HTTPException(status_code=404, detail="company not found")
    group_map = payload.get("map") or payload.get("group") or {}
    alias_map = payload.get("alias") or {}
    if not isinstance(group_map, dict) or not isinstance(alias_map, dict):
        raise HTTPException(status_code=400, detail="invalid payload")
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
    return {"ok": True}


# ------------------------------
# Close / Open month
# ------------------------------

@app.post("/portal/{slug}/payroll/{year}/{month}/close")
def api_close_month(slug: str, year: int, month: int, db: Session = Depends(get_db), authorization: Optional[str] = Header(None), x_api_token: Optional[str] = Header(None)):
    company = require_company(slug, db, authorization, x_api_token, None)
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
    return {"ok": True}


@app.post("/portal/{slug}/payroll/{year}/{month}/open")
def api_open_month(slug: str, year: int, month: int, db: Session = Depends(get_db), authorization: Optional[str] = Header(None), x_api_token: Optional[str] = Header(None)):
    company = require_company(slug, db, authorization, x_api_token, None)
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
    return {"ok": True}


# ------------------------------
# Export (basic workbook)
# ------------------------------
@app.get("/portal/{slug}/export/{year}/{month}")
def api_export(slug: str, year: int, month: int, db: Session = Depends(get_db), authorization: Optional[str] = Header(None), x_api_token: Optional[str] = Header(None), token: Optional[str] = None):
    company = require_company(slug, db, authorization, x_api_token, token)
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
    from payroll_shared.exporter import build_salesmap_workbook
    from payroll_shared.schema import DEFAULT_COLUMNS
    from fastapi.responses import StreamingResponse
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
def _extract_token(authorization: Optional[str], x_api_token: Optional[str], token_qs: Optional[str]) -> Optional[str]:
    if token_qs:
        return token_qs
    if x_api_token:
        return x_api_token
    if authorization and authorization.lower().startswith('bearer '):
        return authorization.split(' ', 1)[1].strip()
    return None


def require_company(slug: str, db: Session, authorization: Optional[str] = Header(None), x_api_token: Optional[str] = Header(None), token: Optional[str] = None) -> Company:
    tok = _extract_token(authorization, x_api_token, token)
    if not tok:
        raise HTTPException(status_code=403, detail="missing token")
    secret = get_settings().secret_key
    payload = verify_company_token(secret, tok)
    if not payload:
        raise HTTPException(status_code=403, detail="invalid token")
    if str(payload.get('slug')) != str(slug):
        raise HTTPException(status_code=403, detail="slug mismatch")
    company = get_company_by_slug(db, slug)
    if not company:
        raise HTTPException(status_code=404, detail="company not found")
    if int(payload.get('cid', 0)) != int(company.id):
        raise HTTPException(status_code=403, detail="company mismatch")
    # Optional revocation check: if company has token_key, require matching key claim
    try:
        ckey = (company.token_key or '').strip()
        pkey = str(payload.get('key', '') or '').strip()
        if ckey and (ckey != pkey):
            raise HTTPException(status_code=403, detail="token revoked")
    except AttributeError:
        pass
    return company
