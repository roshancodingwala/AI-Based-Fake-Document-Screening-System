"""Document rule engine: data-driven, document-type-aware checks.

Everything here operates on EXTRACTED data (field maps + an already parsed
MRZ) and NEVER touches an image. This is the layer between extraction and
scoring: it converts raw observations into `ValidationFlag`s.

Checks provided:
  * required-field presence   (per document type, data-driven)
  * document-number format    (loose/ILLUSTRATIVE per type)
  * MRZ compliance            (check digits reported by mrz_parser)
  * cross-source consistency  (MRZ vs visual-zone OCR, comparing actual
                               calendar dates, not raw strings)
  * blacklist lookup          (via an injected lookup function -- no DB/API
                               dependency lives in this module)

PHILOSOPHY: every flag is evidence with a severity, never a verdict. A
composite-MRZ failure is phrased as "OCR error, handling damage, or
alteration" -- never asserted as tampering.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, Dict, Mapping, Optional, Sequence, Tuple

from mrz_parser import MRZResult, mrz_yyyymmdd_to_iso
from schemas import (
    BarcodeResult,
    DocumentType,
    ExtractedField,
    FieldSource,
    Severity,
    ValidationFlag,
)
from verhoeff import verify_verhoeff

# ---------------------------------------------------------------------------
# Data-driven required fields per document type.
#
# Keys follow the module-wide field-name vocabulary (see README):
#   document_number, surname (primary identifier), given_names, sex,
#   nationality, date_of_birth (ISO), date_of_expiry (ISO), place_of_birth ...
#
# UNKNOWN intentionally has NO required fields: an unrecognized document has
# no known schema. Scoring penalises UNKNOWN elsewhere; it must never be
# forced into the nearest known type here.
# ---------------------------------------------------------------------------
REQUIRED_FIELDS: Dict[DocumentType, Tuple[str, ...]] = {
    DocumentType.PASSPORT: (
        "document_number", "surname", "given_names", "date_of_birth",
        "date_of_expiry", "nationality",
    ),
    DocumentType.ID_CARD: (
        "document_number", "surname", "given_names", "date_of_birth",
        "date_of_expiry",
    ),
    DocumentType.NATIONAL_ID: (
        "document_number", "surname", "date_of_birth",
    ),
    DocumentType.DRIVING_LICENSE: (
        "document_number", "surname", "date_of_birth", "date_of_expiry",
    ),
    DocumentType.VOTER_ID: (
        "document_number", "surname", "date_of_birth",
    ),
    DocumentType.PAN_CARD: (
        "document_number", "surname", "date_of_birth",
    ),
    DocumentType.AADHAAR: (
        "document_number", "surname", "date_of_birth",
    ),
    DocumentType.RESIDENCE_PERMIT: (
        "document_number", "surname", "date_of_birth", "date_of_expiry",
    ),
    DocumentType.UNKNOWN: (),
}

# ---------------------------------------------------------------------------
# Loose, ILLUSTRATIVE document-number formats.
#
# These are intentionally permissive and are NOT authoritative. They must be
# validated against the real issuing authority specifications for each
# document type before being relied upon (see README "What remains
# unverified"). The '<' filler (present in MRZ-sourced numbers) is stripped
# before matching so the same rule works for MRZ and visual-zone values.
# ---------------------------------------------------------------------------
_DIGITS_12 = re.compile(r"^\d{12}$")
_PAN = re.compile(r"^[A-Z]{5}\d{4}[A-Z]$")
_PASSPORT = re.compile(r"^[A-Z]{1,3}[A-Z0-9]{5,8}$")
_VOTER = re.compile(r"^[A-Z]{3}\d{7}$|^[A-Z0-9]{10}$")
_DL = re.compile(r"^[A-Z]{2}\d{2}\d{7,11}$")
_GENERIC_ALNUM = re.compile(r"^[A-Z0-9]{4,20}$")

DOCUMENT_NUMBER_PATTERNS: Dict[DocumentType, Optional[re.Pattern]] = {
    DocumentType.AADHAAR: _DIGITS_12,
    DocumentType.PAN_CARD: _PAN,
    DocumentType.PASSPORT: _PASSPORT,
    DocumentType.VOTER_ID: _VOTER,
    DocumentType.DRIVING_LICENSE: _DL,
    DocumentType.ID_CARD: _GENERIC_ALNUM,
    DocumentType.NATIONAL_ID: _GENERIC_ALNUM,
    DocumentType.RESIDENCE_PERMIT: _GENERIC_ALNUM,
    DocumentType.UNKNOWN: None,
}


# ---------------------------------------------------------------------------
# Per-document-type validation strategy.
#
# Every type is read through its own evidence channels (this is what drives
# field assembly upstream and, on the scoring side, which flags are even
# possible). ``channels`` lists the sources the type normally carries;
# ``anchor`` names the *secure machine-readable channel* that SHOULD be
# present -- a missing anchor is evidence (capture failure, legacy variant,
# or a forged copy without the zone), never a verdict. ``checksum`` names
# the checksum that applies to the type's number, if any. No MRZ/Verhoeff
# check ever runs on a type that cannot carry one (that is what produces
# nonsense false negatives).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DocumentStrategy:
    channels: Tuple[str, ...] = ()
    anchor: Optional[str] = None
    checksum: Optional[str] = None


DOCUMENT_STRATEGY: Dict[DocumentType, DocumentStrategy] = {
    DocumentType.PASSPORT: DocumentStrategy(
        channels=("mrz", "visual"), anchor="mrz", checksum=None,
    ),
    DocumentType.ID_CARD: DocumentStrategy(
        channels=("mrz", "visual"), anchor="mrz", checksum=None,
    ),
    DocumentType.NATIONAL_ID: DocumentStrategy(
        channels=("visual", "template"), anchor=None, checksum=None,
    ),
    DocumentType.AADHAAR: DocumentStrategy(
        channels=("visual", "qr"), anchor="aadhaar_qr", checksum="verhoeff",
    ),
    DocumentType.PAN_CARD: DocumentStrategy(
        channels=("visual", "template"), anchor=None, checksum=None,
    ),
    DocumentType.DRIVING_LICENSE: DocumentStrategy(
        channels=("visual", "barcode", "template"), anchor="dl_barcode",
        checksum=None,
    ),
    DocumentType.VOTER_ID: DocumentStrategy(
        channels=("visual", "template"), anchor=None, checksum=None,
    ),
    DocumentType.RESIDENCE_PERMIT: DocumentStrategy(
        channels=("mrz", "visual"), anchor="mrz", checksum=None,
    ),
    DocumentType.UNKNOWN: DocumentStrategy(channels=(), anchor=None, checksum=None),
}


def _flag(code: str, message: str, severity: Severity, field: Optional[str] = None) -> ValidationFlag:
    return ValidationFlag(code=code, message=message, severity=severity, field=field)


def _clean_document_number(value: str) -> str:
    """Strip MRZ filler '<' so MRZ and visual values compare on equal footing."""
    return value.replace("<", "")


# ---------------------------------------------------------------------------
# Required-field presence
# ---------------------------------------------------------------------------
def check_required_fields(
    document_type: DocumentType,
    fields: Mapping[str, ExtractedField],
    input_side: str = "",
) -> Sequence[ValidationFlag]:
    flags: list[ValidationFlag] = []
    required = REQUIRED_FIELDS.get(document_type, ())
    if document_type == DocumentType.AADHAAR and input_side == "back":
        # The physical BACK of an Aadhaar card prints no holder name or DOB
        # (only the guardian name/address and the QR). Those fields arrive as
        # machine data inside the QR instead -- demanding them as visual-OCR
        # fields would penalise an honest back-only capture.
        required = ()
    for name in required:
        field = fields.get(name)
        if field is None or not field.value.strip():
            flags.append(_flag(
                "missing_required_field",
                f"Required field '{name}' was not extracted or is blank. "
                "Could be OCR failure, an unusual layout, or an altered "
                "document -- verify against the image.",
                Severity.WARNING, name,
            ))
    return flags


# ---------------------------------------------------------------------------
# Document-number format
# ---------------------------------------------------------------------------
def check_document_number_format(
    document_type: DocumentType,
    fields: Mapping[str, ExtractedField],
) -> Sequence[ValidationFlag]:
    pattern = DOCUMENT_NUMBER_PATTERNS.get(document_type)
    if pattern is None:
        return []
    field = fields.get("document_number")
    if field is None or not field.value.strip():
        return []  # absence is reported by required-field checks
    value = _clean_document_number(field.value.strip())
    if not pattern.match(value):
        return [_flag(
            "document_number_format",
            f"Document number '{field.value}' does not match the illustrative "
            f"format expected for {document_type.value} documents. This is a "
            "loose pattern check -- either a misread, a format variation, or "
            "the numbering scheme is different from expected.",
            Severity.WARNING, "document_number",
        )]
    return []


# ---------------------------------------------------------------------------
# PAN structure (strict)
# ---------------------------------------------------------------------------
#: PAN position 4 = holder status (documented Income-tax codes).
_PAN_STATUS_CODES = frozenset("CPHFATBLJG")

#: Weights for the reverse-engineered mod-36 PAN check character.
_PAN_MOD36_WEIGHTS = (1, 2, 3, 4, 5, 6, 7, 8, 9)


def _pan_mod36_check_char(number: str) -> str:
    """Reverse-engineered mod-36 check character over positions 1-9.

    Widely implemented in PAN validators but NOT an officially documented
    Income-tax algorithm -- treated as heuristic evidence, never a verdict.
    """
    total = 0
    for ch, weight in zip(number[:9], _PAN_MOD36_WEIGHTS):
        value = int(ch) if ch.isdigit() else ord(ch) - ord("A") + 10
        total += value * weight
    mod = total % 36
    return str(mod) if mod < 10 else chr(ord("A") + mod - 10)


def _pan_card_initials(name: str) -> set[str]:
    """Likely initials for the PAN 5th char from a printed name.

    For individuals the 5th char is the first letter of the surname (last
    word); for companies/HUF it is the first letter of the entity name. We
    accept either, keeping the check strict enough to catch a mismatch yet
    tolerant of entity cards.
    """
    words = [w for w in re.sub(r"[^A-Za-z ]", " ", name).upper().split() if w]
    if not words:
        return set()
    return {words[0][0], words[-1][0]}


def check_pan_structure(
    fields: Mapping[str, ExtractedField],
) -> Sequence[ValidationFlag]:
    """Strict structural validation of an Indian PAN (10 characters):

      * positions 1-3  -- alphabetic (name / entity abbreviation)
      * position   4   -- holder status: one of C P H F A T B L J G
      * position   5   -- alphabetic (first letter of surname / entity)
      * positions 6-9  -- digits (sequence)
      * position   10  -- alphabetic check char (mod-36 heuristic)

    Position 5 is also cross-checked against the first letter of the
    extracted card holder name. PAN has no machine-readable zone, so these
    structure rules ARE its primary forensic signal; failures are WARNING
    evidence for the officer, never a verdict.
    """
    flags: list[ValidationFlag] = []
    field = fields.get("document_number")
    if field is None or not field.value.strip():
        return flags
    number = _clean_document_number(field.value.strip()).upper()

    shape_ok = (
        len(number) == 10
        and number[:3].isalpha()
        and number[4].isalpha()
        and number[5:9].isdigit()
        and number[9].isalpha()
    )
    if not shape_ok:
        return [_flag(
            "pan_structure_invalid",
            f"PAN '{field.value}' does not match the 10-character pattern "
            "(3 letters + holder status + letter + 4 digits + check letter). "
            "A misread or an altered document -- verify against the image.",
            Severity.WARNING, "document_number",
        )]

    if number[3] not in _PAN_STATUS_CODES:
        flags.append(_flag(
            "pan_status_code_invalid",
            f"PAN holder-status character '{number[3]}' is not a valid "
            f"status code ({', '.join(sorted(_PAN_STATUS_CODES))}).",
            Severity.WARNING, "document_number",
        ))

    name = fields.get("surname")
    if name is not None and name.value.strip():
        initials = _pan_card_initials(name.value)
        if initials and number[4] not in initials:
            flags.append(_flag(
                "pan_name_char_mismatch",
                f"PAN 5th character '{number[4]}' does not match the first "
                f"letter of the printed name '{name.value.strip()}'. Either an "
                "OCR misread or a card whose name and PAN do not belong "
                "together.",
                Severity.WARNING, "document_number",
            ))
        elif initials:
            flags.append(_flag(
                "pan_name_char_match",
                f"PAN 5th character '{number[4]}' agrees with the first "
                "letter of the printed name.",
                Severity.INFO, "document_number",
            ))

    expected = _pan_mod36_check_char(number)
    if expected == number[9]:
        flags.append(_flag(
            "pan_checksum_ok",
            "PAN matches its mod-36 check character (reverse-engineered "
            "heuristic, not an official Income-tax algorithm).",
            Severity.INFO, "document_number",
        ))
    else:
        flags.append(_flag(
            "pan_checksum_failed",
            f"PAN check character expected '{expected}' but position 10 is "
            f"'{number[9]}'. Either a misread, a genuine misprint, or an "
            "altered number -- verify against the image.",
            Severity.WARNING, "document_number",
        ))
    return flags


# ---------------------------------------------------------------------------
# MRZ compliance (check digits from mrz_parser)
# ---------------------------------------------------------------------------
def check_mrz_compliance(mrz: Optional[MRZResult]) -> Sequence[ValidationFlag]:
    flags: list[ValidationFlag] = []
    if mrz is None:
        return flags
    if not mrz.recognized:
        flags.append(_flag(
            "mrz_unrecognized",
            "An MRZ band seems present but could not be parsed (bad line "
            "lengths or illegal characters). Could be OCR failure or an "
            "unusual MRZ -- verify against the image.",
            Severity.WARNING, "mrz",
        ))
        return flags

    mrz_found = any(
        field == "composite" for field in mrz.check_digits
    ) or bool(mrz.check_digits)

    failures = {k: v for k, v in mrz.check_digits.items() if not v}
    if failures:
        if "composite" in failures:
            flags.append(_flag(
                "mrz_composite_check_failed",
                "The MRZ composite check digit does not verify against the "
                "printed data. This can be caused by OCR error, physical "
                "damage to the document, OR alteration -- the available "
                "evidence does not distinguish these.",
                Severity.HIGH, "mrz",
            ))
        for field in (k for k in sorted(failures.keys()) if k != "composite"):
            flags.append(_flag(
                "mrz_field_check_failed",
                f"The MRZ check digit for '{field}' does not verify. This can "
                "be caused by OCR error, physical damage, OR alteration.",
                Severity.WARNING, field,
            ))
    elif mrz_found:
        flags.append(_flag(
            "mrz_checks_verified",
            "All MRZ check digits (including the composite) verify against "
            "the printed data.",
            Severity.INFO, "mrz",
        ))
    return flags


# ---------------------------------------------------------------------------
# Cross-source (MRZ vs visual-zone OCR) consistency
# ---------------------------------------------------------------------------
_VISUAL_DATE_FORMATS = (
    "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d",
    "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y",
)


def parse_visual_date(value: str) -> Optional[date]:
    """Best-effort parse of a date as it appears in the visual zone.

    Supports ISO and common DD-MM-YYYY variants (Indian documents usually
    print day-first). Returns None when unparseable -- missing parsing is
    NOT a mismatch; it just disables the comparison.
    """
    value = value.strip()
    for fmt in _VISUAL_DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


_MRZ_ISO_KEYS = {
    "date_of_birth": "date_of_birth",
    "date_of_expiry": "date_of_expiry",
}


def check_cross_source_consistency(
    mrz: Optional[MRZResult],
    fields: Mapping[str, ExtractedField],
    reference_year: Optional[int] = None,
) -> Sequence[ValidationFlag]:
    """Compare MRZ fields against visual-zone OCR fields.

    Dates are compared as CALENDAR dates: the MRZ's 2-digit year is resolved
    with century inference and compared against the parsed visual date.
    Comparing raw digit strings instead would falsely flag identical values
    (e.g. '1974-08-12' vs MRZ '740812') as mismatches.
    """
    if mrz is None or not mrz.recognized:
        return []
    if reference_year is None:
        reference_year = date.today().year

    flags: list[ValidationFlag] = []

    for mrz_key, visual_key in _MRZ_ISO_KEYS.items():
        mrz_raw = mrz.data.get(mrz_key)
        visual = fields.get(visual_key)
        if (
            not mrz_raw or visual is None or not visual.value.strip()
        ):
            continue  # lack of a side disables the comparison
        # DOB year resolution biases to the past; expiry resolves to the
        # nearest century, matching how the field layer built the IS value.
        prefer_past = mrz_key == "date_of_birth"
        mrz_iso = mrz_yyyymmdd_to_iso(mrz_raw, reference_year, prefer_past=prefer_past)
        visual_date = parse_visual_date(visual.value)
        if mrz_iso is None or visual_date is None:
            continue
        mrz_date = date.fromisoformat(mrz_iso)
        if mrz_date != visual_date:
            flags.append(_flag(
                "cross_source_date_mismatch",
                f"{mrz_key} differs between the MRZ ({mrz_iso}) and the "
                f"visual zone ({visual.value}). The two zones disagree -- "
                "this is evidence of a reading problem or altered document; "
                "verify against the image.",
                Severity.WARNING, visual_key,
            ))

    # document number cross-source
    mrz_num = mrz.data.get("document_number")
    visual_num = fields.get("document_number")
    if (
        mrz_num and visual_num and visual_num.value.strip()
        and visual_num.source == FieldSource.VISUAL
    ):
        a = _clean_document_number(mrz_num)
        b = _clean_document_number(visual_num.value.strip()).upper()
        if a and a != b:
            flags.append(_flag(
                "cross_source_number_mismatch",
                f"Document number differs between MRZ ('{mrz_num}') and "
                f"visual zone ('{visual_num.value}'). Zones disagree -- verify "
                "against the image.",
                Severity.WARNING, "document_number",
            ))
    return flags


# ---------------------------------------------------------------------------
# Blacklist check -- injected lookup, no hardcoded DB/API dependency
# ---------------------------------------------------------------------------
BlacklistLookup = Callable[[Mapping[str, str]], Optional[bool]]


def build_blacklist_query(fields: Mapping[str, ExtractedField]) -> Dict[str, str]:
    """Build a small query dict for the injected blacklist lookup."""
    query: Dict[str, str] = {}
    for key in ("document_number", "surname", "given_names"):
        field = fields.get(key)
        if field is not None and field.value.strip():
            query[key] = field.value.strip()
    return query


def run_blacklist_check(
    fields: Mapping[str, ExtractedField],
    lookup_fn: Optional[BlacklistLookup],
) -> Sequence[ValidationFlag]:
    """Run the injected blacklist lookup and frame its result neutrally.

    Contract for ``lookup_fn(query: dict[str, str]) -> Optional[bool]``:
      True  -> the record is on the blacklist
      False -> the record is not on the blacklist
      None  -> the lookup could not determine anything (treated as failure)
    Raising an exception is ALSO treated as a (flag-raising) failure.

    A genuine hit is a data-plane finding passed up to Stage 4 for fusion --
    it does NOT by itself decide anything here.
    """
    if lookup_fn is None:
        return [_flag(
            "blacklist_not_configured",
            "No blacklist lookup function was provided; blacklist screening "
            "was skipped.",
            Severity.INFO, None,
        )]

    query = build_blacklist_query(fields)
    if not query:
        return [_flag(
            "blacklist_no_identifiers",
            "Blacklist lookup skipped: no identifying fields were extracted.",
            Severity.INFO, None,
        )]

    try:
        hit = lookup_fn(dict(query))
    except Exception as exc:  # defensive: lookup must not crash the pipeline
        return [_flag(
            "blacklist_lookup_failed",
            f"Blacklist lookup failed ({type(exc).__name__}). This is NOT "
            "treated as a clear record -- manual review recommended. "
            "Failure is reported, not silently swallowed.",
            Severity.WARNING, None,
        )]

    if hit is None:
        return [_flag(
            "blacklist_lookup_failed",
            "Blacklist lookup returned no determination. NOT treated as a "
            "clear record -- manual review recommended.",
            Severity.WARNING, None,
        )]
    if hit is True:
        return [_flag(
            "blacklist_hit",
            "External blacklist lookup reported a match for the extracted "
            "identifiers. Evidence for officer attention / Stage 4 fusion -- "
            "not a verdict by itself.",
            Severity.WARNING, None,
        )]
    return [_flag(
        "blacklist_clear",
        "External blacklist lookup returned no match.",
        Severity.INFO, None,
    )]


# ---------------------------------------------------------------------------
# All-in-one
# ---------------------------------------------------------------------------
def check_aadhaar_number_checksum(
    fields: Mapping[str, ExtractedField],
) -> list[ValidationFlag]:
    """Verify the Verhoeff check digit embedded in a 12-digit Aadhaar number.

    The number is evidence of the DATA plane: a failure means the printed/
    recognized digits do not form a valid Aadhaar number -- caused by OCR
    interference OR a fabricated/duplicate number. It never proves a number
    is genuine (that is what the issuer's database is for), so the passing
    case is informational only.
    """
    field = fields.get("document_number")
    if field is None or not field.value:
        return []
    digits = "".join(ch for ch in str(field.value) if ch.isdigit())
    if len(digits) != 12:
        return []  # partial OCR -- the format rule already flags this shape
    if verify_verhoeff(digits):
        return [_flag(
            "aadhaar_checksum_ok",
            "The 12-digit Aadhaar number passes the Verhoeff checksum. This "
            "confirms structural plausibility only -- it does NOT prove the "
            "number exists or belongs to the holder.",
            Severity.INFO, "document_number",
        )]
    return [_flag(
        "aadhaar_checksum_failed",
        "The Aadhaar number does not pass the Verhoeff checksum. Either the "
        "number was mis-read or it is fabricated/altered -- verify against "
        "the card and the UIDAI database.",
        Severity.HIGH, "document_number",
    )]


# ---------------------------------------------------------------------------
# Secure-machine-anchor + QR/barcode consistency (per-type strategy)
# ---------------------------------------------------------------------------
def _digits(value: str) -> str:
    return "".join(ch for ch in str(value) if ch.isdigit())


def _find_barcode(
    barcodes: Optional[Sequence[BarcodeResult]], channel: str
) -> Optional[BarcodeResult]:
    if not barcodes:
        return None
    return next((b for b in barcodes if b.channel == channel), None)


def check_secure_anchor_presence(
    document_type: DocumentType,
    mrz: Optional[MRZResult],
    barcodes: Optional[Sequence[BarcodeResult]],
    input_side: str = "",
) -> list[ValidationFlag]:
    """Flag when a type's secure machine-readable anchor is absent.

    NOT a verdict: a genuine document can miss its anchor because of a bad
    capture, an older/cheaper variant, or a photograph that failed to
    resolve the zone. It is strong evidence for officer attention because a
    legitimate anchor is precisely what a forged copy usually cannot
    reproduce -- which is why per-type strategies demand it.

    Side-aware downgrade: the Aadhaar QR physically lives on the BACK of the
    card. When the caller reports ``input_side='front'``, a missing anchor is
    *expected* from the geometry, not evidence -- it degrades to an INFO note
    telling the officer to upload the back, so an honest front-only capture
    is never silently penalized.
    """
    strategy = DOCUMENT_STRATEGY.get(document_type)
    anchor = strategy.anchor if strategy else None
    if anchor is None:
        return []
    present = False
    if anchor == "mrz":
        present = mrz is not None and mrz.recognized
    elif anchor in ("aadhaar_qr", "dl_barcode"):
        present = _find_barcode(barcodes, anchor) is not None
    if present:
        return []
    zone = {
        "mrz": "machine-readable zone (MRZ)",
        "aadhaar_qr": "UIDAI-secured QR code",
        "dl_barcode": "2D barcode",
    }.get(anchor, anchor)
    if document_type == DocumentType.AADHAAR and input_side == "front":
        return [_flag(
            "anchor_not_verifiable",
            "The UIDAI QR code physically lives on the BACK of the Aadhaar "
            "card, and the provided photo shows only the FRONT, so this "
            "image cannot carry the secure anchor. Not treated as evidence "
            "of alteration -- upload the back side to verify the QR.",
            Severity.INFO, "machine_readable_zone",
        )]
    return [_flag(
        "secure_anchor_missing",
        f"Classified as {document_type.value}, which normally carries the "
        f"{zone}, but none could be decoded. This can mean a poor capture, a "
        "legacy variant without the zone, OR a forged/altered copy -- it is "
        "evidence, not a verdict; verify against the physical document.",
        Severity.WARNING, "machine_readable_zone",
    )]


def _name_words(value: str) -> list[str]:
    """Split a name into an order-insensitive word list for comparison."""
    return [w for w in re.sub(r"[^A-Za-z]", " ", value.upper()).split() if w]


def _normalise_gender(value: str) -> Optional[str]:
    """Map the many printed spellings of sex/gender onto a canonical token."""
    mapping = {
        "M": "MALE", "MALE": "MALE", "MAIL": "MALE",
        "F": "FEMALE", "FEMALE": "FEMALE", "FMALE": "FEMALE",
        "T": "TRANSGENDER", "TRANS": "TRANSGENDER",
        "TRANSGENDER": "TRANSGENDER", "O": "OTHER", "OTHER": "OTHER",
    }
    return mapping.get(value.strip().upper())


def check_aadhaar_qr_consistency(
    fields: Mapping[str, ExtractedField],
    barcodes: Optional[Sequence[BarcodeResult]],
) -> list[ValidationFlag]:
    """Cross-check the UIDAI QR payload against the OCR'd card.

    The QR is machine-typed and attributed to UIDAI, so it is the
    authoritative side of every comparison. A mismatch between the QR and
    the printed/OCR'd zone is HIGH evidence of OCR error or an altered
    card -- the payload itself carries the signature flag separately.
    """
    qr = _find_barcode(barcodes, "aadhaar_qr")
    if qr is None:
        return []
    flags: list[ValidationFlag] = []

    if qr.signature_present:
        flags.append(_flag(
            "aadhaar_qr_signed_payload",
            "The decoded Aadhaar QR payload carries UIDAI's digital signature "
            "element. (Signature *verification* requires UIDAI's public key "
            "and belongs to a trusted verifier stage.)",
            Severity.INFO, "machine_readable_zone",
        ))

    uid = (qr.data.get("uid") or "").strip()
    if uid:
        if verify_verhoeff(uid):
            flags.append(_flag(
                "aadhaar_qr_checksum_ok",
                "The Aadhaar number inside the QR passes the Verhoeff checksum.",
                Severity.INFO, "document_number",
            ))
        else:
            flags.append(_flag(
                "aadhaar_qr_checksum_failed",
                "The Aadhaar number inside the QR FAILS the Verhoeff checksum. "
                "A machine-read payload that fails structurally is strong "
                "evidence of a fabricated number.",
                Severity.HIGH, "document_number",
            ))

    visual_num = fields.get("document_number")
    if uid and visual_num is not None and visual_num.source != FieldSource.BARCODE:
        if _digits(uid) != _digits(visual_num.value):
            flags.append(_flag(
                "aadhaar_qr_number_mismatch",
                f"Document number differs between the UIDAI QR ('{uid}') and "
                f"the printed/OCR zone ('{visual_num.value}'). This is HIGH "
                "evidence of OCR error or an altered card; verify against the "
                "physical document and UIDAI.",
                Severity.HIGH, "document_number",
            ))

    qr_dob = (qr.data.get("dob") or "").strip()
    visual_dob = fields.get("date_of_birth")
    if qr_dob and visual_dob is not None and visual_dob.source != FieldSource.BARCODE:
        qr_d = parse_visual_date(qr_dob)
        vis_d = parse_visual_date(visual_dob.value)
        if qr_d is not None and vis_d is not None and qr_d != vis_d:
            flags.append(_flag(
                "aadhaar_qr_dob_mismatch",
                f"Date of birth differs between the UIDAI QR ('{qr_dob}') and "
                f"the printed zone ('{visual_dob.value}'). Verify against the "
                "card and UIDAI.",
                Severity.WARNING, "date_of_birth",
            ))

    qr_name = (qr.data.get("name") or "").strip()
    visual_name = fields.get("surname")
    if qr_name and visual_name is not None and visual_name.source != FieldSource.BARCODE:
        qr_words = _name_words(qr_name)
        vis_words = _name_words(visual_name.value)
        if qr_words and vis_words:
            if sorted(qr_words) == sorted(vis_words):
                flags.append(_flag(
                    "aadhaar_qr_name_match",
                    "The name in the UIDAI QR agrees with the printed name on "
                    "the card.",
                    Severity.INFO, "surname",
                ))
            else:
                flags.append(_flag(
                    "aadhaar_qr_name_mismatch",
                    f"Name differs between the UIDAI QR ('{qr_name}') and the "
                    f"printed zone ('{visual_name.value}'). Could be an OCR "
                    "misread or a card whose name does not belong to its QR -- "
                    "verify against the physical document.",
                    Severity.WARNING, "surname",
                ))

    qr_gender = _normalise_gender((qr.data.get("gender") or "").strip())
    visual_gender = fields.get("sex")
    if qr_gender and visual_gender is not None and visual_gender.source != FieldSource.BARCODE:
        vis_gender = _normalise_gender(visual_gender.value)
        if vis_gender:
            if vis_gender == qr_gender:
                flags.append(_flag(
                    "aadhaar_qr_gender_match",
                    "The gender in the UIDAI QR agrees with the printed gender.",
                    Severity.INFO, "sex",
                ))
            else:
                flags.append(_flag(
                    "aadhaar_qr_gender_mismatch",
                    f"Gender differs between the UIDAI QR ('{qr.data['gender']}') "
                    f"and the printed zone ('{visual_gender.value}'). Verify "
                    "against the card and UIDAI.",
                    Severity.WARNING, "sex",
                ))
    return flags


def check_dl_barcode_consistency(
    fields: Mapping[str, ExtractedField],
    barcodes: Optional[Sequence[BarcodeResult]],
) -> list[ValidationFlag]:
    """Cross-check the smart-card barcode against the OCR'd licence."""
    barcode = _find_barcode(barcodes, "dl_barcode")
    if barcode is None:
        return []
    flags: list[ValidationFlag] = []

    barcode_num = (barcode.data.get("document_number") or "").strip()
    visual_num = fields.get("document_number")

    if barcode_num and visual_num is not None and visual_num.source != FieldSource.BARCODE:
        a = barcode_num.upper()
        b = _clean_document_number(visual_num.value.strip()).upper()
        if a and a != b:
            flags.append(_flag(
                "dl_barcode_number_mismatch",
                f"Licence number differs between the card barcode ('{a}') and "
                f"the printed zone ('{visual_num.value}'). Evidence of a "
                "misread or an altered card; verify against the physical "
                "document.",
                Severity.HIGH, "document_number",
            ))

    barcode_dob = (barcode.data.get("date_of_birth") or "").strip()
    visual_dob = fields.get("date_of_birth")
    if barcode_dob and visual_dob is not None and visual_dob.source != FieldSource.BARCODE:
        b_d = parse_visual_date(barcode_dob)
        v_d = parse_visual_date(visual_dob.value)
        if b_d is not None and v_d is not None and b_d != v_d:
            flags.append(_flag(
                "dl_barcode_dob_mismatch",
                f"Date of birth differs between the card barcode "
                f"('{barcode_dob}') and the printed zone ('{visual_dob.value}').",
                Severity.WARNING, "date_of_birth",
            ))
    return flags


def run_all_rules(
    document_type: DocumentType,
    fields: Mapping[str, ExtractedField],
    mrz: Optional[MRZResult] = None,
    lookup_fn: Optional[BlacklistLookup] = None,
    reference_year: Optional[int] = None,
    barcodes: Optional[Sequence[BarcodeResult]] = None,
    input_side: str = "",
) -> list[ValidationFlag]:
    """Run every document rule and flatten all flags."""
    flags: list[ValidationFlag] = []
    flags.extend(check_required_fields(document_type, fields, input_side=input_side))
    flags.extend(check_document_number_format(document_type, fields))
    if document_type == DocumentType.AADHAAR:
        flags.extend(check_aadhaar_number_checksum(fields))
        flags.extend(check_aadhaar_qr_consistency(fields, barcodes))
    if document_type == DocumentType.DRIVING_LICENSE:
        flags.extend(check_dl_barcode_consistency(fields, barcodes))
    if document_type == DocumentType.PAN_CARD:
        flags.extend(check_pan_structure(fields))
    flags.extend(check_secure_anchor_presence(document_type, mrz, barcodes, input_side))
    flags.extend(check_mrz_compliance(mrz))
    flags.extend(
        check_cross_source_consistency(mrz, fields, reference_year)
    )
    flags.extend(run_blacklist_check(fields, lookup_fn))
    return flags