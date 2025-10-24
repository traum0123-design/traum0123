from __future__ import annotations

import base64
import hmac
import json
import time
from hashlib import sha256
from typing import Any, Optional


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip('=')


def _b64url_decode(data: str) -> bytes:
    s = data + '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode(s.encode())


def make_company_token(secret: str, company_id: int, slug: str, *, is_admin: bool = False, ttl_seconds: int = 2 * 60 * 60, key: str | None = None) -> str:
    now = int(time.time())
    payload = {
        "cid": int(company_id),
        "slug": str(slug),
        "adm": bool(is_admin),
        "iat": now,
        "exp": now + int(ttl_seconds),
        "typ": "company",
        "ver": 1,
    }
    if key:
        payload["key"] = str(key)
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    sig = hmac.new(secret.encode(), body, sha256).digest()
    return f"{_b64url(body)}.{_b64url(sig)}"


def verify_company_token(secret: str, token: str) -> dict[str, Any] | None:
    try:
        part_body, part_sig = token.split('.')
    except ValueError:
        return None
    try:
        body = _b64url_decode(part_body)
        got_sig = _b64url_decode(part_sig)
    except Exception:
        return None
    exp_sig = hmac.new(secret.encode(), body, sha256).digest()
    if not hmac.compare_digest(exp_sig, got_sig):
        return None
    try:
        payload = json.loads(body.decode())
    except Exception:
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    if payload.get("typ") != "company":
        return None
    if int(payload.get("ver", 0)) != 1:
        return None
    return payload


def make_admin_token(secret: str, *, ttl_seconds: int = 2 * 60 * 60) -> str:
    now = int(time.time())
    payload = {
        "typ": "admin",
        "iat": now,
        "exp": now + int(ttl_seconds),
        "ver": 1,
    }
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    sig = hmac.new(secret.encode(), body, sha256).digest()
    return f"{_b64url(body)}.{_b64url(sig)}"


def verify_admin_token(secret: str, token: str) -> dict[str, Any] | None:
    try:
        part_body, part_sig = token.split('.')
    except ValueError:
        return None
    try:
        body = _b64url_decode(part_body)
        got_sig = _b64url_decode(part_sig)
    except Exception:
        return None
    exp_sig = hmac.new(secret.encode(), body, sha256).digest()
    if not hmac.compare_digest(exp_sig, got_sig):
        return None
    try:
        payload = json.loads(body.decode())
    except Exception:
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    if payload.get("typ") != "admin":
        return None
    if int(payload.get("ver", 0)) != 1:
        return None
    return payload
