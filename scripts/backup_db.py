from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime
from pathlib import Path


def is_sqlite(url: str) -> bool:
    return url.startswith("sqlite:///")


def sqlite_path(url: str) -> Path:
    # sqlite:////absolute/path or sqlite:///relative.db
    path = url.replace("sqlite:///", "", 1)
    return Path(path)


def backup_sqlite(db_path: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    dest = out_dir / f"app_{ts}.db"
    shutil.copy2(str(db_path), str(dest))
    return dest


def main() -> int:
    url = os.environ.get("DATABASE_URL") or ""
    if not url:
        print("DATABASE_URL not set", file=sys.stderr)
        return 2
    if is_sqlite(url):
        dbp = sqlite_path(url)
        if not dbp.exists():
            print(f"SQLite DB not found: {dbp}", file=sys.stderr)
            return 1
        out = backup_sqlite(dbp, Path("backups"))
        print(f"SQLite backup created: {out}")
        return 0
    else:
        # For Postgres/MySQL, recommend using native dump tools
        print("Non-SQLite database detected. Use pg_dump or mysqldump.")
        print("Example: pg_dump --no-owner --format=custom $DATABASE_URL > backups/backup.dump")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

