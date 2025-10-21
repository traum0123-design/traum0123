from __future__ import annotations

import datetime as dt
import re
from typing import Optional


def parse_date_flex(value) -> Optional[dt.date]:
    """Best-effort date parser shared across importer/exporter/UI."""

    if not value:
        return None
    if isinstance(value, dt.date):
        return value
    s = str(value).strip()
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s)
    except Exception:
        pass
    parts = [p for p in re.split(r"[^0-9]", s) if p]
    if len(parts) >= 3:
        try:
            y, m, d = map(int, parts[:3])
            return dt.date(y, m, d)
        except Exception:
            return None
    return None

