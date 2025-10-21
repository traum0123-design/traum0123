from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from payroll_shared.locks import redis_lock


@contextmanager
def company_extra_field_lock(company_id: int, label: str) -> Iterator[bool]:
    """Distributed lock scoped to (company, label) when creating extra fields."""

    key = f"company:{int(company_id)}:extra:{label}"
    with redis_lock(key, ttl_seconds=30, wait_timeout=8) as acquired:
        yield acquired

