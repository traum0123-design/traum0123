from __future__ import annotations

import unicodedata
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.fields import cleanup_duplicate_extra_fields
from core.locks import company_extra_field_lock
from core.models import Company, ExtraField
from core.repositories import extra_fields as extra_fields_repo


def normalize_label(label: str) -> str:
    s = unicodedata.normalize("NFKC", str(label or ""))
    s = s.replace("\u00A0", " ").replace("\u3000", " ")
    s = s.replace("\u200b", "").replace("\u200c", "").replace("\u200d", "")
    return " ".join(s.strip().split())


def ensure_defaults(session: Session, company: Company) -> None:
    cleanup_duplicate_extra_fields(session, company)


def add_extra_field(
    session: Session,
    company: Company,
    label: str,
    typ: str = "number",
) -> Optional[ExtraField]:
    norm_label = normalize_label(label)
    if not norm_label:
        raise ValueError("라벨이 필요합니다.")

    with company_extra_field_lock(company.id, norm_label) as acquired:
        # Even if we could not acquire the lock, we try optimistic path
        existing = extra_fields_repo.find_by_label(session, company.id, norm_label)
        if existing:
            return existing

        key = norm_label
        suffix = 1
        while extra_fields_repo.find_by_name(session, company.id, key):
            suffix += 1
            key = f"{norm_label}_{suffix}"

        field = ExtraField(
            company_id=company.id,
            name=key,
            label=norm_label,
            typ=typ,
        )
        try:
            extra_fields_repo.add(session, field)
            session.commit()
        except IntegrityError:
            session.rollback()
            # Rerun cleanup in case of race and fetch existing
            cleanup_duplicate_extra_fields(session, company)
            field = extra_fields_repo.find_by_label(session, company.id, norm_label)
        return field
