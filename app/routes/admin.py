from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.models import (
    Company,
    WithholdingCell,
    AuditEvent,
    PolicySettingHistory,
    ExtraField,
    FieldPref,
    MonthlyPayroll,
    MonthlyPayrollRow,
    PolicySetting,
    IdempotencyRecord,
)
from core.services import companies as company_service
from core.services.auth import issue_admin_token, issue_company_token
from core.services.audit import record_event
from payroll_api.database import get_db

from .portal import (
    ADMIN_COOKIE_NAME,
    COOKIE_SECURE,
    PORTAL_COOKIE_NAME,
    _apply_template_security,
    _base_context,
    _is_admin,
    _verify_csrf,
)
from payroll_portal.services.rate_limit import limiter, admin_login_key

router = APIRouter(prefix="/admin", tags=["admin"])

TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "payroll_portal" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


@router.get("/login", response_class=HTMLResponse, name="admin.login")
def login_page(request: Request):
    if _is_admin(request):
        return RedirectResponse(url="/admin/", status_code=303)
    context = _base_context(request)
    response = templates.TemplateResponse("admin_login.html", context)
    return _apply_template_security(request, response)


@router.post("/login", name="admin.login_post")
def login_action(request: Request, password: str = Form(...), csrf_token: str | None = Form(None), db: Session = Depends(get_db)):
    _verify_csrf(request, csrf_token)
    rl = limiter()
    key = admin_login_key(request)
    if not company_service.verify_admin_password(password):
        # count attempts and possibly block for a minute
        try:
            exceeded = rl.too_many_attempts(key, 60, 10)
        except Exception:
            exceeded = True
        if exceeded:
            try:
                record_event(db=db, actor='admin', action='login_rate_limited', resource='/admin/login', ip=str(request.client.host if request.client else ''), ua=request.headers.get('user-agent',''), result='fail')
            except Exception:
                pass
            return RedirectResponse(url="/admin/login?error=too_many_attempts", status_code=303)
        try:
            record_event(db=db, actor='admin', action='login_failed', resource='/admin/login', ip=str(request.client.host if request.client else ''), ua=request.headers.get('user-agent',''), result='fail')
        except Exception:
            pass
        return RedirectResponse(url="/admin/login?error=1", status_code=303)
    token = issue_admin_token()
    response = RedirectResponse(url="/admin/", status_code=303)
    response.set_cookie(
        ADMIN_COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
    )
    try:
        record_event(db=db, actor='admin', action='login_success', resource='/admin/login', ip=str(request.client.host if request.client else ''), ua=request.headers.get('user-agent',''), result='ok')
    except Exception:
        pass
    return response


@router.get("/withholding", response_class=HTMLResponse, name="admin.withholding_page")
def withholding_page(request: Request, db: Session = Depends(get_db)):
    if not _is_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    from sqlalchemy import func
    years = db.execute(
        select(
            WithholdingCell.year,
            func.count(),
            func.min(WithholdingCell.wage),
            func.max(WithholdingCell.wage),
        )
        .group_by(WithholdingCell.year)
        .order_by(WithholdingCell.year.desc())
    ).all()
    context = _base_context(request)
    context.update({"years": years})
    response = templates.TemplateResponse("admin_withholding.html", context)
    return _apply_template_security(request, response)


@router.get("/logout", name="admin.logout")
def admin_logout():
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie(ADMIN_COOKIE_NAME, path="/")
    return response


@router.get("/", response_class=HTMLResponse, name="admin.index")
def admin_index(request: Request, db: Session = Depends(get_db)):
    if not _is_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    companies = db.query(Company).order_by(Company.created_at.desc()).all()
    rows = db.execute(
        select(
            WithholdingCell.year,
            func.count(),
            func.min(WithholdingCell.wage),
            func.max(WithholdingCell.wage),
        )
        .group_by(WithholdingCell.year)
        .order_by(WithholdingCell.year.desc())
    ).all()
    wh_counts = [
        {
            "year": row[0],
            "count": row[1],
            "min_wage": row[2],
            "max_wage": row[3],
        }
        for row in rows
    ]
    context = _base_context(request)
    context.update({"companies": companies, "wh_counts": wh_counts})
    response = templates.TemplateResponse("admin_index.html", context)
    return _apply_template_security(request, response)


@router.post("/company/new", name="admin.company_new")
def company_new(request: Request, name: str = Form(...), slug: str = Form(...), db: Session = Depends(get_db), csrf_token: str | None = Form(None)):
    _verify_csrf(request, csrf_token)
    if not _is_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    name = (name or "").strip()
    slug = (slug or "").strip().lower()
    if not name or not slug:
        return RedirectResponse(url="/admin/?error=missing", status_code=303)
    if db.query(Company).filter(Company.slug == slug).first():
        return RedirectResponse(url="/admin/?error=exists", status_code=303)
    company, code = company_service.create_company(db, name, slug)
    response = RedirectResponse(url=f"/admin/company/{company.id}?code={code}", status_code=303)
    return response


@router.get("/company/{company_id}", response_class=HTMLResponse, name="admin.company_detail")
def company_detail(
    request: Request,
    company_id: int,
    db: Session = Depends(get_db),
    code: str | None = None,
    rotated: int | None = None,
):
    if not _is_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="company not found")
    context = _base_context(request)
    context.update({
        "company": company,
        "new_code": code,
        "token_rotated": bool(rotated) if rotated is not None else False,
        "portal_login_url": f"/portal/{company.slug}/login",
    })
    response = templates.TemplateResponse("admin_company_detail.html", context)
    return _apply_template_security(request, response)


@router.post("/company/{company_id}/reset-code", name="admin.company_reset_code")
def company_reset_code(request: Request, company_id: int, db: Session = Depends(get_db), csrf_token: str | None = Form(None)):
    _verify_csrf(request, csrf_token)
    if not _is_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="company not found")
    code = company_service.rotate_company_access(db, company)
    try:
        record_event(db=db, actor='admin', action='company_access_code_rotated', resource=f"/admin/company/{company_id}/reset-code", company_id=company.id, ip=str(request.client.host if request.client else ''), ua=request.headers.get('user-agent',''))
    except Exception:
        pass
    return RedirectResponse(url=f"/admin/company/{company_id}?code={code}", status_code=303)


@router.post("/company/{company_id}/rotate-token-key", name="admin.company_rotate_token_key")
def company_rotate_token_key(
    request: Request,
    company_id: int,
    db: Session = Depends(get_db),
    csrf_token: str | None = Form(None),
):
    _verify_csrf(request, csrf_token)
    if not _is_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="company not found")
    company_service.rotate_company_token_key(db, company)
    try:
        record_event(db=db, actor='admin', action='company_token_key_rotated', resource=f"/admin/company/{company_id}/rotate-token-key", company_id=company.id, ip=str(request.client.host if request.client else ''), ua=request.headers.get('user-agent',''))
    except Exception:
        pass
    return RedirectResponse(url=f"/admin/company/{company_id}?rotated=1", status_code=303)


@router.post("/company/{company_id}/delete", name="admin.company_delete")
def company_delete(
    request: Request,
    company_id: int,
    db: Session = Depends(get_db),
    csrf_token: str | None = Form(None),
):
    _verify_csrf(request, csrf_token)
    if not _is_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    comp = db.get(Company, company_id)
    if not comp:
        raise HTTPException(status_code=404, detail="company not found")
    # Best-effort audit before delete
    try:
        record_event(
            db=db,
            actor='admin',
            action='company_delete_requested',
            resource=f"/admin/company/{company_id}/delete",
            company_id=comp.id,
            ip=str(request.client.host if request.client else ''),
            ua=request.headers.get('user-agent',''),
            result='ok',
        )
    except Exception:
        pass
    # Delete dependent records first to satisfy FKs
    try:
        db.query(MonthlyPayrollRow).filter(MonthlyPayrollRow.company_id == comp.id).delete(synchronize_session=False)
        db.query(MonthlyPayroll).filter(MonthlyPayroll.company_id == comp.id).delete(synchronize_session=False)
        db.query(ExtraField).filter(ExtraField.company_id == comp.id).delete(synchronize_session=False)
        db.query(FieldPref).filter(FieldPref.company_id == comp.id).delete(synchronize_session=False)
        db.query(PolicySetting).filter(PolicySetting.company_id == comp.id).delete(synchronize_session=False)
        # Keep audit trail, but you may prune by company if policy requires
        db.query(IdempotencyRecord).filter(IdempotencyRecord.company_id == comp.id).delete(synchronize_session=False)
        # Finally, delete the company
        db.delete(comp)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return RedirectResponse(url="/admin/?deleted=1", status_code=303)


@router.get("/company/{company_id}/impersonate", name="admin.company_impersonate")
def company_impersonate(request: Request, company_id: int, db: Session = Depends(get_db), year: int | None = None, month: int | None = None):
    if not _is_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="company not found")
    token = issue_company_token(db, company, is_admin=True)
    target = f"/portal/{company.slug}"
    if year and month:
        target = f"/portal/{company.slug}/payroll/{year}/{month}"
    response = RedirectResponse(url=target, status_code=303)
    response.set_cookie(
        PORTAL_COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
    )
    admin_token = request.cookies.get(ADMIN_COOKIE_NAME)
    if admin_token:
        response.set_cookie(
            ADMIN_COOKIE_NAME,
            admin_token,
            httponly=True,
            samesite="lax",
            secure=COOKIE_SECURE,
        )
    return response


@router.get("/audit", response_class=HTMLResponse, name="admin.audit")
def audit_page(
    request: Request,
    db: Session = Depends(get_db),
    company_id: int | None = None,
    actor: str | None = None,
    cursor: str | None = None,
    order: str | None = None,
):
    if not _is_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    q = db.query(AuditEvent)
    if company_id is not None:
        q = q.filter(AuditEvent.company_id == int(company_id))
    if actor:
        q = q.filter(AuditEvent.actor == str(actor))
    desc = (order or "desc").lower() != "asc"
    if desc:
        q = q.order_by(AuditEvent.id.desc())
    else:
        q = q.order_by(AuditEvent.id.asc())
    if cursor:
        try:
            import base64, json
            cur = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
            cid = int(cur.get("id"))
        except Exception:
            cid = None
        if cid:
            if desc:
                q = q.filter(AuditEvent.id < cid)
            else:
                q = q.filter(AuditEvent.id > cid)
    rows = q.limit(51).all()
    has_more = len(rows) > 50
    raw_items = rows[:50]
    # Build lightweight entries for template consumption
    def _flatten(d, prefix=""):
        out = {}
        try:
            it = dict(d or {})
        except Exception:
            it = {}
        for k, v in it.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, dict):
                out.update(_flatten(v, key))
            else:
                out[key] = v
        return out
    # Friendly labels for actions/results
    ACTION_LABELS = {
        "login_success": "관리자 로그인 성공",
        "login_failed": "관리자 로그인 실패",
        "login_rate_limited": "로그인 시도 제한",
        "company_access_code_rotated": "회사 접속코드 재발급",
        "company_token_key_rotated": "토큰 키 회전(강제 로그아웃)",
        "impersonate_token_issued": "가장 토큰 발급",
        "export_download": "엑셀 다운로드",
        "bulk_export_download": "엑셀 일괄 다운로드",
        "month_opened": "월 마감 해제",
        "month_closed": "월 마감",
        "save_payroll": "급여 저장",
        "company_delete_requested": "회사 삭제 요청",
        "policy_updated": "정책 변경",
    }
    RESULT_LABELS = {
        "ok": "성공",
        "fail": "실패",
        "denied": "거부",
    }
    items = []
    for r in raw_items:
        # Parse meta for optional summary
        try:
            import json as _json
            meta = _json.loads(getattr(r, "meta_json", "") or "{}")
        except Exception:
            meta = {}
        flat = _flatten(meta)
        parts = []
        for k in sorted(flat.keys()):
            v = flat.get(k)
            if isinstance(v, (dict, list)):
                continue
            parts.append(f"{k}={v}")
        summary = "; ".join(parts[:6]) + (" …" if len(parts) > 6 else "")
        act = getattr(r, "action", "") or ""
        res = getattr(r, "result", "") or ""
        items.append({
            "id": getattr(r, "id", None),
            "ts": getattr(r, "ts", None),
            "company_id": getattr(r, "company_id", None),
            "actor": getattr(r, "actor", ""),
            "action": act,
            "action_label": ACTION_LABELS.get(act, act or "(알 수 없음)"),
            "resource": getattr(r, "resource", ""),
            "result": res,
            "result_label": RESULT_LABELS.get(res, res or ""),
            "ip": getattr(r, "ip", ""),
            "ua": getattr(r, "ua", ""),
            "summary": summary,
        })
    next_cursor = None
    if has_more and raw_items:
        last_id = getattr(raw_items[-1], "id", None)
        if last_id is not None:
            try:
                import base64, json
                next_cursor = base64.urlsafe_b64encode(json.dumps({"id": int(last_id)}).encode()).decode()
            except Exception:
                next_cursor = None
    context = _base_context(request)
    context.update({
        "events": items,
        "has_more": has_more,
        "next_cursor": next_cursor,
        "filters": {"company_id": company_id, "actor": actor, "order": order or "desc"},
    })
    response = templates.TemplateResponse("admin_audit.html", context)
    return _apply_template_security(request, response)


@router.get("/policy-history", response_class=HTMLResponse, name="admin.policy_history")
def policy_history_page(
    request: Request,
    db: Session = Depends(get_db),
    company_id: int | None = None,
    company_slug: str | None = None,
    year: int | None = None,
    cursor: str | None = None,
    order: str | None = None,
):
    if not _is_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    # Resolve company by slug when provided
    if company_id is None and company_slug:
        comp = db.query(Company).filter(Company.slug == str(company_slug).strip().lower()).first()
        if comp:
            company_id = int(comp.id)

    q = db.query(PolicySettingHistory)
    if company_id is not None:
        q = q.filter(PolicySettingHistory.company_id == int(company_id))
    if year is not None:
        q = q.filter(PolicySettingHistory.year == int(year))
    desc = (order or "desc").lower() != "asc"
    if desc:
        q = q.order_by(PolicySettingHistory.ts.desc(), PolicySettingHistory.id.desc())
    else:
        q = q.order_by(PolicySettingHistory.ts.asc(), PolicySettingHistory.id.asc())
    if cursor:
        try:
            import base64, json
            cur = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
            cid = int(cur.get("id"))
        except Exception:
            cid = None
        if cid:
            if desc:
                q = q.filter(PolicySettingHistory.id < cid)
            else:
                q = q.filter(PolicySettingHistory.id > cid)
    rows = q.limit(51).all()
    has_more = len(rows) > 50
    items = rows[:50]
    next_cursor = None
    if has_more and raw_items:
        try:
            import base64, json
            next_cursor = base64.urlsafe_b64encode(json.dumps({"id": raw_items[-1].id}).encode()).decode()
        except Exception:
            next_cursor = None
    # Build filter options
    # Companies appearing in history (id->slug)
    comp_rows = (
        db.query(PolicySettingHistory.company_id, Company.slug)
        .outerjoin(Company, Company.id == PolicySettingHistory.company_id)
        .distinct()
        .all()
    )
    company_options = []
    for cid, slug in comp_rows:
        if cid is None:
            continue
        label = slug or f"company:{cid}"
        company_options.append({"id": int(cid), "label": label})
    # Year options
    year_rows = db.query(PolicySettingHistory.year).distinct().all()
    year_options = sorted({int(y[0]) for y in year_rows}, reverse=True)

    context = _base_context(request)
    context.update({
        "items": items,
        "has_more": has_more,
        "next_cursor": next_cursor,
        "filters": {"company_id": company_id, "company_slug": company_slug, "year": year, "order": order or "desc"},
        "company_options": company_options,
        "year_options": year_options,
    })
    response = templates.TemplateResponse("admin_policy_history.html", context)
    return _apply_template_security(request, response)
