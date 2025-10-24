from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from .models import Company, ExtraField, FieldPref


def _normalize_label_text(label: str) -> str:
    if label is None:
        return ""
    s = str(label)
    s = s.replace("\u00A0", " ").replace("\u3000", " ")
    s = s.replace("\u200b", "").replace("\u200c", "").replace("\u200d", "")
    s = " ".join(s.strip().split())
    return s


def cleanup_duplicate_extra_fields(s: Session, company: Company) -> bool:
    """Collapse duplicate ExtraField entries by normalized label for a company.

    - Keep the earliest created field (smallest id) for each normalized label.
    - Migrate FieldPref rows to the surviving field and merge metadata
      (alias/group/flags) to avoid preference loss.

    Returns:
        bool: True if any rows were removed or preferences updated.
    """
    changed = False
    rows: list[ExtraField] = (
        s.query(ExtraField)
        .filter(ExtraField.company_id == company.id)
        .order_by(ExtraField.label.asc(), ExtraField.id.asc())
        .all()
    )
    by_label: dict[str, list[ExtraField]] = {}
    for ef in rows:
        norm = _normalize_label_text(ef.label)
        by_label.setdefault(norm, []).append(ef)
    for _, items in by_label.items():
        if len(items) <= 1:
            continue
        keep = items[0]
        for dup in items[1:]:
            _merge_field_prefs(s, company.id, keep, dup)
            s.delete(dup)
            changed = True
    if changed:
        try:
            s.commit()
        except Exception:
            s.rollback()
            raise
    return changed


def _merge_field_prefs(
    s: Session,
    company_id: int,
    keep: ExtraField,
    duplicate: ExtraField,
) -> None:
    """Best-effort merge of FieldPref rows pointing at a duplicate field."""

    def _get_pref(field_name: str) -> FieldPref | None:
        return (
            s.query(FieldPref)
            .filter(FieldPref.company_id == company_id, FieldPref.field == field_name)
            .first()
        )

    dup_prefs: list[FieldPref] = (
        s.query(FieldPref)
        .filter(FieldPref.company_id == company_id, FieldPref.field == duplicate.name)
        .all()
    )
    if not dup_prefs:
        return

    keep_pref = _get_pref(keep.name)
    for pref in dup_prefs:
        if keep_pref is None:
            pref.field = keep.name
            keep_pref = pref
            continue
        # Merge text metadata
        if not keep_pref.alias and pref.alias:
            keep_pref.alias = pref.alias
        if (not keep_pref.group or keep_pref.group == "none") and pref.group and pref.group != "none":
            keep_pref.group = pref.group
        # Merge boolean/int flags
        if getattr(pref, "exempt_enabled", False) and not getattr(keep_pref, "exempt_enabled", False):
            keep_pref.exempt_enabled = True
        if getattr(pref, "exempt_limit", 0) and not getattr(keep_pref, "exempt_limit", 0):
            keep_pref.exempt_limit = pref.exempt_limit
        if getattr(pref, "ins_nhis", False) and not getattr(keep_pref, "ins_nhis", False):
            keep_pref.ins_nhis = True
        if getattr(pref, "ins_ei", False) and not getattr(keep_pref, "ins_ei", False):
            keep_pref.ins_ei = True
        s.delete(pref)
