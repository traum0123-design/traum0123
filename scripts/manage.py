from __future__ import annotations

import argparse
import subprocess
import sys
from typing import Optional

from sqlalchemy import text

from core.db import init_database, session_scope
from core.models import Company, ExtraField, FieldPref, MonthlyPayroll, MonthlyPayrollRow, WithholdingCell, IdempotencyRecord, RevokedToken
from core.services import companies as company_service
from core.services.auth import issue_admin_token, issue_company_token


def _run(cmd: list[str]) -> int:
    print("$", " ".join(cmd))
    return subprocess.call(cmd)


def cmd_migrate(_: argparse.Namespace) -> int:
    return _run(["alembic", "upgrade", "head"])


def cmd_downgrade(args: argparse.Namespace) -> int:
    target = args.to or "base"
    return _run(["alembic", "downgrade", target])


def cmd_seed_demo(_: argparse.Namespace) -> int:
    from scripts import dev_seed

    dev_seed.main()
    return 0


def cmd_db_check(_: argparse.Namespace) -> int:
    engine = init_database()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("DB OK")
    return 0


def cmd_create_company(args: argparse.Namespace) -> int:
    name = args.name
    slug = args.slug
    if not name or not slug:
        print("--name and --slug are required", file=sys.stderr)
        return 2
    with session_scope() as session:
        company, code = company_service.create_company(session, name, slug)
        print(f"Created company: id={company.id} slug={company.slug}")
        print(f"Portal access code: {code}")
    return 0


def cmd_impersonate_token(args: argparse.Namespace) -> int:
    company_id: int | None = args.company_id
    slug: str | None = args.slug
    with session_scope() as session:
        comp: Company | None = None
        if company_id:
            comp = session.get(Company, company_id)
        elif slug:
            comp = session.query(Company).filter(Company.slug == slug).first()
        if not comp:
            print("Company not found", file=sys.stderr)
            return 1
        tok = issue_company_token(session, comp, is_admin=True)
        print(tok)
    return 0


def cmd_admin_token(_: argparse.Namespace) -> int:
    print(issue_admin_token())
    return 0


def cmd_revoke_admin_token(args: argparse.Namespace) -> int:
    token = args.token
    if not token:
        print("--token is required", file=sys.stderr)
        return 2
    from core.settings import get_settings
    from core.auth import verify_admin_token
    payload = verify_admin_token(get_settings().secret_key, token)
    if not payload:
        print("Invalid token", file=sys.stderr)
        return 1
    jti = str(payload.get("jti") or "")
    if not jti:
        print("Token missing jti", file=sys.stderr)
        return 1
    with session_scope() as session:
        if session.query(RevokedToken).filter(RevokedToken.typ == "admin", RevokedToken.jti == jti).first():
            print("Already revoked")
            return 0
        rec = RevokedToken(typ="admin", jti=jti)
        session.add(rec)
        session.commit()
        print("Revoked admin token")
    return 0


def cmd_revoke_admin_all(_: argparse.Namespace) -> int:
    import time
    from core.models import TokenFence
    with session_scope() as session:
        fence = session.query(TokenFence).filter(TokenFence.typ == "admin").first()
        now = int(time.time())
        if not fence:
            fence = TokenFence(typ="admin", revoked_before_iat=now)
            session.add(fence)
        else:
            fence.revoked_before_iat = now
        session.commit()
        print("Revoked all admin tokens issued at/before:", now)
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    import json
    import urllib.request

    host = args.host or "127.0.0.1"
    port = args.port or 8000
    url = f"http://{host}:{port}/api/healthz"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:  # nosec - local
            ok = resp.getcode() == 200 and json.loads(resp.read().decode("utf-8")).get("ok")
            print("HEALTH:", "OK" if ok else "FAIL", url)
            return 0 if ok else 1
    except Exception as e:
        print("HEALTH: ERROR", e)
        return 1


def cmd_stats(_: argparse.Namespace) -> int:
    init_database()
    with session_scope() as session:
        stats = {
            "companies": session.query(Company).count(),
            "monthly_payrolls": session.query(MonthlyPayroll).count(),
            "monthly_payroll_rows": session.query(MonthlyPayrollRow).count(),
            "extra_fields": session.query(ExtraField).count(),
            "field_prefs": session.query(FieldPref).count(),
            "withholding_cells": session.query(WithholdingCell).count(),
        }
        for k, v in stats.items():
            print(f"{k}: {v}")
    return 0


def cmd_list_companies(_: argparse.Namespace) -> int:
    init_database()
    with session_scope() as session:
        rows = session.query(Company).order_by(Company.created_at.desc()).all()
        for c in rows:
            print(f"{c.id}\t{c.slug}\t{c.name}\t{c.created_at}")
    return 0


def cmd_prune_idempotency(args: argparse.Namespace) -> int:
    days = int(args.days)
    import datetime as dt
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    with session_scope() as session:
        try:
            n = (
                session.query(IdempotencyRecord)
                .filter(IdempotencyRecord.created_at < cutoff)
                .delete(synchronize_session=False)
            )
            session.commit()
            print(f"Pruned {n} idempotency records older than {days}d")
        except Exception as e:
            print("Error pruning:", e, file=sys.stderr)
            return 1
    return 0


def cmd_rotate_company_token_key(args: argparse.Namespace) -> int:
    ident = args.company_id
    if ident is None and not args.slug:
        print("--company-id or --slug required", file=sys.stderr)
        return 2
    with session_scope() as session:
        comp: Company | None = None
        if ident is not None:
            comp = session.get(Company, int(ident))
        else:
            comp = session.query(Company).filter(Company.slug == args.slug).first()
        if not comp:
            print("Company not found", file=sys.stderr)
            return 1
        company_service.rotate_company_token_key(session, comp)
        print(f"Rotated token key for company id={comp.id} slug={comp.slug}")
    return 0


def cmd_rotate_company_access(args: argparse.Namespace) -> int:
    ident = args.company_id
    if ident is None and not args.slug:
        print("--company-id or --slug required", file=sys.stderr)
        return 2
    with session_scope() as session:
        comp: Company | None = None
        if ident is not None:
            comp = session.get(Company, int(ident))
        else:
            comp = session.query(Company).filter(Company.slug == args.slug).first()
        if not comp:
            print("Company not found", file=sys.stderr)
            return 1
        code = company_service.rotate_company_access(session, comp)
        print(f"New access code: {code}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="manage", description="Dev management CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("migrate", help="Upgrade DB to head").set_defaults(func=cmd_migrate)

    p_down = sub.add_parser("downgrade", help="Downgrade DB to target (default base)")
    p_down.add_argument("to", nargs="?", default="base")
    p_down.set_defaults(func=cmd_downgrade)

    sub.add_parser("seed-demo", help="Create demo company and print access code").set_defaults(func=cmd_seed_demo)

    sub.add_parser("db-check", help="Run a simple DB connectivity check").set_defaults(func=cmd_db_check)

    p_new = sub.add_parser("create-company", help="Create a company and print access code")
    p_new.add_argument("--name", required=True)
    p_new.add_argument("--slug", required=True)
    p_new.set_defaults(func=cmd_create_company)

    p_imp = sub.add_parser("impersonate-token", help="Issue admin-impersonation portal token for a company")
    p_imp.add_argument("--company-id", type=int)
    p_imp.add_argument("--slug")
    p_imp.set_defaults(func=cmd_impersonate_token)

    sub.add_parser("admin-token", help="Issue an admin token").set_defaults(func=cmd_admin_token)
    p_rev = sub.add_parser("revoke-admin-token", help="Revoke a specific admin token (by token string)")
    p_rev.add_argument("--token", required=True)
    p_rev.set_defaults(func=cmd_revoke_admin_token)
    sub.add_parser("revoke-admin-all", help="Revoke all admin tokens (fence by iat)").set_defaults(func=cmd_revoke_admin_all)

    p_health = sub.add_parser("health", help="Call /api/healthz on host:port")
    p_health.add_argument("--host", default="127.0.0.1")
    p_health.add_argument("--port", type=int, default=8000)
    p_health.set_defaults(func=cmd_health)

    sub.add_parser("stats", help="Print table counts").set_defaults(func=cmd_stats)
    sub.add_parser("list-companies", help="List companies").set_defaults(func=cmd_list_companies)
    p_prune = sub.add_parser("prune-idempotency", help="Delete idempotency records older than N days")
    p_prune.add_argument("--days", type=int, default=7)
    p_prune.set_defaults(func=cmd_prune_idempotency)

    p_rot_tok = sub.add_parser("rotate-company-token-key", help="Rotate company token key (revoke tokens)")
    p_rot_tok.add_argument("--company-id", type=int)
    p_rot_tok.add_argument("--slug")
    p_rot_tok.set_defaults(func=cmd_rotate_company_token_key)

    p_rot_acc = sub.add_parser("rotate-company-access", help="Rotate company portal access code")
    p_rot_acc.add_argument("--company-id", type=int)
    p_rot_acc.add_argument("--slug")
    p_rot_acc.set_defaults(func=cmd_rotate_company_access)

    # Utilities
    try:
        from cryptography.fernet import Fernet  # type: ignore

        def cmd_gen_pii_key(_: argparse.Namespace) -> int:
            print(Fernet.generate_key().decode())
            return 0

        sub.add_parser("gen-pii-key", help="Generate a Fernet key for PII_ENC_KEY").set_defaults(func=cmd_gen_pii_key)
    except Exception:
        pass

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
