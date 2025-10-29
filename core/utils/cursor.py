from __future__ import annotations

import base64
import json
from typing import Any, Optional


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64url_decode(data: str) -> bytes:
    s = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(s.encode())


def encode_cursor(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode()
    return _b64url_encode(body)


def decode_cursor(token: str) -> dict[str, Any]:
    try:
        body = _b64url_decode(token)
        return json.loads(body.decode())
    except Exception as e:
        raise ValueError("invalid cursor") from e

