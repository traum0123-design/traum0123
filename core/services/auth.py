from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from core.auth import make_admin_token, make_company_token, verify_admin_token, verify_company_token
from core.models import Company
from core.repositories import companies as companies_repo
from core.settings import get_settings


def extract_token(
    authorization: str | None,
    header_token: str | None,
    query_token: str | None,
    cookie_token: str | None = None,
) -> str | None:
    """Normalize token retrieval across headers/query params."""

    if cookie_token:
        token = str(cookie_token).strip()
        if token:
            return token
    if query_token:
        token = str(query_token).strip()
        if token:
            return token
    if header_token:
        token = str(header_token).strip()
        if token:
            return token
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if token:
            return token
    return None


def authenticate_company(session: Session, slug: str | None, token: str) -> Company | None:
    secret = get_settings().secret_key
    payload = verify_company_token(secret, token)
    if not payload:
        return None
    payload_slug = str(payload.get("slug") or "")
    desired_slug = str(slug) if slug else payload_slug
    if desired_slug and payload_slug and payload_slug != desired_slug:
        return None
    if not desired_slug:
        return None
    company = companies_repo.get_by_slug(session, desired_slug)
    if not company:
        return None
    if int(payload.get("cid", 0)) != int(company.id):
        return None
    token_key = (company.token_key or "").strip()
    payload_key = str(payload.get("key") or "").strip()
    if token_key and token_key != payload_key:
        return None
    return company


def issue_company_token(session: Session, company: Company, *, ttl_seconds: int | None = None, is_admin: bool = False, ensure_key: bool = True, roles: list[str] | None = None) -> str:
    from core.services import companies as company_service  # local import to avoid circular import

    if ensure_key:
        company_service.ensure_token_key(session, company)
        session.refresh(company)
    secret = get_settings().secret_key
    ttl = ttl_seconds if ttl_seconds is not None else int(getattr(get_settings(), "company_token_ttl", 7200) or 7200)
    key = (company.token_key or "").strip() if ensure_key else None
    eff_roles = roles if roles is not None else (["admin"] if is_admin else ["payroll_manager"])
    return make_company_token(secret, company.id, company.slug, is_admin=is_admin, ttl_seconds=ttl, key=key, roles=eff_roles)


def authenticate_admin(token: str) -> bool:
    secret = get_settings().secret_key
    payload = verify_admin_token(secret, token)
    if not payload:
        return False
    # Optional revoke list check (best-effort)
    try:
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import create_engine
        from core.settings import get_settings as _gs
        from core.models import RevokedToken, TokenFence
        engine = create_engine(_gs().database_url, future=True)
        with sessionmaker(bind=engine, future=True)() as s:  # type: ignore[call-arg]
            jti = str(payload.get("jti") or "")
            iat = int(payload.get("iat") or 0)
            fence = s.query(TokenFence).filter(TokenFence.typ == "admin").first()
            if fence and iat and iat <= int(fence.revoked_before_iat or 0):
                return False
            if jti and s.query(RevokedToken).filter(RevokedToken.typ == "admin", RevokedToken.jti == jti).first():
                return False
    except Exception:
        pass
    return True


def issue_admin_token(*, ttl_seconds: int | None = None) -> str:
    secret = get_settings().secret_key
    ttl = ttl_seconds if ttl_seconds is not None else int(getattr(get_settings(), "admin_token_ttl", 7200) or 7200)
    return make_admin_token(secret, ttl_seconds=ttl, roles=["admin"])


def token_roles(token: str, *, is_admin: bool = False) -> list[str]:
    secret = get_settings().secret_key
    payload = verify_admin_token(secret, token) if is_admin else verify_company_token(secret, token)
    if not payload:
        return []
    roles = payload.get("roles") or []
    try:
        return [str(r) for r in roles]
    except Exception:
        return []
