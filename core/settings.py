from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PayrollSettings(BaseSettings):
    """Centralized application configuration pulled from environment/.env."""

    secret_key: str = Field("dev-secret", alias="SECRET_KEY")
    # Make ADMIN_PASSWORD optional at process start to avoid hard-crash on missing env
    # - When empty, admin login will always fail, but the app can boot (useful for Cloud Run first deploy)
    admin_password: str = Field("", alias="ADMIN_PASSWORD")
    database_url: Optional[str] = Field(None, alias="DATABASE_URL")
    payroll_auto_apply_ddl: bool = Field(True, alias="PAYROLL_AUTO_APPLY_DDL")
    admin_rate_limit_backend: str = Field("auto", alias="ADMIN_RATE_LIMIT_BACKEND")
    admin_rate_limit_redis_url: Optional[str] = Field(None, alias="ADMIN_RATE_LIMIT_REDIS_URL")
    # Redis rate limit fail policy: 'open' (allow when Redis down), 'closed' (block), 'memory' (fallback to in-proc)
    admin_rate_limit_redis_policy: str = Field("open", alias="ADMIN_RATE_LIMIT_REDIS_POLICY")
    enforce_alembic_migrations: bool = Field(False, alias="PAYROLL_ENFORCE_ALEMBIC")
    # Build/meta info
    app_version: str = Field("dev", alias="APP_VERSION")
    git_sha: Optional[str] = Field(None, alias="GIT_SHA")
    build_ts: Optional[str] = Field(None, alias="BUILD_TS")
    # Public base URL for portal links (e.g., https://portal.example.com)
    portal_public_base_url: Optional[str] = Field(None, alias="PORTAL_PUBLIC_BASE_URL")
    # Company token TTL (seconds). Default 30 days to reduce repeated logins.
    company_token_ttl: int = Field(60 * 60 * 24 * 30, alias="COMPANY_TOKEN_TTL")
    # Portal cookie max age (seconds). Defaults to company_token_ttl if not set.
    portal_cookie_max_age: Optional[int] = Field(None, alias="PORTAL_COOKIE_MAX_AGE")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("secret_key", mode="before")
    @classmethod
    def _normalize_secret(cls, value: str | None) -> str:
        val = (value or "dev-secret").strip()
        return val or "dev-secret"

    @field_validator("admin_password", mode="before")
    @classmethod
    def _validate_admin_password(cls, value: str | None) -> str:
        # Allow empty admin password at boot; actual login will fail when empty.
        # This prevents startup crashes on platforms where envs are injected later or misconfigured.
        val = (value or "").strip()
        return val

    @field_validator("database_url", mode="before")
    @classmethod
    def _strip_database_url(cls, value: str | None) -> Optional[str]:
        return value.strip() if isinstance(value, str) else value

    @field_validator("payroll_auto_apply_ddl", mode="before")
    @classmethod
    def _parse_bool(cls, value) -> bool:
        if isinstance(value, bool):
            return value
        if value is None or value == "":
            return True
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    @field_validator("admin_rate_limit_backend", mode="before")
    @classmethod
    def _normalize_backend(cls, value: str | None) -> str:
        val = (value or "auto").strip().lower()
        if val not in {"auto", "memory", "redis"}:
            return "memory"
        return val or "auto"

    @field_validator("admin_rate_limit_redis_policy", mode="before")
    @classmethod
    def _normalize_redis_policy(cls, value: str | None) -> str:
        val = (value or "open").strip().lower()
        if val not in {"open", "closed", "memory"}:
            return "open"
        return val

    @field_validator("enforce_alembic_migrations", mode="before")
    @classmethod
    def _parse_enforce(cls, value) -> bool:
        if isinstance(value, bool):
            return value
        if value is None or value == "":
            return False
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    @field_validator("portal_public_base_url", mode="before")
    @classmethod
    def _normalize_portal_base(cls, value: str | None) -> Optional[str]:
        if value is None:
            return None
        val = str(value).strip()
        return val or None

    @field_validator("company_token_ttl", mode="before")
    @classmethod
    def _parse_int_ttl(cls, value) -> int:
        try:
            n = int(value)
            return max(600, n)  # at least 10 minutes
        except Exception:
            return 60 * 60 * 24 * 30

    @field_validator("portal_cookie_max_age", mode="before")
    @classmethod
    def _parse_cookie_age(cls, value) -> Optional[int]:
        if value in (None, ""):
            return None
        try:
            n = int(value)
            return max(600, n)
        except Exception:
            return None


@lru_cache(maxsize=1)
def get_settings() -> PayrollSettings:
    return PayrollSettings()


def reset_settings_cache() -> None:
    """Testing helper to clear cached settings."""
    get_settings.cache_clear()
