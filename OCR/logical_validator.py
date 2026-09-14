"""Logical (data-level) validation: dates, ordering, plausibility.

This layer works on already-extracted *calendar* values (ISO 'YYYY-MM-DD'
strings) -- it never touches an image, an OCR model, or extraction. It can
therefore be unit-tested with hand-built fixtures and zero dependencies.

PHILOSOPHY: every finding is a `ValidationFlag` with a severity.

  * An EXPIRED document is a validity matter: severity `warning`, always.
    It is never `high` and never conflated with forgery signals.
  * Impossible date ORDERINGS (expiry before issue, issue before birth,
    birth or issue in the future) are `HIGH` severity but framed as "likely
    OCR misread -- verify against the image", i.e. evidence, not proof.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from schemas import LogicalValidationResult, Severity, ValidationFlag

# ---------------------------------------------------------------------------
# Named, tunable constants -- STARTING VALUES for calibration against real
# checkpoint samples; not authoritative.
# ---------------------------------------------------------------------------
#: Upper bound on a document holder's age before it is flagged implausible.
MAX_PLAUSIBLE_AGE_YEARS: int = 120


def _parse_iso(value: Optional[str]) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        pass
    # Visual zones print dates in human layouts (DD/MM/YYYY etc.), not ISO.
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _flag(code: str, message: str, severity: Severity, field: Optional[str]) -> ValidationFlag:
    return ValidationFlag(code=code, message=message, severity=severity, field=field)


def validate_dates(
    date_of_birth: Optional[str] = None,
    issue_date: Optional[str] = None,
    expiry_date: Optional[str] = None,
    reference_date: Optional[date] = None,
) -> LogicalValidationResult:
    """Validate the calendar data of a document.

    All inputs are 'YYYY-MM-DD' strings (or None when not extracted).
    ``reference_date`` defaults to today (injectable for deterministic tests).
    """
    if reference_date is None:
        reference_date = date.today()

    result = LogicalValidationResult(
        date_of_birth=date_of_birth,
        issue_date=issue_date,
        expiry_date=expiry_date,
    )

    dob = _parse_iso(date_of_birth)
    issue = _parse_iso(issue_date)
    exp = _parse_iso(expiry_date)

    # --- structural parse failures ---------------------------------------
    for label, value, key in (
        ("date of birth", date_of_birth, "date_of_birth"),
        ("issue date", issue_date, "issue_date"),
        ("expiry date", expiry_date, "expiry_date"),
    ):
        if value is not None and _parse_iso(value) is None:
            result.flags.append(_flag(
                "invalid_date_format",
                f"Extracted {label} '{value}' could not be parsed as a calendar "
                "date. Likely OCR misread -- verify against the image.",
                Severity.WARNING, key,
            ))

    # --- expiry -----------------------------------------------------------
    if exp is not None:
        if exp < reference_date:
            days = (reference_date - exp).days
            result.expired = True
            result.days_to_expiry = -days
            result.flags.append(_flag(
                "expired",
                f"Document expired {days} day(s) before the reference date "
                f"({reference_date.isoformat()}). Expiry is a validity issue -- "
                "the document may still be data-accurate.",
                Severity.WARNING, "expiry_date",
            ))
        else:
            result.days_to_expiry = (exp - reference_date).days
    if exp is not None and issue is not None and exp < issue:
        result.flags.append(_flag(
            "expiry_before_issue",
            f"Expiry date ({exp.isoformat()}) precedes the issue date "
            f"({issue.isoformat()}), which is impossible for a real document. "
            "Most likely an OCR misread of one of the dates -- verify both "
            "against the image.",
            Severity.HIGH, "expiry_date",
        ))

    # --- issue vs birth ---------------------------------------------------
    if issue is not None and dob is not None and issue < dob:
        result.flags.append(_flag(
            "issue_before_birth",
            f"Issue date ({issue.isoformat()}) is before the holder's date of "
            f"birth ({dob.isoformat()}), which is impossible. Likely an OCR "
            "misread -- verify against the image.",
            Severity.HIGH, "issue_date",
        ))

    # --- date of birth in the future -------------------------------------
    if dob is not None and dob > reference_date:
        result.flags.append(_flag(
            "dob_in_future",
            f"Date of birth ({dob.isoformat()}) is in the future relative to "
            f"{reference_date.isoformat()}, which is impossible. Likely an OCR "
            "misread -- verify against the image.",
            Severity.HIGH, "date_of_birth",
        ))

    # --- issue date in the future ----------------------------------------
    if issue is not None and issue > reference_date:
        result.flags.append(_flag(
            "issue_in_future",
            f"Issue date ({issue.isoformat()}) is in the future relative to "
            f"{reference_date.isoformat()}, which is impossible for an "
            "already-printed document. Likely an OCR misread -- verify "
            "against the image.",
            Severity.HIGH, "issue_date",
        ))

    # --- age plausibility --------------------------------------------------
    if dob is not None and dob <= reference_date:
        age = reference_date.year - dob.year
        if (reference_date.month, reference_date.day) < (dob.month, dob.day):
            age -= 1
        result.age_years = age
        if age > MAX_PLAUSIBLE_AGE_YEARS:
            result.flags.append(_flag(
                "age_out_of_plausibility",
                f"Computed holder age ({age} years) exceeds the plausibility "
                f"bound of {MAX_PLAUSIBLE_AGE_YEARS} years. Either the date of "
                "birth was misread or the data does not hang together -- "
                "verify against the image.",
                Severity.WARNING, "date_of_birth",
            ))

    # --- informational: checks that could not run --------------------------
    if dob is None:
        result.flags.append(_flag(
            "dob_missing",
            "No date of birth extracted; age and birth-order checks skipped.",
            Severity.INFO, "date_of_birth",
        ))
    if exp is None:
        result.flags.append(_flag(
            "expiry_missing",
            "No expiry date extracted; expiry status check skipped.",
            Severity.INFO, "expiry_date",
        ))
    if issue is None:
        result.flags.append(_flag(
            "issue_missing",
            "No issue date extracted; issue-order checks skipped.",
            Severity.INFO, "issue_date",
        ))

    return result