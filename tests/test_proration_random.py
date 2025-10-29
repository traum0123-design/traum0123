from __future__ import annotations

import random
import datetime as dt

from core.services.calculation import proration_factor_for_month


def test_proration_random_sanity():
    random.seed(42)
    year, month = 2025, 10
    for _ in range(100):
        ms = dt.date(year, month, 1)
        me = dt.date(year, month, 31)
        join_day = random.randint(1, 31)
        leave_day = random.randint(1, 31)
        if join_day > leave_day:
            join_day, leave_day = leave_day, join_day
        row = {
            "입사일": f"{year}-{month:02d}-{join_day:02d}",
            "퇴사일": f"{year}-{month:02d}-{leave_day:02d}",
            "월 시작일": str(ms),
            "월 말일": str(me),
        }
        d, t = proration_factor_for_month(row, year=year, month=month)
        assert 0 <= d <= t <= 31

