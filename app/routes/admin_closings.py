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
    only_closed: bool = False,
    status: Optional[str] = None,  # 'all' | 'closed' | 'progress' | 'none'
    fill_range: bool = False,
    limit: int = 50,
    cursor: Optional[str] = None,
    db: Session = Depends(get_db),
):
    if not _is_admin(request):
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    q = db.query(MonthlyPayroll, Company).join(Company, Company.id == MonthlyPayroll.company_id)
    if company_id:
        q = q.filter(MonthlyPayroll.company_id == int(company_id))
    # Backward-compatibility: only_closed takes precedence for SQL filtering
    if only_closed or (status and status == 'closed'):
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

    # Build map for quick lookup (by company, year, month)
    rec_map: dict[tuple[int, int, int], dict] = {}
    items_rows = rows[:limit]
    for rec, comp in items_rows:
        try:
            data = json.loads(rec.rows_json or "[]")
            rcnt = len(data) if isinstance(data, list) else 0
        except Exception:
            rcnt = 0
        status = "closed" if bool(getattr(rec, "is_closed", False)) else ("in_progress" if rcnt > 0 else "none")
        rec_map[(int(comp.id), int(rec.year), int(rec.month))] = {
            "company_id": comp.id,
            "company_name": comp.name,
            "year": int(rec.year),
            "month": int(rec.month),
            "is_closed": bool(getattr(rec, "is_closed", False)),
            "updated_at": rec.updated_at.isoformat() if getattr(rec, "updated_at", None) else None,
            "rows_count": rcnt,
            "status": status,
        }

    # If requested and range fully provided for a specific company, fill missing months
    items = []
    if fill_range and company_id and frm and to:
        try:
            fy, fm = _parse_month(frm)
            ty, tm = _parse_month(to)
        except Exception:
            fy=fm=ty=tm=0
        def iter_months(y1,m1,y2,m2):
            ym = y1*12 + (m1-1)
            end = y2*12 + (m2-1)
            seq = []
            while ym <= end:
                y = ym // 12; m = (ym % 12) + 1
                seq.append((y,m))
                ym += 1
            return seq
        if fy>0 and ty>0:
            # descending for recent first
            for y,m in reversed(iter_months(fy,fm,ty,tm)):
                item = rec_map.get((int(company_id), y, m))
                if not item:
                    # skeleton for missing month
                    comp = db.get(Company, int(company_id)) if company_id else None
                    items.append({
                        "company_id": int(company_id),
                        "company_name": comp.name if comp else "",
                        "year": y,
                        "month": m,
                        "is_closed": False,
                        "updated_at": None,
                        "rows_count": 0,
                        "status": "none",
                    })
                else:
                    items.append(item)
            has_more = False
            next_cur = None
            return {"ok": True, "items": items, "has_more": has_more, "next_cursor": next_cur}

    # Default (no filling): current page items, optional post-filter by status
    items = list(rec_map.values())
    st = (status or 'all').strip().lower()
    if st == 'progress':
      items = [it for it in items if (it.get('status') == 'in_progress')]
    elif st == 'none':
      # 'none' is meaningful when fill_range produced skeletons; otherwise, filter on computed status
      items = [it for it in items if (it.get('status') == 'none')]
    has_more = len(rows) > limit
    next_cur = None
    if has_more and items_rows:
        last_rec, _ = items_rows[-1]
        next_cur = encode_cursor({"year": int(last_rec.year), "month": int(last_rec.month), "id": int(last_rec.id)})
    return {"ok": True, "items": items, "has_more": has_more, "next_cursor": next_cur}


@router.get("/export.zip")
def export_zip(
    request: Request,
    company_id: Optional[int] = None,
    month: Optional[List[str]] = None,  # repeated yyyy-mm; also accepts manual parsing
    db: Session = Depends(get_db),
):
    if not _is_admin(request):
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    # Build selection map: either (company_id + months) or sel=company:yyy-mm list
    selections: dict[int, list[tuple[int,int]]] = {}
    # Path 1: explicit 'sel' pairs
    sels = []
    try:
        sels = request.query_params.getlist("sel")
    except Exception:
        sels = []
    if sels:
        for s in sels:
            try:
                cid_str, mon = str(s).split(":", 1)
                y, m = _parse_month(mon)
                cid = int(cid_str)
                selections.setdefault(cid, []).append((y, m))
            except Exception:
                continue
    else:
        # Path 2: single company + multiple month params (backward compatible)
        # Robustly collect months from query (supports month or month[]= ... styles)
        months = list(month or [])
        try:
            if not months:
                months = request.query_params.getlist("month") or request.query_params.getlist("month[]")
        except Exception:
            months = list(month or [])
        if not months or not company_id:
            return JSONResponse({"ok": False, "error": "no months selected"}, status_code=400)
        lst: list[tuple[int,int]] = []
        for mon in months:
            try:
                y, m = _parse_month(mon)
                lst.append((y,m))
            except Exception:
                continue
        if not lst:
            return JSONResponse({"ok": False, "error": "invalid months"}, status_code=400)
        selections[int(company_id)] = lst

    # Build ZIP in spooled file
    spooled: io.BufferedRandom = tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024)  # 32MB memory, then disk
    with zipfile.ZipFile(spooled, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        from core.schema import DEFAULT_COLUMNS
        import re
        def _make_filename(company_name: str, y: int, m: int) -> str:
            tail = f"{y%100:02d}{m:02d}"
            title = f"{company_name}_급여_{tail}"
            # sanitize for zip entry (avoid path separators and reserved characters)
            title = re.sub(r'[\\/:*?"<>|]+', '_', title)
            title = title.replace(' ', '')
            return title + '.xlsx'
        for cid, pairs in selections.items():
            comp = db.get(Company, int(cid))
            if not comp:
                continue
            # cache extras/prefs per company for efficiency
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
            all_cols = list(DEFAULT_COLUMNS) + [(e.name, e.label, e.typ or 'number') for e in extras]
            seen_pairs = set()
            for (y, m) in pairs:
                key = (y, m)
                if key in seen_pairs: continue
                seen_pairs.add(key)
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
                arcname = _make_filename(comp.name or comp.slug, y, m)
                zf.writestr(arcname, bio.read())

    # audit (best effort)
    try:
        record_event(db,
            actor='admin',
            action='bulk_export_download',
            resource='/admin/closings/export.zip',
            company_id=None,
            meta={"selection": list(selections.keys())},
        )
    except Exception:
        pass

    spooled.seek(0)
    from urllib.parse import quote
    fname = f"closings_{comp.slug}.zip"
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"}
    return StreamingResponse(spooled, media_type="application/zip", headers=headers)
