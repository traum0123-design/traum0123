from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Create Alembic autogenerate migration")
    parser.add_argument("-m", "--message", required=True, help="Migration message")
    args = parser.parse_args()

    # Ensure alembic.ini exists in project root
    root = Path(__file__).resolve().parents[1]
    ini = root / "alembic.ini"
    if not ini.exists():
        print("alembic.ini not found at project root", file=sys.stderr)
        return 2

    cmd = ["alembic", "revision", "--autogenerate", "-m", args.message]
    print("$", " ".join(cmd))
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())

