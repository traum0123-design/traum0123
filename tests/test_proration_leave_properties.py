from __future__ import annotations

import pytest
import datetime as dt

hypothesis = pytest.importorskip("hypothesis")
st = pytest.importorskip("hypothesis.strategies")

from core.services.calculation import proration_factor_for_month


@hypothesis.given(
    year=st.integers(min_value=2000, max_value=2100),
    month=st.integers(min_value=1, max_value=12),
    j=st.integers(min_value=1, max_value=28),
    l=st.integers(min_value=1, max_value=28),
    s=st.integers(min_value=1, max_value=28),
    e=st.integers(min_value=1, max_value=28),
)
def test_proration_with_leave_never_exceeds_total(year, month, j, l, s, e):
    # Normalize orders
    if j > l:
      j, l = l, j
    if s > e:
      s, e = e, s
    ms = dt.date(year, month, 1)
    me = dt.date(year, month, 28)
    row = {
      "입사일": f"{year}-{month:02d}-{j:02d}",
      "퇴사일": f"{year}-{month:02d}-{l:02d}",
      "휴직일": f"{year}-{month:02d}-{s:02d}",
      "휴직종료일": f"{year}-{month:02d}-{e:02d}",
      "월 시작일": str(ms),
      "월 말일": str(me),
    }
    d, t = proration_factor_for_month(row, year=year, month=month)
    assert 0 <= d <= t <= 31

