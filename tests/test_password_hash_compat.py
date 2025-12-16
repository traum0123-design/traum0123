from __future__ import annotations

from werkzeug.security import generate_password_hash

from core.services import companies
from core.settings import reset_settings_cache


SCRYPT_HASH_1234 = (
    "scrypt:32768:8:1$dsWbqeMFENgkHHg5$"
    "4b77cbcd7abd34169fee626783c7c542e8efa3f67f3acb930d842bfa5bf191ef"
    "61d98508c650c08655885eac7945dc7df4970b704f7e9a9d50fa6a7284eafcef"
)


def test_scrypt_manual_fallback_when_werkzeug_fails(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", SCRYPT_HASH_1234)
    reset_settings_cache()

    def boom(*_a, **_kw):
        raise ValueError("memory limit exceeded")

    monkeypatch.setattr(companies, "check_password_hash", boom)
    assert companies.verify_admin_password("1234") is True


def test_plain_password_still_supported(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "plainpw")
    reset_settings_cache()
    assert companies.verify_admin_password("plainpw") is True


def test_pbkdf2_manual_fallback(monkeypatch):
    pb_hash = generate_password_hash("pw", method="pbkdf2:sha256")
    monkeypatch.setenv("ADMIN_PASSWORD", pb_hash)
    reset_settings_cache()

    def boom(*_a, **_kw):
        raise ValueError("boom")

    monkeypatch.setattr(companies, "check_password_hash", boom)
    assert companies.verify_admin_password("pw") is True

