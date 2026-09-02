"""Shared date-field validation for pilot and ICP ledgers."""

from __future__ import annotations

from datetime import date, datetime


def require_iso_datetime(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} is required and must be an ISO 8601 datetime")
    validate_optional_iso_datetime(value, field_name)


def validate_optional_iso_datetime(value: str, field_name: str) -> None:
    text = value.strip()
    if not text:
        return
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO 8601 datetime, got: {text!r}") from exc


def validate_optional_date(value: str, field_name: str) -> None:
    text = value.strip()
    if not text:
        return
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be YYYY-MM-DD, got: {text!r}") from exc
