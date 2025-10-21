"""Payroll portal package exposing Flask app factory."""

from .app import app, create_app  # noqa: F401

__all__ = ["create_app", "app"]
