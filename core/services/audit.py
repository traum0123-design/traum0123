from __future__ import annotations

import json
import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from core.models import AuditEvent

logger = logging.getLogger("payroll_core.audit")


def record_event(
    db: Session,
    *,
    actor: str,
    action: str,
    resource: str = "",
    company_id: Optional[int] = None,
    ip: str = "",
    ua: str = "",
    result: str = "ok",
    meta: Optional[dict[str, Any]] = None,
) -> None:
    """Persist an audit event with best-effort durability.

    Important: Do not rely on the caller's DB transaction being committed.
    To ensure the audit trail is not lost when the outer transaction does
    not commit (e.g., redirects, early returns), this function writes using
    an independent short‑lived session and commits immediately. If that
    fails, fall back to structured application logs.
    """
    payload = {
        "actor": str(actor or "unknown")[:120],
        "action": str(action or "event")[:80],
        "resource": str(resource or "")[:255],
        "company_id": company_id,
        "ip": str(ip or "")[:64],
        "ua": str(ua or "")[:255],
        "result": str(result or "ok")[:40],
        "meta_json": json.dumps(meta or {}, ensure_ascii=False),
    }
    try:
        # Prefer an independent session so we can commit without affecting caller state
        try:
            from core.db import get_sessionmaker  # lazy import to avoid cycles
            SessionLocal = get_sessionmaker()
            s = SessionLocal()
            try:
                evt = AuditEvent(**payload)
                s.add(evt)
                s.commit()
            except Exception:
                s.rollback()
                raise
            finally:
                s.close()
        except Exception:
            # Fallback: attempt to use the provided session (may not be committed by caller)
            evt = AuditEvent(**payload)
            db.add(evt)
            db.flush()
    except Exception:
        # Last resort: emit as an application log so the signal is not lost entirely
        try:
            logger.info(
                "audit_fallback",
                extra={
                    "event": payload["action"],
                    "actor": payload["actor"],
                    "company_id": payload["company_id"],
                    "resource": payload["resource"],
                    "ip": payload["ip"],
                    "ua": payload["ua"],
                    "result": payload["result"],
                    "meta": meta or {},
                },
            )
        except Exception:
            pass
