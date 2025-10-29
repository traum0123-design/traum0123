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
    try:
        evt = AuditEvent(
            actor=str(actor or "unknown")[:120],
            action=str(action or "event")[:80],
            resource=str(resource or "")[:255],
            company_id=company_id,
            ip=str(ip or "")[:64],
            ua=str(ua or "")[:255],
            result=str(result or "ok")[:40],
            meta_json=json.dumps(meta or {}, ensure_ascii=False),
        )
        db.add(evt)
        # Let caller decide transaction scope; best-effort flush
        db.flush()
    except Exception:
        try:
            logger.info(
                "audit_fallback",
                extra={
                    "event": action,
                    "actor": actor,
                    "company_id": company_id,
                    "resource": resource,
                    "ip": ip,
                    "ua": ua,
                    "result": result,
                    "meta": meta or {},
                },
            )
        except Exception:
            pass

