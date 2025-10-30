from __future__ import annotations

from typing import Optional, List

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from payroll_api.database import get_db
from core.models import Company, MonthlyPayroll, ExtraField, FieldPref
from core.services.audit import record_event
from core.exporter import build_salesmap_workbook_stream_spooled as build_workbook
from core.utils.cursor import encode_cursor, decode_cursor

from .portal import (
    _apply_template_security,
    _base_context,
    _is_admin,
)

from pathlib import Path
from fastapi.templating import Jinja2Templates
import json
import io
import zipfile
import tempfile


router = APIRouter(prefix="/admin/closings", tags=["admin-closings"]) 

TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "payroll_portal" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


def _parse_month(m: str) -> tuple[int, int]:
    s = (m or "").strip()
    if not s:
        raise ValueError("empty month")
    parts = s.split("-")
    if len(parts) != 2:
        raise ValueError("invalid month format")
    y = int(parts[0]); mo = int(parts[1])
    if mo < 1 or mo > 12:
        raise ValueError("invalid month")
    return y, mo


@router.get("/", response_class=HTMLResponse, name="admin.closings")
def closings_page(request: Request, db: Session = Depends(get_db)):
    if not _is_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    companies = db.query(Company).order_by(Company.name.asc()).all()
    context = _base_context(request)
    context.update({
        "companies": companies,
    })
    response = templates.TemplateResponse("admin_closings.html", context)
    return _apply_template_security(request, response)


@router.get("/data.json")
def closings_data(
    request: Request,
    company_id: Optional[int] = None,
    frm: Optional[str] = None,  # yyyy-mm
    to: Optional[str] = None,   # yyyy-mm
    only_closed: bool = True,
    limit: int = 50,
    cursor: Optional[str] = None,
    db: Session = Depends(get_db),
):
    if not _is_admin(request):
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    q = db.query(MonthlyPayroll, Company).join(Company, Company.id == MonthlyPayroll.company_id)
    if company_id:
        q = q.filter(MonthlyPayroll.company_id == int(company_id))
    if only_closed:
        q = q.filter(MonthlyPayroll.is_closed == True)  # noqa: E712

    if frm:
        fy, fm = _parse_month(frm)
        q = q.filter(or_(MonthlyPayroll.year > fy, and_(MonthlyPayroll.year == fy, MonthlyPayroll.month >= fm)))
    if to:
        ty, tm = _parse_month(to)
        q = q.filter(or_(MonthlyPayroll.year < ty, and_(MonthlyPayroll.year == ty, MonthlyPayroll.month <= tm)))

    # order desc by default (recent first)
    q = q.order_by(MonthlyPayroll.year.desc(), MonthlyPayroll.month.desc(), MonthlyPayroll.id.desc())

    if cursor:
        try:
            cur = decode_cursor(cursor)
            cy = int(cur.get("year")); cm = int(cur.get("month")); cid = int(cur.get("id"))
            q = q.filter(
                or_(
                    MonthlyPayroll.year < cy,
                    and_(MonthlyPayroll.year == cy, MonthlyPayroll.month < cm),
                    and_(MonthlyPayroll.year == cy, MonthlyPayroll.month == cm, MonthlyPayroll.id < cid),
                )
            )
        except Exception:
            return JSONResponse({"ok": False, "error": "invalid cursor"}, status_code=400)

    rows = q.limit(max(1, min(200, limit)) + 1).all()
    has_more = len(rows) > limit
    items_rows = rows[:limit]
    items = []
    for rec, comp in items_rows:
        try:
            data = json.loads(rec.rows_json or "[]")
            rcnt = len(data) if isinstance(data, list) else 0
        except Exception:
            rcnt = 0
        items.append({
            "company_id": comp.id,
            "company_name": comp.name,
            "year": int(rec.year),
            "month": int(rec.month),
            "is_closed": bool(getattr(rec, "is_closed", False)),
            "updated_at": rec.updated_at.isoformat() if getattr(rec, "updated_at", None) else None,
            "rows_count": rcnt,
        })

    next_cur = None
    if has_more and items_rows:
        last_rec, _ = items_rows[-1]
        next_cur = encode_cursor({"year": last_rec.year, "month": last_rec.month, "id": last_rec.id})
    return {"ok": True, "items": items, "has_more": has_more, "next_cursor": next_cur}


@router.get("/export.zip")
def export_zip(
    request: Request,
    company_id: int,
    month: Optional[List[str]] = None,  # repeated yyyy-mm; also accepts manual parsing
    db: Session = Depends(get_db),
):
    if not _is_admin(request):
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    # Robustly collect months from query (supports month or month[]= ... styles)
    months = list(month or [])
    try:
        if not months:
            months = request.query_params.getlist("month") or request.query_params.getlist("month[]")
    except Exception:
        months = list(month or [])
    if not months:
        return JSONResponse({"ok": False, "error": "no months selected"}, status_code=400)
    comp = db.get(Company, int(company_id))
    if not comp:
        return JSONResponse({"ok": False, "error": "company not found"}, status_code=404)

    # Build ZIP in spooled file
    spooled: io.BufferedRandom = tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024)  # 32MB memory, then disk
    with zipfile.ZipFile(spooled, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for mon in months:
            try:
                y, m = _parse_month(mon)
            except Exception:
                continue
            rec = (
                db.query(MonthlyPayroll)
                .filter(MonthlyPayroll.company_id == comp.id, MonthlyPayroll.year == y, MonthlyPayroll.month == m)
                .first()
            )
            if not rec:
                continue
            try:
                rows = json.loads(rec.rows_json or "[]")
            except Exception:
                rows = []
            # extras and prefs
            extras = (
                db.query(ExtraField)
                .filter(ExtraField.company_id == comp.id)
                .order_by(ExtraField.position.asc(), ExtraField.id.asc())
                .all()
            )
            prefs = db.query(FieldPref).filter(FieldPref.company_id == comp.id).all()
            gp: dict[str, str] = {}
            ap: dict[str, str] = {}
            for p in prefs:
                if getattr(p, "group", None) and p.group != "none":
                    gp[p.field] = p.group
                if getattr(p, "alias", None):
                    ap[p.field] = p.alias

            # Build workbook with default columns + extras (keep parity with single export)
            from core.schema import DEFAULT_COLUMNS
            all_cols = list(DEFAULT_COLUMNS) + [(e.name, e.label, e.typ or 'number') for e in extras]
            bio = build_workbook(
                company_slug=comp.slug,
                year=y,
                month=m,
                rows=rows,
                all_columns=all_cols,
                group_prefs=gp,
                alias_prefs=ap,
            )
            bio.seek(0)
            arcname = f"{comp.slug}_{y}-{m:02d}.xlsx"
            zf.writestr(arcname, bio.read())

    # audit (best effort)
    try:
        record_event(db,
            actor='admin',
            action='bulk_export_download',
            resource='/admin/closings/export.zip',
            company_id=comp.id,
            meta={"months": months},
        )
    except Exception:
        pass

    spooled.seek(0)
    from urllib.parse import quote
    fname = f"closings_{comp.slug}.zip"
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"}
    return StreamingResponse(spooled, media_type="application/zip", headers=headers)
