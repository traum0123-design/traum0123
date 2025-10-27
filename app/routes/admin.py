from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.models import Company, WithholdingCell
from core.services import companies as company_service
from core.services.auth import issue_admin_token, issue_company_token
from payroll_api.database import get_db

from .portal import (
    ADMIN_COOKIE_NAME,
    COOKIE_SECURE,
    PORTAL_COOKIE_NAME,
    _apply_template_security,
    _base_context,
    _is_admin,
)

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
def login_action(request: Request, password: str = Form(...), csrf_token: str | None = Form(None)):
    if not company_service.verify_admin_password(password):
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
    return response


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
def company_detail(request: Request, company_id: int, db: Session = Depends(get_db), code: str | None = None):
    if not _is_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="company not found")
    context = _base_context(request)
    context.update({
        "company": company,
        "new_code": code,
        "portal_login_url": f"/portal/{company.slug}/login",
    })
    response = templates.TemplateResponse("admin_company_detail.html", context)
    return _apply_template_security(request, response)


@router.post("/company/{company_id}/reset-code", name="admin.company_reset_code")
def company_reset_code(request: Request, company_id: int, db: Session = Depends(get_db), csrf_token: str | None = Form(None)):
    if not _is_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="company not found")
    code = company_service.rotate_company_access(db, company)
    return RedirectResponse(url=f"/admin/company/{company_id}?code={code}", status_code=303)


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
