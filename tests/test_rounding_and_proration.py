from __future__ import annotations

from decimal import Decimal

from core.services.calculation import _round_amount, proration_factor_for_month


def test_round_amount_half_up_step10():
    assert _round_amount(Decimal("14"), 10, "round") == 10
    assert _round_amount(Decimal("15"), 10, "round") == 20
    assert _round_amount(Decimal("25"), 10, "round") == 30


def test_round_amount_floor_step10():
    assert _round_amount(Decimal("19"), 10, "floor") == 10
    assert _round_amount(Decimal("20"), 10, "floor") == 20


def test_proration_join_mid_month():
    # 2025-10 month has 31 days; join on 16th → 16 days (16..31 inclusive)
    row = {
        "입사일": "2025-10-16",
        "월 시작일": "2025-10-01",
        "월 말일": "2025-10-31",
    }
    d, t = proration_factor_for_month(row, year=2025, month=10)
    assert t == 31 and d == 16


def test_proration_leave_mid_month():
    row = {
        "퇴사일": "2025-10-10",
        "월 시작일": "2025-10-01",
        "월 말일": "2025-10-31",
    }
    d, t = proration_factor_for_month(row, year=2025, month=10)
    assert t == 31 and d == 10


def test_proration_leave_period_exclusion():
    row = {
        "입사일": "2025-10-01",
        "휴직일": "2025-10-11",
        "휴직종료일": "2025-10-20",
        "월 시작일": "2025-10-01",
        "월 말일": "2025-10-31",
    }
    d, t = proration_factor_for_month(row, year=2025, month=10)
    # 31 days total, 10 days active before leave + 11 days after leave = 21
    assert t == 31 and d == 21

