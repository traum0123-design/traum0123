from __future__ import annotations

import argparse
import subprocess
import sys
from typing import Optional

from sqlalchemy import text

from core.db import init_database, session_scope
from core.models import Company
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
    company_id: Optional[int] = args.company_id
    slug: Optional[str] = args.slug
    with session_scope() as session:
        comp: Optional[Company] = None
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

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

