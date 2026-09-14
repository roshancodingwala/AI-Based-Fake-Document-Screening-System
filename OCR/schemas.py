"""Data contracts for Module 1 (OCR & Document Validation).

This module defines ONLY contracts -- enums, data models and result
objects. It contains zero logic about parsing, validating or judging
documents, so it can be imported by every other module without pulling in
OpenCV or OCR runtimes.

Design philosophy (see README):
  * These result objects NEVER express a fraud/genuine verdict. Every
    finding is a `ValidationFlag` carrying a severity and a human-readable,
    officer-facing message.
  * The 0-100 `validation_score` measures ONLY whether the document's
    *data* hangs together. Nothing here touches image authenticity or face
    match -- those belong to later stages (Module 2+).
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class DocumentType(str, Enum):
    """Supported document types.

    `UNKNOWN` is a first-class value: an unrecognized document must be
    scored as such and handled gracefully, never forced into the nearest
    known type.
    """

    PASSPORT = "passport"
    ID_CARD = "id_card"
    NATIONAL_ID = "national_id"
    DRIVING_LICENSE = "driving_license"
    VOTER_ID = "voter_id"
    PAN_CARD = "pan_card"
    AADHAAR = "aadhaar"
    RESIDENCE_PERMIT = "residence_permit"
    UNKNOWN = "unknown"


class MRZFormat(str, Enum):
    """ICAO 9303 machine-readable zone layout families.

    TD1: 3 lines x 30 chars (ID cards, visa vignettes).
    TD2: 2 lines x 36 chars (MRV visas, some ID cards).
    TD3: 2 lines x 44 chars (passport booklets).
    """

    TD1 = "TD1"
    TD2 = "TD2"
    TD3 = "TD3"
    NONE = "NONE"


class FieldSource(str, Enum):
    """Where an `ExtractedField` value came from."""

    MRZ = "mrz"
    VISUAL = "visual"  # visible-zone OCR
    BARCODE = "barcode"
    OCR = "ocr"  # generic OCR source, source not pinned
    TEMPLATE = "template"  # structure-aware ROI crop of a registered template
    UNKNOWN = "unknown"


class Severity(str, Enum):
    """Severity of a validation finding.

    `info`      -> purely informational observation.
    `warning`   -> plausibility / policy concern (e.g. expired document).
    `high`      -> data-level inconsistency that materially weakens the
                   document's data (still evidence, never proof -- the
                   cause may be OCR error, damage, or tampering).
    """

    INFO = "info"
    WARNING = "warning"
    HIGH = "high"


class CheckDigitResult(BaseModel):
    """Outcome of one modulus-10 weighted check digit."""

    field: str
    expected: str
    computed: str
    valid: bool = False


class ExtractedField(BaseModel):
    """A single field value with provenance and confidence."""

    name: str
    value: str
    source: FieldSource = FieldSource.OCR
    confidence: float = Field(ge=0.0, le=1.0)
    # Fractional (0.0-1.0) bounding box [x0, y0, x1, y1], optional.
    bbox: Optional[tuple[float, float, float, float]] = None


class MRZResult(BaseModel):
    """Parsed output of the machine-readable zone.

    `data` holds the raw MRZ strings per standardized key; per-field raw
    strings keep the 2-digit-year / check-digit layout intact so rules can
    inspect exact OCR output. `check_digits` reports each per-field check
    digit and the composite check digit; every failing check is evidence
    (OCR error, physical damage, OR tampering) -- never asserted as a
    cause on its own.
    """

    mrz_format: MRZFormat = MRZFormat.NONE
    recognized: bool = False
    lines: list[str] = Field(default_factory=list)
    data: dict[str, str] = Field(default_factory=dict)
    identifiers: dict[str, str] = Field(default_factory=dict)
    check_digits: dict[str, bool] = Field(default_factory=dict)
    check_details: list[CheckDigitResult] = Field(default_factory=list)
    message: str = ""


class ValidationFlag(BaseModel):
    """One validated finding: stable code + officer-facing message."""

    code: str
    message: str
    severity: Severity = Severity.WARNING
    field: Optional[str] = None


class LogicalValidationResult(BaseModel):
    """Date/plausibility checks over the parsed calendar fields."""

    flags: list[ValidationFlag] = Field(default_factory=list)
    date_of_birth: Optional[str] = None
    issue_date: Optional[str] = None
    expiry_date: Optional[str] = None
    age_years: Optional[int] = None
    expired: bool = False
    days_to_expiry: Optional[int] = None


class BarcodeResult(BaseModel):
    """One decoded machine-readable zone read.

    ``channel`` is the classified purpose: ``aadhaar_qr`` (UIDAI QR
    payload), ``dl_barcode`` (smart-card 2D barcode) or ``unclassified``.
    ``data`` holds the parsed payload fields on the channel's own vocabulary
    (e.g. UIDAI ``uid``/``name``/``dob``), and ``signature_present`` records
    whether the Aadhaar payload carried UIDAI's digitally-signed element
    (true signature *verification* belongs to a trusted verifier stage).
    """

    channel: str = "unclassified"
    format: str = ""
    raw: str = ""
    data: dict[str, str] = Field(default_factory=dict)
    signature_present: bool = False


class DocumentValidationResult(BaseModel):
    """Full Module-1 output for one document.

    `validation_score` (0-100): higher = the document's *data* hangs
    together better. It is NOT a fraud/genuine score; it deliberately
    ignores image authenticity and face-match (those live in later
    stages) and can only ever grow to 0-100 via explicit named deductions.
    """

    document_type: DocumentType = DocumentType.UNKNOWN
    classification_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    validation_score: int = Field(default=0, ge=0, le=100)
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    #: One row per named deduction (flag severity / low confidence / unknown
    #: penalty), each with the points removed and the running balance, so a
    #: dashboard can show EXACTLY why the score left points. Ends with the
    #: "remaining_points" row = final validation_score.
    score_ledger: list[dict] = Field(default_factory=list)
    flags: list[ValidationFlag] = Field(default_factory=list)
    fields: list[ExtractedField] = Field(default_factory=list)
    mrz: Optional[MRZResult] = None
    mrz_found: bool = False
    barcodes: list[BarcodeResult] = Field(default_factory=list)
    message: str = ""

    @field_validator("validation_score")
    @classmethod
    def _clamp_score(cls, v: int) -> int:
        return max(0, min(100, int(v)))


# Keys the `score_breakdown` dict must ALWAYS contain, even when zero, so a
# downstream dashboard can render a stable panel without missing-key checks.
BREAKDOWN_KEYS: tuple[str, ...] = (
    "flag_deductions",
    "confidence_deductions",
    "unknown_type_penalty",
    "remaining_points",
)


def build_score_breakdown(
    flag_deductions: float = 0.0,
    confidence_deductions: float = 0.0,
    unknown_type_penalty: float = 0.0,
) -> dict[str, float]:
    """Build a full breakdown from deduction lines, zeroing the remainder."""
    remaining = max(0.0, 100.0 - flag_deductions - confidence_deductions - unknown_type_penalty)
    return {
        "flag_deductions": round(flag_deductions, 2),
        "confidence_deductions": round(confidence_deductions, 2),
        "unknown_type_penalty": round(unknown_type_penalty, 2),
        "remaining_points": round(remaining, 2),
    }


class ROIField(BaseModel):
    """One fractional region of interest bound to an extracted-field name."""

    name: str
    x0: float = Field(ge=0.0, le=1.0)
    y0: float = Field(ge=0.0, le=1.0)
    x1: float = Field(ge=0.0, le=1.0)
    y1: float = Field(ge=0.0, le=1.0)


class DocumentTemplate(BaseModel):
    """Template of named fractional ROIs for one document type.

    MRZ documents additionally carry an `mrz_roi` (fractional) selecting
    the band sent down the dedicated MRZ path. Values are always fractional
    (0.0-1.0) -- documents are normalized to arbitrary resolutions upstream.
    """

    document_type: DocumentType
    rois: list[ROIField] = Field(default_factory=list)
    mrz_roi: Optional[ROIField] = None