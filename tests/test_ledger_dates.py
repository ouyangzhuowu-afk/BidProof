import pytest

from work.ledger_dates import (
    require_iso_datetime,
    validate_optional_date,
    validate_optional_iso_datetime,
)


def test_require_iso_datetime_accepts_offset():
    require_iso_datetime("2026-09-02T10:00:00+08:00", "received_at")


def test_require_iso_datetime_rejects_empty():
    with pytest.raises(ValueError, match="received_at is required"):
        require_iso_datetime("", "received_at")


def test_validate_optional_iso_datetime_rejects_bad_value():
    with pytest.raises(ValueError, match="ISO 8601"):
        validate_optional_iso_datetime("yesterday", "contacted_at")


def test_validate_optional_date_accepts_iso_date():
    validate_optional_date("2026-09-09", "next_step_due")


def test_validate_optional_date_rejects_us_format():
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        validate_optional_date("09/09/2026", "next_step_due")
