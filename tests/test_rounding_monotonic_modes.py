from __future__ import annotations

import pytest
from decimal import Decimal

hypothesis = pytest.importorskip("hypothesis")
st = pytest.importorskip("hypothesis.strategies")

from core.services.calculation import _round_amount


@hypothesis.given(
    a=st.decimals(min_value=0, max_value=1_000_000, places=2),
    b=st.decimals(min_value=0, max_value=1_000_000, places=2),
    step=st.integers(min_value=1, max_value=1000),
)
def test_round_amount_monotonic_all_modes(a, b, step):
    x = Decimal(a)
    y = Decimal(b)
    if x > y:
        x, y = y, x
    modes = ["floor", "ceil", "half_down", "round"]
    for m in modes:
        rx = _round_amount(x, step, m)
        ry = _round_amount(y, step, m)
        assert rx <= ry

