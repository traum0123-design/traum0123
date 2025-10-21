from __future__ import annotations

import datetime as dt
import copy

import pytest

from core.models import Company, FieldPref, WithholdingCell
from core.services import payroll as payroll_service


@pytest.fixture
def company(session):
    comp = Company(
        name="테스트회사",
        slug="test-co",
        access_hash="hash",
        token_key="",
        created_at=dt.datetime.now(dt.timezone.utc),
    )
    session.add(comp)
    session.commit()
    return comp


@pytest.fixture
def insure_config(monkeypatch):
    original = copy.deepcopy(payroll_service.INSURANCE_CONFIG)
    config = {
        "base_exemptions": {},
        "nps": {"rate": 0.045, "min_base": None, "max_base": None, "round_to": 10, "rounding": "round"},
        "nhis": {
            "rate": 0.03545,
            "min_base": None,
            "max_base": None,
            "round_to": 10,
            "rounding": "round",
            "ltc_rate": 0.1295,
            "ltc_round_to": 10,
            "ltc_rounding": "round",
        },
        "ei": {"rate": 0.009, "min_base": None, "max_base": None, "round_to": 10, "rounding": "round"},
    }
    monkeypatch.setattr(payroll_service, "INSURANCE_CONFIG", config, raising=False)
    yield config
    monkeypatch.setattr(payroll_service, "INSURANCE_CONFIG", original, raising=False)


def _seed_field_prefs(session, company):
    prefs = [
        FieldPref(company_id=company.id, field="기본급", group="earn", ins_nhis=True, ins_ei=True),
        FieldPref(company_id=company.id, field="식대", group="earn"),
        FieldPref(company_id=company.id, field="국민연금", group="deduct"),
        FieldPref(company_id=company.id, field="건강보험", group="deduct"),
        FieldPref(company_id=company.id, field="장기요양보험", group="deduct"),
        FieldPref(company_id=company.id, field="고용보험", group="deduct"),
        FieldPref(company_id=company.id, field="소득세", group="deduct"),
        FieldPref(company_id=company.id, field="지방소득세", group="deduct"),
    ]
    session.add_all(prefs)
    session.commit()


def _seed_withholding_table(session):
    rows = [
        WithholdingCell(year=2024, dependents=1, wage=2_000_000, tax=100_000),
        WithholdingCell(year=2024, dependents=1, wage=2_100_000, tax=110_000),
        WithholdingCell(year=2024, dependents=1, wage=2_200_000, tax=120_000),
    ]
    session.add_all(rows)
    session.commit()


@pytest.mark.usefixtures("insure_config")
def test_compute_deductions_basic_rounding(session, company):
    _seed_field_prefs(session, company)
    _seed_withholding_table(session)

    row = {
        "기본급": 2_000_000,
        "식대": 200_000,
        "부양가족수": 1,
    }

    amounts, meta = payroll_service.compute_deductions(session, company, row, 2024)

    assert meta["default_base"] == 2_200_000
    assert amounts["national_pension"] == 99_000
    assert amounts["health_insurance"] == 70_900
    assert amounts["long_term_care"] == 9_180
    assert amounts["employment_insurance"] == 18_000
    assert amounts["income_tax"] == 120_000
    assert amounts["local_income_tax"] == 12_000


def test_compute_deductions_honours_base_exemptions(session, company, insure_config):
    insure_config["base_exemptions"] = {"식대": 100_000}
    _seed_field_prefs(session, company)
    _seed_withholding_table(session)

    row = {
        "기본급": 2_000_000,
        "식대": 200_000,
        "부양가족수": 1,
    }

    amounts, meta = payroll_service.compute_deductions(session, company, row, 2024)

    assert meta["default_base"] == 2_100_000
    assert amounts["national_pension"] == 94_500
    assert amounts["income_tax"] == 110_000

