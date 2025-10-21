"""
Legacy compatibility shim: payroll_api.models now re-exports the shared ORM models
from core.models so there is a single source of truth for the schema.
"""

from core.models import (  # noqa: F401
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
