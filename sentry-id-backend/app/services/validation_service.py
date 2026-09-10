"""
Rule-based validation of extracted document fields.

This module is intentionally pure logic (no ML) — it checks required
fields, date formats/ordering, and simple document-number patterns. This
is the layer most likely to stay hand-written even in production, since
these are deterministic business rules rather than model predictions.
"""
import re
from datetime import datetime, timezone

from app.schemas.documents import OCRFields, ValidationResponse

DATE_FORMAT = "%Y-%m-%d"

DOC_NUMBER_PATTERNS = {
    "Passport": re.compile(r"^[A-Z]-?\d{6,9}$"),
    "Visa": re.compile(r"^V-?\d{4,9}$"),
    "National ID": re.compile(r"^ID-?\d{4,9}$"),
    "Driving Licence": re.compile(r"^DL-?\d{4,9}$"),
    "Permit": re.compile(r"^PM-?\d{4,9}$"),
}


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.strptime(value, DATE_FORMAT)
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


class ValidationService:
    def validate(self, fields: OCRFields, document_type: str) -> ValidationResponse:
        errors: list[str] = []
        warnings: list[str] = []

        # Required fields
        required = ["name", "document_number", "nationality", "date_of_birth", "issue_date", "expiry_date"]
        for field_name in required:
            if not getattr(fields, field_name, None):
                errors.append(f"Missing required field: {field_name}")

        # Date formats
        dob = _parse_date(fields.date_of_birth)
        issue = _parse_date(fields.issue_date)
        expiry = _parse_date(fields.expiry_date)

        if fields.date_of_birth and dob is None:
            errors.append("date_of_birth is not in YYYY-MM-DD format")
        if fields.issue_date and issue is None:
            errors.append("issue_date is not in YYYY-MM-DD format")
        if fields.expiry_date and expiry is None:
            errors.append("expiry_date is not in YYYY-MM-DD format")

        now = datetime.now(timezone.utc)

        # Internal consistency
        if dob and dob > now:
            errors.append("date_of_birth is in the future")
        if issue and expiry and issue >= expiry:
            errors.append("issue_date must be before expiry_date")
        if expiry and expiry < now:
            warnings.append("Document has expired")
        if dob and issue and (issue.year - dob.year) < 0:
            errors.append("issue_date predates date_of_birth")

        # Document number format (soft rule -> warning, not hard error, since
        # real-world formats vary a lot by issuing country)
        pattern = DOC_NUMBER_PATTERNS.get(document_type)
        if pattern and fields.document_number and not pattern.match(fields.document_number.upper()):
            warnings.append(f"Document number format is unusual for {document_type}")

        return ValidationResponse(is_valid=len(errors) == 0, errors=errors, warnings=warnings)


def get_validation_service() -> ValidationService:
    return ValidationService()
