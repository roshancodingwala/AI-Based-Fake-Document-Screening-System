"""Tests for logical date validation -- hand-built fixtures, NO OCR / images.

All reference dates are injected so the tests are deterministic regardless of
when they run.
"""

from datetime import date

from logical_validator import validate_dates
from schemas import Severity


def _codes(result):
    return {f.code for f in result.flags}


def test_clean_valid_document_before_expiry():
    r = validate_dates(
        date_of_birth="1980-05-10",
        issue_date="2015-03-01",
        expiry_date="2030-03-01",
        reference_date=date(2026, 1, 1),
    )
    assert r.expired is False
    assert r.days_to_expiry == 1520
    assert r.age_years == 45
    assert _codes(r) == set()  # no flags at all


def test_expired_document_is_warning_not_high():
    r = validate_dates(
        date_of_birth="1980-05-10",
        issue_date="2015-03-01",
        expiry_date="2020-03-01",
        reference_date=date(2026, 1, 1),
    )
    assert r.expired is True
    assert r.days_to_expiry == -2132
    codes = {f.code: f.severity for f in r.flags}
    assert codes["expired"] == Severity.WARNING
    # an expired (but otherwise consistent) doc must NOT raise high severity
    assert Severity.HIGH not in codes.values()


def test_expiry_before_issue_is_high():
    r = validate_dates(
        date_of_birth="1980-05-10",
        issue_date="2015-03-01",
        expiry_date="2010-03-01",
        reference_date=date(2026, 1, 1),
    )
    assert any(f.code == "expiry_before_issue" and f.severity == Severity.HIGH
               for f in r.flags)
    # framed as evidence, never as a forgery assertion
    assert any("OCR misread" in f.message for f in r.flags)


def test_issue_before_birth_is_high():
    r = validate_dates(
        date_of_birth="2000-06-01",
        issue_date="1995-01-01",
        expiry_date="2030-01-01",
        reference_date=date(2026, 1, 1),
    )
    assert any(f.code == "issue_before_birth" and f.severity == Severity.HIGH
               for f in r.flags)


def test_dob_in_future_is_high():
    r = validate_dates(
        date_of_birth="2035-06-01",
        issue_date="2020-01-01",
        expiry_date="2030-01-01",
        reference_date=date(2026, 1, 1),
    )
    assert any(f.code == "dob_in_future" and f.severity == Severity.HIGH
               for f in r.flags)
    assert r.age_years is None


def test_issue_in_future_is_high():
    r = validate_dates(
        date_of_birth="1990-06-01",
        issue_date="2035-01-01",
        expiry_date="2040-01-01",
        reference_date=date(2026, 1, 1),
    )
    assert any(f.code == "issue_in_future" and f.severity == Severity.HIGH
               for f in r.flags)
    assert any("OCR misread" in f.message for f in r.flags)


def test_issue_today_is_not_future():
    r = validate_dates(
        issue_date="2026-01-01",
        reference_date=date(2026, 1, 1),
    )
    assert "issue_in_future" not in _codes(r)


def test_extreme_age_flags_warning():
    r = validate_dates(
        date_of_birth="1850-06-01",
        issue_date="2015-03-01",
        expiry_date="2030-03-01",
        reference_date=date(2026, 1, 1),
    )
    assert r.age_years == 175
    assert any(f.code == "age_out_of_plausibility"
               and f.severity == Severity.WARNING for f in r.flags)


def test_legal_age_not_flagged():
    r = validate_dates(
        date_of_birth="2001-06-01",
        issue_date="2015-03-01",
        expiry_date="2030-03-01",
        reference_date=date(2026, 1, 1),
    )
    assert r.age_years == 24
    assert "age_out_of_plausibility" not in _codes(r)


def test_missing_dates_produce_info_flags():
    r = validate_dates(expiry_date="2030-01-01", reference_date=date(2026, 1, 1))
    assert r.age_years is None
    assert "dob_missing" in _codes(r)
    assert "issue_missing" in _codes(r)
    assert all(
        f.severity == Severity.INFO
        for f in r.flags
        if f.code in ("dob_missing", "issue_missing")
    )


def test_invalid_date_format_is_warning_not_crash():
    r = validate_dates(date_of_birth="not-a-date", reference_date=date(2026, 1, 1))
    assert any(f.code == "invalid_date_format" for f in r.flags)
    assert r.age_years is None
    assert r.expired is False


def test_boundary_expiry_today_is_not_expired():
    r = validate_dates(
        expiry_date="2026-01-01",
        reference_date=date(2026, 1, 1),
    )
    assert r.expired is False
    assert r.days_to_expiry == 0
    assert "expired" not in _codes(r)


def test_all_dates_valid_but_multiple_checks_run():
    # full date trio, valid ordering, no expiry -> zero flags
    r = validate_dates(
        date_of_birth="1990-01-01",
        issue_date="2010-06-15",
        expiry_date="2030-06-14",
        reference_date=date(2026, 1, 1),
    )
    assert _codes(r) == set()
    assert r.age_years == 36
    assert r.days_to_expiry == 1625