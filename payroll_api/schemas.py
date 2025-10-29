from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    ok: bool
    status: Optional[str] = None
    error: Optional[str] = None


class SimpleOkResponse(BaseModel):
    ok: bool = True


class ErrorResponse(BaseModel):
    ok: bool = False
    error: str
    code: Optional[str] = None


class WithholdingResponse(BaseModel):
    ok: bool = True
    year: int
    dep: int
    wage: int
    tax: int
    local_tax: int


class PayrollRowsResponse(BaseModel):
    ok: bool = True
    rows: list[dict[str, Any]]


class CompanySummary(BaseModel):
    id: int
    name: str
    slug: str
    created_at: Optional[str] = None


class AdminCompaniesResponse(BaseModel):
    ok: bool = True
    companies: list[CompanySummary]


class AdminCompaniesPageResponse(BaseModel):
    ok: bool = True
    items: list[CompanySummary]
    next_cursor: str | None = None
    has_more: bool = False


class AdminCompanyCreateResponse(BaseModel):
    ok: bool = True
    company: CompanySummary
    access_code: str


class AdminCompanyResetResponse(BaseModel):
    ok: bool = True
    company_id: int
    access_code: str


class WithholdingImportResponse(BaseModel):
    ok: bool = True
    year: int
    count: int


class PayrollCalcRequest(BaseModel):
    year: int
    row: dict[str, Any] = Field(default_factory=dict)


class PayrollCalcResponse(BaseModel):
    ok: bool = True
    amounts: dict[str, int] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WithholdingYearsResponse(BaseModel):
    ok: bool = True
    years: list[list[int]]


class ClientLogPayload(BaseModel):
    level: Optional[str] = "error"
    message: Optional[str] = None
    url: Optional[str] = None
    ua: Optional[str] = None
    line: Optional[str] = None
    col: Optional[str] = None
    stack: Optional[str] = None
    kind: Optional[str] = None


class FieldCalcInclude(BaseModel):
    nhis: dict[str, bool] = Field(default_factory=dict)
    ei: dict[str, bool] = Field(default_factory=dict)


class FieldCalcConfigResponse(BaseModel):
    ok: bool = True
    include: FieldCalcInclude


class FieldCalcConfigRequest(BaseModel):
    include: dict[str, dict[str, bool]] = Field(default_factory=dict)


class FieldExemptEntry(BaseModel):
    enabled: bool = False
    limit: int = 0


class FieldExemptConfigResponse(BaseModel):
    ok: bool = True
    exempt: dict[str, FieldExemptEntry] = Field(default_factory=dict)
    base: dict[str, int] = Field(default_factory=dict)


class FieldExemptConfigRequest(BaseModel):
    exempt: dict[str, FieldExemptEntry] = Field(default_factory=dict)


class FieldAddRequest(BaseModel):
    label: str
    typ: str = "number"


class FieldInfo(BaseModel):
    name: str
    label: str
    typ: str


class FieldAddResponse(BaseModel):
    ok: bool = True
    field: FieldInfo
    existed: bool = False


class FieldDeleteRequest(BaseModel):
    name: str


class FieldGroupConfigRequest(BaseModel):
    map: dict[str, str] = Field(default_factory=dict)
    alias: dict[str, str] = Field(default_factory=dict)


class FieldGroupConfigResponse(BaseModel):
    ok: bool = True


class FieldProrateConfigResponse(BaseModel):
    ok: bool = True
    prorate: dict[str, bool] = Field(default_factory=dict)


class FieldProrateConfigRequest(BaseModel):
    prorate: dict[str, bool] = Field(default_factory=dict)


class WithholdingCellEntry(BaseModel):
    dependents: int
    wage: int
    tax: int


class AdminWithholdingCellsPageResponse(BaseModel):
    ok: bool = True
    items: list[WithholdingCellEntry]
    next_cursor: str | None = None
    has_more: bool = False


class ExtraFieldEntry(BaseModel):
    id: int
    name: str
    label: str
    typ: str
    position: int


class AdminExtraFieldsPageResponse(BaseModel):
    ok: bool = True
    items: list[ExtraFieldEntry]
    next_cursor: str | None = None
    has_more: bool = False


class AdminPayrollSummary(BaseModel):
    id: int
    year: int
    month: int
    is_closed: bool = False
    updated_at: Optional[str] = None


class AdminCompanyPayrollsPageResponse(BaseModel):
    ok: bool = True
    items: list[AdminPayrollSummary]
    next_cursor: str | None = None
    has_more: bool = False


class AdminPolicyHistoryEntry(BaseModel):
    id: int
    ts: str
    actor: str
    company_id: int | None = None
    year: int
    old: dict[str, Any] = Field(default_factory=dict)
    new: dict[str, Any] = Field(default_factory=dict)


class AdminPolicyHistoryPageResponse(BaseModel):
    ok: bool = True
    items: list[AdminPolicyHistoryEntry]
    next_cursor: str | None = None
    has_more: bool = False


class UIPrefsGetResponse(BaseModel):
    ok: bool = True
    values: dict[str, Any] = Field(default_factory=dict)


class UIPrefsPostRequest(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)


class UIPrefsPostResponse(BaseModel):
    ok: bool = True


class AuditEventEntry(BaseModel):
    id: int
    ts: str
    actor: str
    company_id: int | None = None
    action: str
    resource: str
    ip: str
    ua: str
    result: str
    meta: dict[str, Any] = Field(default_factory=dict)


class AdminAuditPageResponse(BaseModel):
    ok: bool = True
    items: list[AuditEventEntry]
    next_cursor: str | None = None
    has_more: bool = False
