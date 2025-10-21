from __future__ import annotations

from typing import Any, Dict, List, Optional

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
    rows: List[Dict[str, Any]]


class CompanySummary(BaseModel):
    id: int
    name: str
    slug: str
    created_at: Optional[str] = None


class AdminCompaniesResponse(BaseModel):
    ok: bool = True
    companies: List[CompanySummary]


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


class WithholdingYearsResponse(BaseModel):
    ok: bool = True
    years: List[List[int]]


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
    nhis: Dict[str, bool] = Field(default_factory=dict)
    ei: Dict[str, bool] = Field(default_factory=dict)


class FieldCalcConfigResponse(BaseModel):
    ok: bool = True
    include: FieldCalcInclude


class FieldCalcConfigRequest(BaseModel):
    include: Dict[str, Dict[str, bool]] = Field(default_factory=dict)


class FieldExemptEntry(BaseModel):
    enabled: bool = False
    limit: int = 0


class FieldExemptConfigResponse(BaseModel):
    ok: bool = True
    exempt: Dict[str, FieldExemptEntry] = Field(default_factory=dict)
    base: Dict[str, int] = Field(default_factory=dict)


class FieldExemptConfigRequest(BaseModel):
    exempt: Dict[str, FieldExemptEntry] = Field(default_factory=dict)


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
    map: Dict[str, str] = Field(default_factory=dict)
    alias: Dict[str, str] = Field(default_factory=dict)


class FieldGroupConfigResponse(BaseModel):
    ok: bool = True
