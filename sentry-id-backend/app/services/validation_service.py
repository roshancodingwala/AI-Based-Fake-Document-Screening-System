"""
Rule-based validation of extracted document fields.

This module is intentionally pure logic (no ML) — it checks required
fields, date formats/ordering, and simple document-number patterns. This
is the layer most likely to stay hand-written even in production, since
these are deterministic business rules rather than model predictions.
"""
import re
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Optional

# Ensure OCR folder is in sys.path for verhoeff / rules
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_WORKSPACE_ROOT = _BACKEND_DIR.parent
_OCR_DIR = _WORKSPACE_ROOT / "OCR"
if _OCR_DIR.is_dir() and str(_OCR_DIR) not in sys.path:
    sys.path.insert(0, str(_OCR_DIR))

try:
    from verhoeff import verify_verhoeff
    _VERHOEFF_AVAILABLE = True
except Exception:
    _VERHOEFF_AVAILABLE = False

from app.schemas.documents import OCRFields, OCRResponse, ValidationResponse

DATE_FORMAT = "%Y-%m-%d"

DOC_NUMBER_PATTERNS = {
    "Passport": re.compile(r"^[A-Z]-?\d{6,9}$"),
    "Visa": re.compile(r"^V-?\d{4,9}$"),
    "National ID": re.compile(r"^ID-?\d{4,9}$"),
    "Driving Licence": re.compile(r"^DL-?\d{4,9}$"),
    "Permit": re.compile(r"^PM-?\d{4,9}$"),
    "Aadhaar": re.compile(r"^\d{4}\s?\d{4}\s?\d{4}$"),
    "PAN": re.compile(r"^[A-Z]{5}\d{4}[A-Z]$"),
}


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in (DATE_FORMAT, "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            dt = datetime.strptime(value.strip(), fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


class ValidationService:
    def validate(
        self,
        fields: OCRFields,
        document_type: str = "Passport",
        ocr_response: Optional[OCRResponse] = None,
    ) -> ValidationResponse:
        errors: list[str] = []
        warnings: list[str] = []

        # Required fields check
        required = ["name", "document_number", "nationality", "date_of_birth", "issue_date", "expiry_date"]
        # Aadhaar does not carry expiry_date or issue_date on standard cards
        if document_type.lower() in ("aadhaar", "pan", "pan_card"):
            required = ["name", "document_number"]

        for field_name in required:
            if not getattr(fields, field_name, None):
                errors.append(f"Missing required field: {field_name}")

        # Date formats
        dob = _parse_date(fields.date_of_birth)
        issue = _parse_date(fields.issue_date)
        expiry = _parse_date(fields.expiry_date)

        if fields.date_of_birth and dob is None:
            errors.append("date_of_birth is not in a valid date format (expected YYYY-MM-DD or DD/MM/YYYY)")
        if fields.issue_date and issue is None:
            errors.append("issue_date is not in a valid date format")
        if fields.expiry_date and expiry is None:
            errors.append("expiry_date is not in a valid date format")

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

        # Document number checks
        doc_num = (fields.document_number or "").replace(" ", "").replace("-", "").strip()

        # Aadhaar Verhoeff Checksum
        is_aadhaar = document_type.lower() in ("aadhaar", "uidai") or (len(doc_num) == 12 and doc_num.isdigit())
        if is_aadhaar and doc_num:
            if len(doc_num) != 12 or not doc_num.isdigit():
                errors.append("Aadhaar number must be exactly 12 digits")
            elif _VERHOEFF_AVAILABLE:
                if not verify_verhoeff(doc_num):
                    errors.append("Aadhaar Verhoeff checksum failed: invalid check digit (possible altered number)")

        # PAN Card Check
        is_pan = document_type.lower() in ("pan", "pan_card") or (len(doc_num) == 10 and re.match(r"^[A-Z]{5}\d{4}[A-Z]$", doc_num.upper()))
        if is_pan and doc_num:
            clean_pan = doc_num.upper()
            if not re.match(r"^[A-Z]{5}\d{4}[A-Z]$", clean_pan):
                errors.append("PAN card format invalid (expected 5 letters, 4 digits, 1 letter)")
            else:
                entity_char = clean_pan[3]
                if entity_char not in ("P", "C", "H", "F", "A", "T", "B", "L", "J", "G"):
                    warnings.append(f"PAN card entity code '{entity_char}' is unusual")

        # Standard document pattern warning
        pattern = DOC_NUMBER_PATTERNS.get(document_type)
        if pattern and fields.document_number and not pattern.match(fields.document_number.upper()):
            warnings.append(f"Document number format is unusual for {document_type}")

        # Ingest flags from OCR engine if available
        if ocr_response and ocr_response.flags:
            for flag in ocr_response.flags:
                sev = flag.get("severity", "warning")
                msg = flag.get("message", flag.get("code", "Flag"))
                if sev == "high":
                    errors.append(f"OCR Finding: {msg}")
                elif sev == "warning":
                    warnings.append(f"OCR Note: {msg}")

        return ValidationResponse(is_valid=len(errors) == 0, errors=errors, warnings=warnings)


def get_validation_service() -> ValidationService:
    return ValidationService()
