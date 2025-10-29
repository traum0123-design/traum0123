from __future__ import annotations

import sys
from core.db import get_engine
from core.alembic_utils import ensure_up_to_date


def main() -> int:
    try:
        engine = get_engine()
        ensure_up_to_date(engine)
        print("Alembic status: OK (DB at head)")
        return 0
    except Exception as e:
        print(f"Alembic status: FAIL ({e})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

