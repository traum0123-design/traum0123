from __future__ import annotations

import pytest
from decimal import Decimal

hypothesis = pytest.importorskip("hypothesis")
st = pytest.importorskip("hypothesis.strategies")

from core.services.calculation import _round_amount


@hypothesis.given(
    amount=st.decimals(min_value=0, max_value=1_000_000, places=2),
    step=st.integers(min_value=1, max_value=1000),
)
def test_rounding_floor_leq_original(amount, step):
    d = Decimal(amount)
    out = _round_amount(d, step, "floor")
    assert out <= int((d // Decimal(step)) * Decimal(step) + (Decimal(0)))


@hypothesis.given(
    amount=st.decimals(min_value=0, max_value=1_000_000, places=2),
    step=st.integers(min_value=1, max_value=1000),
)
def test_rounding_ceil_geq_original(amount, step):
    d = Decimal(amount)
    out = _round_amount(d, step, "ceil")
    # Ceil result should be >= amount
    assert out >= int(d)

