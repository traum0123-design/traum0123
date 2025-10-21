"""
Legacy compatibility shim: payroll_api.models now re-exports the shared ORM models
from payroll_shared.models so there is a single source of truth for the schema.
"""

from payroll_shared.models import (  # noqa: F401
    Base,
    Company,
    MonthlyPayroll,
    ExtraField,
    FieldPref,
    WithholdingCell,
)

__all__ = [
    "Base",
    "Company",
    "MonthlyPayroll",
    "ExtraField",
    "FieldPref",
    "WithholdingCell",
]
