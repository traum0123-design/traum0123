from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Optional, Tuple

from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash, generate_password_hash

from core.models import Company
from core.repositories import companies as companies_repo
from core.settings import get_settings


def _parse_werkzeug_hash(expected: str) -> Tuple[str, list[str], str, bytes] | None:
    """Parse Werkzeug-style password hashes.

    Format: "<method[:args...]>$<salt>$<hexhash>"
    Supported methods: scrypt, pbkdf2.
    """
    try:
        method_part, salt, hash_hex = expected.split("$", 2)
    except ValueError:
        return None
    method_bits = method_part.split(":")
    if not method_bits:
        return None
    method = method_bits[0].strip().lower()
    args = [b.strip() for b in method_bits[1:]]
    if method not in {"scrypt", "pbkdf2"}:
        return None
    try:
        digest = bytes.fromhex(hash_hex)
    except ValueError:
        return None
    return method, args, salt, digest


def _verify_scrypt(args: list[str], salt: str, digest: bytes, candidate: str) -> bool:
    try:
        n = int(args[0]) if len(args) > 0 else 32768
        r = int(args[1]) if len(args) > 1 else 8
        p = int(args[2]) if len(args) > 2 else 1
    except Exception:
        return False
    # OpenSSL may enforce a low default memory cap. Pre-compute needed mem and
    # set maxmem comfortably above it.
    needed = 128 * r * n
    maxmem = max(needed * 2, 1024 * 1024 * 1024)  # >=1GB, avoids "memory limit exceeded"
    try:
        dk = hashlib.scrypt(
            candidate.encode("utf-8"),
            salt=salt.encode("utf-8"),
            n=n,
            r=r,
            p=p,
            dklen=len(digest),
            maxmem=maxmem,
        )
    except Exception:
        return False
    return hmac.compare_digest(dk, digest)


def _verify_pbkdf2(args: list[str], salt: str, digest: bytes, candidate: str) -> bool:
    # args: [hash_name, iterations] (Werkzeug default pbkdf2:sha256:260000)
    hash_name = (args[0] if len(args) > 0 else "sha256").lower()
    try:
        iterations = int(args[1]) if len(args) > 1 else 260000
    except Exception:
        iterations = 260000
    try:
        dk = hashlib.pbkdf2_hmac(
            hash_name,
            candidate.encode("utf-8"),
            salt.encode("utf-8"),
            iterations,
            dklen=len(digest),
        )
    except Exception:
        return False
    return hmac.compare_digest(dk, digest)


def _check_password_compat(expected: str, candidate: str) -> bool:
    """Verify candidate against expected hash or plain password.

    If expected looks like a supported Werkzeug hash, try Werkzeug first and
    fall back to a manual implementation that avoids low scrypt memory caps.
    Otherwise treat expected as plain text.
    """
    parsed = _parse_werkzeug_hash(expected)
    if parsed:
        method, args, salt, digest = parsed
        try:
            return check_password_hash(expected, candidate)
        except Exception:
            if method == "scrypt":
                return _verify_scrypt(args, salt, digest, candidate)
            if method == "pbkdf2":
                return _verify_pbkdf2(args, salt, digest, candidate)
            return False
    # Not a recognized hash -> plain comparison
    return secrets.compare_digest(candidate, expected)


def verify_admin_password(password: str) -> bool:
    candidate = (password or "").strip()
    expected = (get_settings().admin_password or "").strip()
    if not expected or not candidate:
        return False
    return _check_password_compat(expected, candidate)


def validate_company_access(session: Session, company: Company, access_code: str) -> bool:
    expected = (company.access_hash or "").strip()
    candidate = (access_code or "").strip()
    if not expected or not candidate:
        return False
    return _check_password_compat(expected, candidate)


def create_company(session: Session, name: str, slug: str) -> tuple[Company, str]:
    slug = slug.strip().lower()
    company = Company(name=name.strip(), slug=slug, access_hash="")
    session.add(company)
    session.flush()
    code = rotate_company_access(session, company)
    return company, code


def rotate_company_access(session: Session, company: Company) -> str:
    code = secrets.token_hex(4)
    company.access_hash = generate_password_hash(code)
    # Also rotate the token_key so existing tokens are invalidated as a safety net
    company.token_key = secrets.token_hex(16)
    session.commit()
    return code


def ensure_token_key(session: Session, company: Company) -> None:
    if company.token_key and company.token_key.strip():
        return
    company.token_key = secrets.token_hex(16)
    session.commit()

def rotate_company_token_key(session: Session, company: Company) -> str:
    """Rotate company's token key to immediately revoke existing tokens.

    Returns the new key (not exposed to clients; only for internal auditing/tests).
    """
    company.token_key = secrets.token_hex(16)
    session.commit()
    return company.token_key


def find_company_by_slug(session: Session, slug: str) -> Company | None:
    return companies_repo.get_by_slug(session, slug)


def find_company_by_id(session: Session, company_id: int) -> Company | None:
    return companies_repo.get_by_id(session, company_id)
