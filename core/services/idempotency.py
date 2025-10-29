from __future__ import annotations

import hashlib
import json
from typing import Callable, Optional, Tuple

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from core.models import IdempotencyRecord


def compute_body_hash(obj) -> str:
    """Compute a stable SHA256 hex hash for the given payload-like object.

    Accepts dict/list/str/bytes and normalizes JSON to a canonical form for stability.
    """
    if obj is None:
        data = b"null"
    elif isinstance(obj, (bytes, bytearray)):
        data = bytes(obj)
    elif isinstance(obj, str):
        data = obj.encode("utf-8")
    else:
        # Canonical JSON: sorted keys, compact separators, UTF-8
        try:
            dumped = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except Exception:
            dumped = str(obj)
        data = dumped.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def maybe_idempotent_json(
    db: Session,
    request: Request,
    *,
    company_id: Optional[int],
    body_hash: str,
    produce: Callable[[], Tuple[dict, int]],
):
    """If Idempotency-Key provided, ensure at-most-once semantics and return stored response on replay.

    - On first request: run producer, persist response, and return it.
    - On replay with same key and different body: raise 409 conflict.
    - On replay with same key and same body: return stored response.
    """
    key = request.headers.get("Idempotency-Key") or request.headers.get("IdempotencyKey")
    method = (request.method or "").upper()
    path = request.url.path
    if not key:
        content, status = produce()
        return content, status

    # Try existing
    existing = (
        db.query(IdempotencyRecord)
        .filter(
            IdempotencyRecord.key == key,
            IdempotencyRecord.method == method,
            IdempotencyRecord.path == path,
        )
        .first()
    )
    if existing:
        if existing.body_hash != body_hash:
            raise HTTPException(status_code=409, detail="idempotency key conflict")
        try:
            content = json.loads(existing.response_json or "{}")
        except Exception:
            content = {"ok": True}
        return content, int(existing.status_code or 200)

    # First-time key: run and persist response
    content, status = produce()
    rec = IdempotencyRecord(
        key=key,
        method=method,
        path=path,
        body_hash=body_hash,
        company_id=company_id,
        status_code=int(status or 200),
        response_json=json.dumps(content, ensure_ascii=False),
    )
    db.add(rec)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Fetch and reconcile
        again = (
            db.query(IdempotencyRecord)
            .filter(
                IdempotencyRecord.key == key,
                IdempotencyRecord.method == method,
                IdempotencyRecord.path == path,
            )
            .first()
        )
        if again and again.body_hash == body_hash:
            try:
                stored = json.loads(again.response_json or "{}")
            except Exception:
                stored = {"ok": True}
            return stored, int(again.status_code or 200)
        raise HTTPException(status_code=409, detail="idempotency key conflict")

    return content, status

