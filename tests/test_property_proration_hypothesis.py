from __future__ import annotations

import pytest

hypothesis = pytest.importorskip("hypothesis")
st = pytest.importorskip("hypothesis.strategies")

from core.services.calculation import proration_factor_for_month
import datetime as dt


@hypothesis.given(
    year=st.integers(min_value=2000, max_value=2100),
    month=st.integers(min_value=1, max_value=12),
    join_day=st.integers(min_value=1, max_value=28),
    leave_day=st.integers(min_value=1, max_value=28),
)
def test_proration_properties(year: int, month: int, join_day: int, leave_day: int):
    if join_day > leave_day:
        join_day, leave_day = leave_day, join_day
    ms = dt.date(year, month, 1)
    # pick an upper bound day safely (28)
    me = dt.date(year, month, 28)
    row = {
        "입사일": f"{year}-{month:02d}-{join_day:02d}",
        "퇴사일": f"{year}-{month:02d}-{leave_day:02d}",
        "월 시작일": str(ms),
        "월 말일": str(me),
    }
    d, t = proration_factor_for_month(row, year=year, month=month)
    assert 0 <= d <= t <= 31
    # If join and leave cover the entire range, days should equal total when no leave periods
    if join_day == 1 and leave_day == 28:
        assert d == t

