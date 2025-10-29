from __future__ import annotations

import os
from typing import Optional, List


def _get_fernets() -> List["Fernet"]:
    """Return a list of Fernet instances from PII_ENC_KEYS (comma-separated) or PII_ENC_KEY.

    First item is used for encryption; all are tried for decryption.
    """
    keys_raw = (os.environ.get("PII_ENC_KEYS") or "").strip()
    if not keys_raw:
        single = (os.environ.get("PII_ENC_KEY") or "").strip()
        keys = [single] if single else []
    else:
        keys = [k.strip() for k in keys_raw.split(',') if k.strip()]
    if not keys:
        return []
    try:
        from cryptography.fernet import Fernet  # type: ignore
    except Exception:
        return []
    out: List["Fernet"] = []
    for k in keys:
        try:
            out.append(Fernet(k))
        except Exception:
            continue
    return out


def encrypt_ssn(value: str) -> str:
    """Encrypt SSN when cryptography+PII_ENC_KEY available; otherwise return masked.

    Uses Fernet (AES128 in CBC + HMAC under the hood) with a base64 urlsafe key.
    Stored format: 'enc:<token>' to distinguish from masked/plain.
    """
    s = (value or "").strip()
    if not s:
        return ""
    f_list = _get_fernets()
    if not f_list:
        return mask_ssn(s)
    try:
        tok = f_list[0].encrypt(s.encode("utf-8")).decode("utf-8")
        return f"enc:{tok}"
    except Exception:
        return mask_ssn(s)


def decrypt_ssn(value: str) -> str:
    """Decrypt previously encrypted SSN. Returns empty string if not decryptable."""
    s = (value or "").strip()
    if not s:
        return ""
    if not s.startswith("enc:"):
        return s
    f_list = _get_fernets()
    if not f_list:
        return ""
    tok = s[4:]
    for f in f_list:
        try:
            return f.decrypt(tok.encode("utf-8")).decode("utf-8")
        except Exception:
            continue
    return ""


def mask_ssn(ssn: str) -> str:
    digits = "".join([c for c in ssn if c.isdigit()])
    if len(digits) >= 4:
        return f"***-**-{digits[-4:]}"
    return ""
