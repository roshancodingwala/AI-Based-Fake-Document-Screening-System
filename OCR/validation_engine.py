"""Validation engine: orchestrates preprocessing -> OCR -> MRZ -> fields ->
classification -> rules + logical validation -> scoring.

This is the ONLY module that wires the phases together. Everything under it
is decoupled: extraction produces facts, rules produce evidence flags, and
scoring derives a 0-100 data-coherence score. The engine NEVER emits a
fraud/genuine verdict -- its output is a ``DocumentValidationResult`` full
of evidence-flagged findings for an officer and later stages.

Invariants honored here (each enforced by tests):
  * ``UNKNOWN`` document type is scored with a named penalty, never coerced
    into the nearest known type.
  * The blacklist lookup is injected; a missing/None/failing lookup is
    surfaced as a flag (never silently swallowed, never a clear).
  * The engine degrades gracefully: a bad image or missing OCR backend
    produces a result with flags, not an exception.
  * Score deductions come only from named, calibrated constants; the
    ``score_breakdown`` always carries all canonical keys.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Callable, Dict, Mapping, Optional, Sequence, Tuple

import numpy as np

from barcode_extractor import BarcodeExtractor, fields_from_barcode_result
from document_rules import BlacklistLookup, run_all_rules
from logical_validator import validate_dates
from mrz_parser import (
    MRZFormat,
    MRZResult,
    detect_format,
    mrz_yyyymmdd_to_iso,
    parse_mrz,
)
from ocr_extractor import MockOCRExtractor, OCRTextLine, cv2_gray_to_bgr
from preprocessing import PreprocessedDocument, preprocess_image
from schemas import (
    BREAKDOWN_KEYS,
    BarcodeResult,
    DocumentTemplate,
    DocumentType,
    DocumentValidationResult,
    ExtractedField,
    FieldSource,
    MRZResult as SchemasMRZResult,
    Severity,
    ValidationFlag,
    build_score_breakdown,
)
from template_recognizer import engine_ocr_crop, recognize_template_fields

# ---------------------------------------------------------------------------
# Scoring calibration -- STARTING VALUES.
#
# Deductions are deliberately capped so that a stack of modest findings can
# never silently zero a document; the 0-100 score is a data-coherence measure
# for triage, not a fraud probability.
# ---------------------------------------------------------------------------
#: Deduction per HIGH-severity evidence flag.
HIGH_DEDUCTION: float = 22.0
#: Deduction per WARNING-severity evidence flag.
WARNING_DEDUCTION: float = 8.0
#: Deduction per INFO flag (informational findings do not lower the score).
INFO_DEDUCTION: float = 0.0
#: Cap on the combined flag deduction (bands of bad evidence).
MAX_FLAG_DEDUCTION: float = 60.0
#: Fields below this OCR confidence start deducting.
LOW_CONFIDENCE_THRESHOLD: float = 0.6
#: Per-field confidence deduction while confidence < threshold.
CONFIDENCE_DEDUCTION_PER_FIELD: float = 2.0
#: Cap on total confidence deductions.
MAX_CONFIDENCE_DEDUCTION: float = 10.0
#: Penalty for classifying the document type as UNKNOWN.
UNKNOWN_TYPE_PENALTY: float = 25.0


# ---------------------------------------------------------------------------
# MRZ discovery among arbitrary OCR lines
# ---------------------------------------------------------------------------
def find_mrz_block(line_texts: Sequence[str]) -> Optional[MRZResult]:
    """Locate a parseable MRZ block among OCR line texts.

    OCR often returns extra noise lines above/below the MRZ band, so this
    scans sliding windows of the right shape for each format until one
    detects and parses cleanly. Returns None when no MRZ is found.

    Two passes:
      * exact -- every line has the full printed width (44/36/30); OCR
        retained every filler column, nothing to repair.
      * relaxed -- a window is short only on its RIGHT edge (trailing '<'
        fillers get dropped by OCR more often than interior columns). Every
        line is padded right to the format width and re-tried. If the OCR
        also dropped an INTERIOR character the parse still succeeds, and the
        field/check-digit errors that follow are the honest evidence -- this
        fallback never fabricates a clean reading.
    """
    texts = [
        re.sub(r"\s+", "", t).upper()
        for t in line_texts
        if t and t.strip()
    ]
    #: (format, line count, full width) -- confirmed ICAO widths only.
    _FORMATS = (
        (MRZFormat.TD3, 2, 44),
        (MRZFormat.TD2, 2, 36),
        (MRZFormat.TD1, 3, 30),
    )
    for fmt, n_lines, width in _FORMATS:
        for i in range(len(texts) - n_lines + 1):
            window = texts[i:i + n_lines]
            if detect_format(window) == fmt:
                parsed = parse_mrz(window)
                if parsed.recognized:
                    return parsed
    #: How many right-edge columns OCR is allowed to have dropped before a
    #: window stops being credible for that format.
    MAX_SHORT = 12
    for fmt, n_lines, width in _FORMATS:
        window_size = n_lines
        for i in range(len(texts) - window_size + 1):
            window = texts[i:i + window_size]
            if any(not (width - MAX_SHORT <= len(ln) <= width) for ln in window):
                continue
            padded = [ln.ljust(width, "<") for ln in window]
            if detect_format(padded) != fmt:
                continue
            parsed = parse_mrz(padded)
            if parsed.recognized:
                return parsed
    return None


# ---------------------------------------------------------------------------
# Field assembly from MRZ + visual recognizer
# ---------------------------------------------------------------------------
_MRZ_SIMPLE_FIELDS = {
    "document_number": "document_number",
    "nationality": "nationality",
    "sex": "sex",
    "personal_number": "personal_number",
}
_MRZ_DATE_FIELDS = {
    "date_of_birth": "date_of_birth",
    "date_of_expiry": "date_of_expiry",
}


def _clean_mrz_value(value: str) -> str:
    return value.replace("<", " ").strip()


def fields_from_mrz(
    mrz: Optional[MRZResult],
    reference_year: Optional[int] = None,
) -> Dict[str, ExtractedField]:
    """Derive ``ExtractedField``s (source=MRZ) from a parsed MRZ.

    MRZ dates keep their 2-digit-year layout in ``mrz.data``; here they are
    resolved to ISO dates with century inference for the field layer, while
    ``mrz.data`` remains untouched for granular rule checks.
    """
    if mrz is None or not mrz.recognized:
        return {}
    if reference_year is None:
        reference_year = date.today().year
    out: Dict[str, ExtractedField] = {}
    for src_key, fname in _MRZ_SIMPLE_FIELDS.items():
        value = mrz.data.get(src_key)
        if value:
            out[fname] = ExtractedField(
                name=fname,
                value=_clean_mrz_value(value),
                source=FieldSource.MRZ,
                confidence=1.0,
            )
    for src_key, fname in _MRZ_DATE_FIELDS.items():
        value = mrz.data.get(src_key)
        if value:
            # DOB year resolution biases to the past; expiry resolves to the
            # nearest century so an unexpired document (e.g. YY=35 against a
            # 2026 reference) resolves to 2035, not 1935.
            prefer_past = src_key == "date_of_birth"
            iso = mrz_yyyymmdd_to_iso(value, reference_year, prefer_past=prefer_past)
            out[fname] = ExtractedField(
                name=fname,
                value=iso or _clean_mrz_value(value),
                source=FieldSource.MRZ,
                confidence=1.0,
            )
    identifiers = mrz.identifiers or {}
    primary = identifiers.get("primary_identifier")
    secondary = identifiers.get("secondary_identifiers")
    if primary:
        out["surname"] = ExtractedField(
            name="surname", value=primary, source=FieldSource.MRZ, confidence=1.0
        )
    if secondary:
        out["given_names"] = ExtractedField(
            name="given_names", value=secondary, source=FieldSource.MRZ,
            confidence=1.0,
        )
    return out


def merge_fields(
    visual: Mapping[str, ExtractedField],
    mrz_fields: Mapping[str, ExtractedField],
) -> Dict[str, ExtractedField]:
    """Visual fields take display precedence when both sources agree on a
    name; MRZ fills in the gaps. Where both exist, the visual value stays in
    ``fields`` and the MRZ value remains accessible through
    ``mrz.data`` -- that pairing is what enables cross-source checks."""
    merged = dict(visual)
    for name, field in mrz_fields.items():
        merged.setdefault(name, field)
    return merged


# ---------------------------------------------------------------------------
# Default visual-zone recognizer (label:value lines for common layouts)
# ---------------------------------------------------------------------------
_VISUAL_PATTERNS: Tuple[Tuple[re.Pattern, str], ...] = (
    (re.compile(r"(?i)\b([0-9]{12})\b"), "document_number"),
    (re.compile(r"(?i)document\s*no\.?\s*[:#-]*\s*([A-Z0-9]{5,20})"), "document_number"),
    (re.compile(r"(?i)\b([0-9]{4}[\s-][0-9]{4}[\s-][0-9]{4})\b"), "document_number"),
    (re.compile(r"(?i)aadhaar(?:\s*(?:number|no\.?|uid))?\s*[:#-]*\s*([0-9]{4}[\s-]?[0-9]{4}[\s-]?[0-9]{4})"), "document_number"),
    (re.compile(r"(?i)permanent\s+account\s+(?:number|no\.?)\s*[:#-]*\s*([A-Z]{5}\d{4}[A-Z])"), "document_number"),
    (re.compile(r"(?i)\b([A-Z]{5}\d{4}[A-Z])\b"), "document_number"),
    (re.compile(r"(?i)(?:licence|license)\s*(?:no\.?|number)?\s*[:#-]*\s*([A-Z]{2}\d{2}\d{7,11})"), "document_number"),
    (re.compile(r"(?i)\b([A-Z]{2}\d{2}\d{7,11})\b"), "document_number"),
    (re.compile(r"(?i)(?:date\s*[o0]\s*f\s*birth|dob|d0b)\s*[:#-]*\s*([0-9-./]{8,10})"), "date_of_birth"),
    (re.compile(r"(?i)(?:date\s*of\s*(?:expiry|expiration)|valid\s*(?:till|until|through))\s*[:#-]*\s*([0-9-./]{8,10})"), "date_of_expiry"),
    (re.compile(r"(?i)(?:issue(?:d|date)?|date\s*of\s*issue)\s*[:#-]*\s*([0-9-./]{8,10})"), "issue_date"),
    (re.compile(r"(?im)^\s*(?:name|full\s*name)\s*[:#-]*\s*([A-Z][A-Z\s.]{2,40})"), "surname"),
    (re.compile(r"(?i)(?:sex|gender)\s*[:#-]*\s*(male|female|M|F)\b"), "sex"),
    (re.compile(r"(?i)^\s*((?:male|female))\b"), "sex"),
)

#: Labels frequently appear on their own OCR line with the value on the next
#: line (or the next few lines). (label_re, field, multi_fragment)
_VISUAL_NEXT_LINE: Tuple[Tuple[re.Pattern, str, bool], ...] = (
    (re.compile(r"(?im)^\s*(?:name|full\s*name)\b"), "surname", False),
    (re.compile(r"(?im)^\s*(?:dob|date\s*[o0]\s*f\s*birth)\b"), "date_of_birth", False),
    (re.compile(r"(?im)^\s*(?:sex|gender)\b"), "sex", False),
    (re.compile(r"(?im)^\s*(?:your\s+aadhaar\s*number|aadhaar(?:\s*(?:number|no\.?|uid))?)\b"),
     "document_number", True),
    (re.compile(r"(?im)^\s*document\s*no\.?\b"), "document_number", False),
    (re.compile(r"(?im)^\s*(?:date\s*of\s*(?:expiry|expiration)|valid\s*(?:till|until|through))\b"),
     "date_of_expiry", False),
)

_LABEL_RES = [re for re, _, _ in _VISUAL_NEXT_LINE]

_AADHAAR_CONTEXT = ("aadhaar", "uidai", "unique identification")

#: Lines that look like boilerplate, never like holder names.
_SKIP_AS_NAME = re.compile(
    r"(?i)^(?:aadhaar|it|or|authentication|and|government|unique|date|this|proof)"
)


def _is_pure_label(text: str) -> bool:
    return any(re.search(text) for re in _LABEL_RES)


def _value_ok(name: str, text: str) -> bool:
    """Does this OCR line plausibly carry the *value* (not a stray fragment)
    for the field the previous label line announced?

    Guards the next-line strategy against pulling in a neighbouring token
    ('PHOTO' beside a DoB row, for example). Field types with an unambiguous
    value shape only accept matching lines; prose fields accept any line.
    """
    t = text.strip()
    if name == "date_of_birth":
        return bool(re.search(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{4}", t)) or \
            bool(re.match(r"^\s*\d{4}\s*$", t))
    if name == "date_of_expiry":
        return bool(re.search(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{4}", t))
    if name == "sex":
        return bool(re.match(r"(?i)^(?:male|female|transgender)$", t))
    if name == "document_number":
        return len(re.sub(r"[^A-Z0-9]", "", t)) >= 4
    return True


def default_visual_recognizer(
    lines: Sequence[OCRTextLine],
) -> Dict[str, ExtractedField]:
    """Conservative label-value recognizer for the visual zone.

    Two strategies, applied in order (first match wins per field):
      1. same-line ``label: value`` patterns (``_VISUAL_PATTERNS``);
      2. label-only lines that carry their value on the FOLLOWING line(s)
         (``_VISUAL_NEXT_LINE``) -- common with real OCR engines that split
         printed label rows. Multi-fragment values (e.g. a 12-digit Aadhaar
         number printed in 4+4+4 groups that OCR breaks into pieces) are
         joined left-to-right by bounding-box x so digit order is preserved.

    Unrecognized lines are ignored. This is ILLUSTRATIVE -- real deployments
    bring a template-based ROI recognizer (``schemas.DocumentTemplate``).
    """
    fields: Dict[str, ExtractedField] = {}
    rows = [(line.text, line.confidence, line.bbox) for line in lines]

    def set_field(name, value, confidence, bbox):
        fields.setdefault(
            name,
            ExtractedField(
                name=name,
                value=value,
                source=FieldSource.VISUAL,
                confidence=confidence,
                bbox=bbox,
            ),
        )

    # Strategy 1: same-line patterns.
    for text, conf, bbox in rows:
        for pattern, name in _VISUAL_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue
            value = match.group(1)
            if name == "document_number":
                value = re.sub(r"[^A-Z0-9]", "", value)
            set_field(name, value, conf, bbox)

    # Strategy 2: label line consumes following fragment(s).
    for idx, (text, conf, bbox) in enumerate(rows):
        for label_re, name, multi in _VISUAL_NEXT_LINE:
            if name in fields or not label_re.search(text):
                continue
            following = []
            for nxt_text, nxt_conf, nxt_bbox in rows[idx + 1:]:
                nxt_text = nxt_text.strip()
                if not nxt_text or _is_pure_label(nxt_text):
                    break
                if multi:
                    if sum(len(re.sub(r"[^0-9]", "", t)) for t, _, _ in following) == 0 \
                            and len(re.sub(r"[^0-9]", "", nxt_text)) == 0:
                        break  # number fragments carry digits; don't pull in prose
                    following.append((nxt_text, nxt_conf, nxt_bbox))
                    if sum(len(re.sub(r"[^0-9]", "", t)) for t, _, _ in following) >= 12:
                        break
                elif _value_ok(name, nxt_text):
                    following.append((nxt_text, nxt_conf, nxt_bbox))
                    break
                # else: keep scanning for a value-shaped sibling (a label may
                # sit beside a foreign token on the same row, e.g. 'PHOTO').
            if not following:
                continue
            if multi:
                ordered = sorted(following, key=lambda t: t[2][0] if t[2] else 0.0)
                value = "".join(re.sub(r"[^A-Z0-9]", "", t) for t, _, _ in ordered)
                conf_used = min(conf, min(c for _, c, _ in ordered))
                box = min(ordered, key=lambda t: t[2][0] if t[2] else 0.0)[2]
            else:
                value, conf_used, box = following[0]
            set_field(name, value, conf_used, box)

    # Strategy 3: Aadhaar cards print the holder name with NO label. When the
    # corpus is clearly an Aadhaar card and the name is still missing, take a
    # plausible title-case line (this is why it is scoped to Aadhaar context).
    corpus = " ".join(t for t, _, _ in rows).lower()
    if "surname" not in fields and any(k in corpus for k in _AADHAAR_CONTEXT):
        for text, _conf, bbox in rows:
            cleaned = text.strip()
            words = cleaned.split()
            if not (2 <= len(words) <= 6):
                continue
            if not cleaned[0].isupper() or not cleaned.isalpha() and any(
                    not w.isalpha() for w in words):
                continue
            if _SKIP_AS_NAME.match(cleaned) or _is_pure_label(cleaned):
                continue
            if any(k in cleaned.lower() for k in _AADHAAR_CONTEXT):
                continue
            set_field("surname", cleaned, _conf, bbox)
            break
    return fields


#: Fields a template ROI may *override* when its confidence beats the
#: free-text read. Name-type fields are fill-only: whole-page OCR empirically
#: reads multi-word names ('Keshav Kumar') better than a cropped band, so a
#: higher-confidence-but-wrong ROI read must never push out a good free-text
#: one.
_TEMPLATE_OVERRIDE_FIELDS = frozenset(
    {"document_number", "date_of_birth", "date_of_expiry", "issue_date", "sex"}
)


def merge_template_fields(
    visual: Mapping[str, ExtractedField],
    template_fields: Mapping[str, ExtractedField],
) -> Dict[str, ExtractedField]:
    """Merge structure-aware ROI results over the free-text visual fields.

    Template crops fill every missing name. For names both sources produce,
    the template wins only when the field is ``_TEMPLATE_OVERRIDE_FIELDS``
    AND its confidence beats the existing value; name-type fields are
    fill-only. MRZ fields are never touched here.
    """
    merged = dict(visual)
    for name, template_field in template_fields.items():
        visual_field = merged.get(name)
        if visual_field is None:
            merged[name] = template_field
        elif (
            name in _TEMPLATE_OVERRIDE_FIELDS
            and template_field.confidence > visual_field.confidence
        ):
            merged[name] = template_field
    return merged


# ---------------------------------------------------------------------------
# Document-type classification
# ---------------------------------------------------------------------------
_TYPE_HINT_KEYWORDS: Dict[DocumentType, Tuple[str, ...]] = {
    DocumentType.AADHAAR: ("aadhaar", "unique identification", "uidai",
                            "unique identification authority", "government of india"),
    DocumentType.PAN_CARD: ("permanent account number", "income tax", "pan card"),
    DocumentType.DRIVING_LICENSE: ("driving licence", "driving license", "motor vehicle"),
    DocumentType.VOTER_ID: ("elector", "voter id", "election commission"),
    DocumentType.RESIDENCE_PERMIT: ("residence permit",),
    DocumentType.NATIONAL_ID: ("national id", "civil registration"),
    DocumentType.PASSPORT: ("passport", "ministry of external affairs"),
}

VisualRecognizer = Callable[[Sequence[OCRTextLine]], Dict[str, ExtractedField]]
TypeHintsFn = Callable[[Sequence[OCRTextLine]], Dict[DocumentType, float]]


def default_type_hints(lines: Sequence[OCRTextLine]) -> Dict[DocumentType, float]:
    """Keyword-occupancy scores per type from OCR line text (0.0-1.0)."""
    text = " ".join(line.text for line in lines).lower()
    hints: Dict[DocumentType, float] = {}
    for doc_type, keywords in _TYPE_HINT_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in text)
        if hits:
            hints[doc_type] = min(0.7, 0.3 + 0.15 * hits)
    return hints


def classify_document(
    mrz: Optional[MRZResult],
    hints: Mapping[DocumentType, float],
) -> Tuple[DocumentType, float]:
    """Classify from MRZ type code first, visual hints second.

    UNKNOWN is first-class: an unrecognized MRZ type char or a hint-less
    visual zone yields UNKNOWN (penalized in scoring) -- never a forced jump
    to the nearest known type.
    """
    if mrz is not None and mrz.recognized:
        type_char = _clean_mrz_value(mrz.data.get("document_type") or "").upper()
        if type_char == "P":
            return DocumentType.PASSPORT, 0.98
        if type_char in ("I", "ID"):
            return DocumentType.ID_CARD, 0.9
        return DocumentType.UNKNOWN, 0.5
    if hints:
        best = max(hints, key=hints.get)
        return best, min(0.8, hints[best] + 0.3)
    return DocumentType.UNKNOWN, 0.0


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def compute_score(
    flags: Sequence[ValidationFlag],
    fields: Mapping[str, ExtractedField],
    document_type: DocumentType,
) -> Tuple[int, Dict[str, float], list[dict]]:
    """Calibrated 0-100 data-coherence score from evidence + deductions.

    Returns ``(score, breakdown, ledger)``; ``ledger`` is one traced row per
    named deduction (flag, low-confidence field, unknown penalty) with points
    removed and running balance so downstream UIs can render exactly why and
    where points left the document.
    """
    counts = {Severity.HIGH: 0, Severity.WARNING: 0, Severity.INFO: 0}
    for flag in flags:
        counts[flag.severity] = counts.get(flag.severity, 0) + 1

    ledger: list[dict] = []
    balance = 100.0
    flag_pool = MAX_FLAG_DEDUCTION
    for flag in flags:
        nominal = {
            Severity.HIGH: HIGH_DEDUCTION,
            Severity.WARNING: WARNING_DEDUCTION,
            Severity.INFO: INFO_DEDUCTION,
        }[flag.severity]
        applied = min(nominal, flag_pool)
        flag_pool -= applied
        balance -= applied
        reason = flag.message
        if nominal and applied < nominal:
            reason = reason + " (score capped: flag deductions max -60)"
        ledger.append({
            "code": flag.code,
            "severity": flag.severity.value,
            "reason": reason,
            "deduction": round(applied, 2),
            "balance": round(balance, 2),
        })

    flag_deductions = min(
        MAX_FLAG_DEDUCTION,
        counts[Severity.HIGH] * HIGH_DEDUCTION
        + counts[Severity.WARNING] * WARNING_DEDUCTION
        + counts[Severity.INFO] * INFO_DEDUCTION,
    )

    low_conf = [
        f for f in fields.values() if f.confidence < LOW_CONFIDENCE_THRESHOLD
    ]
    confidence_pool = MAX_CONFIDENCE_DEDUCTION
    for field in low_conf:
        applied = min(CONFIDENCE_DEDUCTION_PER_FIELD, confidence_pool)
        confidence_pool -= applied
        balance -= applied
        ledger.append({
            "code": "low_ocr_confidence",
            "severity": "info",
            "reason": (
                f"'{field.name}' read at {field.confidence:.0%} confidence "
                f"(below {LOW_CONFIDENCE_THRESHOLD:.0%})"
            ),
            "deduction": round(applied, 2),
            "balance": round(balance, 2),
        })
    confidence_deductions = min(
        MAX_CONFIDENCE_DEDUCTION,
        len(low_conf) * CONFIDENCE_DEDUCTION_PER_FIELD,
    )

    unknown_type_penalty = UNKNOWN_TYPE_PENALTY if document_type == DocumentType.UNKNOWN else 0.0
    if document_type == DocumentType.UNKNOWN:
        balance -= UNKNOWN_TYPE_PENALTY
        ledger.append({
            "code": "unknown_type_penalty",
            "severity": "info",
            "reason": f"document type could not be recognized ('{document_type.value}')",
            "deduction": round(UNKNOWN_TYPE_PENALTY, 2),
            "balance": round(balance, 2),
        })

    ledger.append({
        "code": "remaining_points",
        "severity": "info",
        "reason": "points left after all named deductions = final score",
        "deduction": 0.0,
        "balance": round(max(0.0, balance), 2),
    })

    breakdown = build_score_breakdown(
        flag_deductions=flag_deductions,
        confidence_deductions=confidence_deductions,
        unknown_type_penalty=unknown_type_penalty,
    )
    score = int(round(breakdown["remaining_points"]))
    return score, breakdown, ledger


# ---------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------
@dataclass
class EngineOptions:
    """Injection points -- see README for the decoupling rationale."""

    ocr_extractor: Optional[object] = None
    barcode_extractor: Optional[object] = None
    visual_recognizer: Optional[VisualRecognizer] = None
    type_hints_fn: Optional[TypeHintsFn] = None
    blacklist_lookup: Optional[BlacklistLookup] = None
    reference_date: Optional[date] = None
    templates: Sequence[DocumentTemplate] = ()
    #: Channel toggles for manual mode selection (1=OCR+QR, 2=MRZ, 3=all).
    skip_mrz: bool = False
    skip_visual: bool = False
    skip_barcodes: bool = False
    #: Which physical side(s) of the document the image shows. The Aadhaar QR
    #: lives on the BACK, so 'front' downgrades a missing anchor to a neutral
    #: note instead of evidence. Values: '' (unknown) | 'front' | 'back' | 'both'.
    input_sides: str = ""


class ValidationEngine:
    def __init__(self, options: Optional[EngineOptions] = None) -> None:
        options = options or EngineOptions()
        self.ocr = options.ocr_extractor or MockOCRExtractor()
        self.barcode_extractor = options.barcode_extractor or BarcodeExtractor()
        self.visual_recognizer = options.visual_recognizer or default_visual_recognizer
        self.type_hints_fn = options.type_hints_fn or default_type_hints
        self.blacklist_lookup = options.blacklist_lookup
        self.reference_date = options.reference_date or date.today()
        self.templates = tuple(options.templates)
        self.skip_mrz = options.skip_mrz
        self.skip_visual = options.skip_visual
        self.skip_barcodes = options.skip_barcodes
        self.input_sides = options.input_sides

    # -- public API --------------------------------------------------------
    def validate_image(self, image_bgr: np.ndarray) -> DocumentValidationResult:
        """Full pipeline for a raw BGR image."""
        try:
            preprocessed = preprocess_image(image_bgr)
        except Exception as exc:
            return self._degraded_result(
                f"Image could not be preprocessed ({type(exc).__name__}).",
                "image_preprocessing_failed",
            )
        return self._run(preprocessed)

    def validate_mrz_lines(self, lines: Sequence[str]) -> DocumentValidationResult:
        """Rules + logical + scoring over hand-fed MRZ lines (no image)."""
        mrz = find_mrz_block(list(lines))
        flags, fields, _ = self._assemble(mrz, {})
        return self._score_and_finish(None, mrz, fields, flags, {})

    # -- internals ---------------------------------------------------------
    def _run(self, preprocessed: PreprocessedDocument) -> DocumentValidationResult:
        pipeline_flags: list[ValidationFlag] = []
        try:
            ocr_result = self.ocr.extract(preprocessed)
        except Exception as exc:  # an extractor bug must not crash the engine
            ocr_result = None
            pipeline_flags.append(self._mkflag(
                "ocr_extraction_failed",
                f"OCR extraction crashed ({type(exc).__name__}); MRZ rules "
                "could not run.",
                Severity.WARNING,
            ))
        if ocr_result is not None:
            if not ocr_result.recognized:
                pipeline_flags.append(self._mkflag(
                    "ocr_no_text",
                    f"No text recognized ({ocr_result.message}). Either the "
                    "image is empty or the OCR backend is unavailable.",
                    Severity.WARNING,
                ))
            else:
                pipeline_flags.append(self._mkflag(
                    "ocr_read_from",
                    f"OCR consumed the {ocr_result.read_from} copy per the "
                    "two-copy contract.",
                    Severity.INFO,
                ))

        lines = ocr_result.lines if ocr_result is not None else []
        mrz = find_mrz_block([line.text for line in lines]) if not self.skip_mrz else None
        hints = self.type_hints_fn(lines)
        visual: Dict[str, ExtractedField] = (
            {} if self.skip_visual else self.visual_recognizer(lines)
        )
        if not self.skip_visual:
            visual = self._apply_templates(
                preprocessed, mrz, hints, visual, pipeline_flags
            )
        barcodes = (
            [] if self.skip_barcodes
            else self._read_barcodes(preprocessed, pipeline_flags)
        )
        if not self.skip_barcodes:
            visual = merge_fields(visual, self._barcode_fields(barcodes))
        flags, fields, _ = self._assemble(mrz, visual)
        return self._score_and_finish(
            preprocessed, mrz, fields, pipeline_flags + flags, hints,
            barcodes=barcodes,
        )

    def _apply_templates(
        self,
        preprocessed: PreprocessedDocument,
        mrz: Optional[MRZResult],
        hints: Mapping[DocumentType, float],
        visual: Dict[str, ExtractedField],
        pipeline_flags: list[ValidationFlag],
    ) -> Dict[str, ExtractedField]:
        """Run structure-aware ROI OCR when a registered template matches the
        classified type. Fields are merged (higher confidence wins per name,
        gaps filled); a failing template pass degrades to an info flag --
        the free-text recognizer's output stays as the fallback."""
        if not self.templates:
            return visual
        for_classify = mrz if (mrz is not None and mrz.recognized) else None
        doc_type, _ = classify_document(for_classify, hints)
        matching = [t for t in self.templates if t.document_type == doc_type]
        if not matching:
            return visual
        bgr = cv2_gray_to_bgr(preprocessed.clahe_gray)
        applied = 0
        for template in matching:
            try:
                fields = recognize_template_fields(
                    bgr, template, lambda crop: engine_ocr_crop(self.ocr, crop)
                )
            except Exception as exc:  # a template bug must not crash the engine
                pipeline_flags.append(self._mkflag(
                    "template_roi_failed",
                    f"Template ROI OCR failed ({type(exc).__name__}); fell "
                    "back to the free-text recognizer.",
                    Severity.INFO,
                ))
                continue
            applied += len(fields)
            visual = merge_template_fields(visual, {f.name: f for f in fields})
        if applied:
            pipeline_flags.append(self._mkflag(
                "template_roi_applied",
                f"Registered {doc_type.value} template produced {applied} "
                "structure-aware fields.",
                Severity.INFO,
            ))
        return visual

    # -- best-effort path (upload an image, get the best result) -------------
    def validate_best_effort(
        self,
        image_bgr: np.ndarray,
        forced_type: Optional[DocumentType] = None,
        companion_bgr: Optional[np.ndarray] = None,
    ) -> DocumentValidationResult:
        """Insert a raw image and get the most accurate result available,
        WITHOUT requiring a type hint.

        Unlike ``validate_image`` this is the accuracy-first production path:
          * classification still auto-detects (MRZ type char -> keyword hints),
          * template ROI OCR runs for EVERY plausible candidate type (MRZ
            type + top hinted types) instead of only the exact classified
            type, and
          * the best-confidence read wins per field across all sources.

        ``forced_type`` pins the type up-front (the CLI's ``--type``
        argument); when None the engine falls back to auto-detection.

        ``companion_bgr`` is the other physical side of the same document
        (e.g. the Aadhaar BACK that carries the QR). Its OCR lines are folded
        into the visual-zone pool and its machine-readable zones are decoded
        alongside the primary image, so the QR anchored cross-checks run
        against both sides at once.
        """
        try:
            preprocessed = preprocess_image(image_bgr)
        except Exception as exc:
            return self._degraded_result(
                f"Image could not be preprocessed ({type(exc).__name__}).",
                "image_preprocessing_failed",
            )
        companion = None
        if companion_bgr is not None:
            try:
                companion = preprocess_image(companion_bgr)
            except Exception as exc:
                return self._degraded_result(
                    f"Companion (other-side) image could not be preprocessed "
                    f"({type(exc).__name__}).",
                    "companion_image_preprocessing_failed",
                )
        return self._run_best_effort(preprocessed, forced_type, companion)

    def _run_best_effort(
        self,
        preprocessed: PreprocessedDocument,
        forced_type: Optional[DocumentType] = None,
        companion_preprocessed: Optional[PreprocessedDocument] = None,
    ) -> DocumentValidationResult:
        pipeline_flags: list[ValidationFlag] = []

        def _ocr(prep):
            try:
                return self.ocr.extract(prep)
            except Exception as exc:  # an extractor bug must not crash the engine
                pipeline_flags.append(self._mkflag(
                    "ocr_extraction_failed",
                    f"OCR extraction crashed ({type(exc).__name__}); MRZ rules "
                    "could not run.",
                    Severity.WARNING,
                ))
                return None

        ocr_result = _ocr(preprocessed)
        companion_ocr = _ocr(companion_preprocessed) if companion_preprocessed is not None else None

        for result, label in ((ocr_result, "primary"),
                              (companion_ocr, "companion")):
            if result is None:
                continue
            if not result.recognized:
                pipeline_flags.append(self._mkflag(
                    "ocr_no_text",
                    f"No text recognized from the {label} image "
                    f"({result.message}). Either the image is empty or the "
                    "OCR backend is unavailable.",
                    Severity.WARNING,
                ))
            else:
                pipeline_flags.append(self._mkflag(
                    "ocr_read_from",
                    f"OCR consumed the {result.read_from} copy of the "
                    f"{label} side per the two-copy contract.",
                    Severity.INFO,
                ))

        lines: list = []
        if ocr_result is not None:
            lines.extend(ocr_result.lines or [])
        if companion_ocr is not None:
            lines.extend(companion_ocr.lines or [])
        mrz = find_mrz_block([line.text for line in lines]) if not self.skip_mrz else None
        hints = self.type_hints_fn(lines)
        visual: Dict[str, ExtractedField] = (
            {} if self.skip_visual else self.visual_recognizer(lines)
        )
        candidates = self._best_effort_candidates(mrz, hints, forced_type)
        if not self.skip_visual:
            visual = self._apply_templates_for_types(
                preprocessed, candidates, visual, pipeline_flags
            )
        barcodes: list[BarcodeResult] = []
        if not self.skip_barcodes:
            barcodes.extend(self._read_barcodes(preprocessed, pipeline_flags))
            if companion_preprocessed is not None:
                barcodes.extend(
                    self._read_barcodes(companion_preprocessed, pipeline_flags)
                )
            visual = merge_fields(visual, self._barcode_fields(barcodes))
        flags, fields, _ = self._assemble(mrz, visual)
        return self._score_and_finish(
            preprocessed, mrz, fields, pipeline_flags + flags, hints,
            forced_type=forced_type, barcodes=barcodes,
        )

    def _best_effort_candidates(
        self,
        mrz: Optional[MRZResult],
        hints: Mapping[DocumentType, float],
        forced_type: Optional[DocumentType] = None,
    ) -> list[DocumentType]:
        """Ordered candidate types for the best-effort template pass.

        Forced type (when supplied) wins, MRZ type code is next, and the
        top-2 keyword-hinted types round out the set when no MRZ exists.
        UNKNOWN is never a template target.
        """
        ordered: list[DocumentType] = []
        if forced_type is not None:
            ordered.append(forced_type)
        if mrz is not None and mrz.recognized:
            mrz_type, _ = classify_document(mrz, {})
            if mrz_type != DocumentType.UNKNOWN:
                ordered.append(mrz_type)
        else:
            for doc_type, _score in sorted(
                hints.items(), key=lambda kv: kv[1], reverse=True
            )[:2]:
                ordered.append(doc_type)
        seen: set[DocumentType] = set()
        out: list[DocumentType] = []
        for doc_type in ordered:
            if doc_type != DocumentType.UNKNOWN and doc_type not in seen:
                seen.add(doc_type)
                out.append(doc_type)
        return out

    def _apply_templates_for_types(
        self,
        preprocessed: PreprocessedDocument,
        candidate_types: Sequence[DocumentType],
        visual: Dict[str, ExtractedField],
        pipeline_flags: list[ValidationFlag],
    ) -> Dict[str, ExtractedField]:
        """Run structure-aware ROI OCR for every candidate type and keep the
        best-confidence read per field name across all of them.

        This is the accuracy improvement over ``_apply_templates``: instead
        of committing to one classified type up-front, parallel candidate
        layouts compete and the strongest read wins each field. A failing
        template pass degrades to an info flag -- the free-text recognizer's
        output stays as the fallback.
        """
        if not self.templates or not candidate_types:
            return visual
        bgr = cv2_gray_to_bgr(preprocessed.clahe_gray)
        best_by_name: Dict[str, ExtractedField] = {}
        applied = 0
        for doc_type in candidate_types:
            matching = [t for t in self.templates if t.document_type == doc_type]
            for template in matching:
                try:
                    fields = recognize_template_fields(
                        bgr, template,
                        lambda crop: engine_ocr_crop(self.ocr, crop),
                    )
                except Exception as exc:  # a template bug must not crash the engine
                    pipeline_flags.append(self._mkflag(
                        "template_roi_failed",
                        f"Template ROI OCR failed ({type(exc).__name__}); "
                        "fell back to the free-text recognizer.",
                        Severity.INFO,
                    ))
                    continue
                applied += len(fields)
                for field in fields:
                    current = best_by_name.get(field.name)
                    if current is None or field.confidence > current.confidence:
                        best_by_name[field.name] = field
        if applied:
            pipeline_flags.append(self._mkflag(
                "template_roi_applied",
                f"Best-effort template pass registered {applied} "
                "structure-aware field reads across "
                f"{', '.join(dt.value for dt in candidate_types)}.",
                Severity.INFO,
            ))
        if best_by_name:
            visual = merge_template_fields(visual, best_by_name)
        return visual

    def _read_barcodes(
        self,
        preprocessed: Optional[PreprocessedDocument],
        pipeline_flags: list[ValidationFlag],
    ) -> list[BarcodeResult]:
        """Decode the machine-readable zones off the forensic copy.

        Orphic: a failing decode is an info flag (the per-type anchor rule
        decides whether its absence matters), and a decoder crash must never
        take the pipeline down.
        """
        if preprocessed is None:
            return []
        try:
            barcodes = list(self.barcode_extractor.extract(preprocessed))
        except Exception as exc:  # a decoder bug must not crash the engine
            pipeline_flags.append(self._mkflag(
                "barcode_read_failed",
                f"Barcode/QR decoding failed ({type(exc).__name__}).",
                Severity.INFO,
            ))
            return []
        if barcodes:
            channels = ", ".join(sorted({b.channel for b in barcodes}))
            pipeline_flags.append(self._mkflag(
                "machine_channel_read",
                f"Decoded {len(barcodes)} machine-readable zone(s): {channels}.",
                Severity.INFO,
            ))
        return barcodes

    @staticmethod
    def _barcode_fields(
        barcodes: Sequence[BarcodeResult],
    ) -> Dict[str, ExtractedField]:
        """Map classified barcode payloads to ``ExtractedField``s (B=BARCODE)."""
        out: Dict[str, ExtractedField] = {}
        for barcode in barcodes:
            for name, value in fields_from_barcode_result(barcode).items():
                if name in out:
                    continue
                out[name] = ExtractedField(
                    name=name,
                    value=value,
                    source=FieldSource.BARCODE,
                    confidence=0.99,
                )
        return out

    def _assemble(
        self,
        mrz: Optional[MRZResult],
        visual: Mapping[str, ExtractedField],
    ) -> Tuple[list[ValidationFlag], Dict[str, ExtractedField], list[ValidationFlag]]:
        flags: list[ValidationFlag] = []
        if mrz is not None and not mrz.recognized:
            flags.append(self._mkflag(
                "mrz_detection_failed",
                "An MRZ-like region was detected but could not be parsed "
                "cleanly; MRZ-based rules were skipped. Could be OCR failure "
                "or an unusual layout.",
                Severity.WARNING,
            ))
        mrz_fields = fields_from_mrz(mrz, self.reference_date.year)
        fields = merge_fields(visual, mrz_fields)
        return flags, fields, []

    def _score_and_finish(
        self,
        preprocessed: Optional[PreprocessedDocument],
        mrz: Optional[MRZResult],
        fields: Dict[str, ExtractedField],
        flags: list[ValidationFlag],
        hints: Mapping[DocumentType, float],
        forced_type: Optional[DocumentType] = None,
        barcodes: Sequence[BarcodeResult] = (),
    ) -> DocumentValidationResult:
        if forced_type is not None:
            # The caller pinned the document type up-front.
            # Respect it as the extraction target, but surface a conflict
            # when the MRZ/keyword evidence points the other way.
            auto_type, _ = classify_document(
                mrz if (mrz is not None and mrz.recognized) else None, hints
            )
            document_type, confidence = forced_type, 1.0
            if auto_type != DocumentType.UNKNOWN and auto_type != forced_type:
                flags.append(self._mkflag(
                    "type_hint_conflict",
                    f"Specified type {forced_type.value} differs from the "
                    f"auto-detected {auto_type.value}. The selected type "
                    "drove extraction; verify against the image.",
                    Severity.WARNING,
                ))
        else:
            mrz_for_classify = mrz if (mrz is not None and mrz.recognized) else None
            document_type, confidence = classify_document(mrz_for_classify, hints)

        # logical validation over calendar fields
        logical = validate_dates(
            date_of_birth=fields.get("date_of_birth").value if fields.get("date_of_birth") else None,
            issue_date=fields.get("issue_date").value if fields.get("issue_date") else None,
            expiry_date=fields.get("date_of_expiry").value if fields.get("date_of_expiry") else None,
            reference_date=self.reference_date,
        )
        flags.extend(logical.flags)

        # document rules for this type
        rules_flags = run_all_rules(
            document_type,
            fields,
            mrz=mrz,
            lookup_fn=self.blacklist_lookup,
            reference_year=self.reference_date.year,
            barcodes=barcodes,
            input_side=self.input_sides,
        )
        flags.extend(rules_flags)

        # When a dual-side Aadhaar upload (or a back-only capture) still shows
        # no QR, give the officer an actionable hint instead of only the
        # generic anchor warning.
        if (
            document_type == DocumentType.AADHAAR
            and self.input_sides in ("back", "both")
            and not any(b.channel == "aadhaar_qr" for b in barcodes)
        ):
            hint_msg = (
                f"The {self.input_sides.upper()} side of the Aadhaar card "
                "was uploaded, but the UIDAI QR could not be decoded from it. "
                "Upload a tight, well-lit crop of the QR zone (or the "
                "e-Aadhaar PDF) so the secure anchor can be verified."
            ) if self.input_sides == "back" else (
                "Both sides were provided but no UIDAI QR could be decoded "
                "from them. Upload a tight, well-lit crop of the QR zone (or "
                "the e-Aadhaar PDF) so the secure anchor can be verified."
            )
            flags.append(self._mkflag(
                "anchor_crop_hint", hint_msg, Severity.INFO,
            ))

        score, breakdown, ledger = compute_score(flags, fields, document_type)

        mrz_found = mrz is not None and mrz.recognized
        schemas_mrz = _to_schemas_mrz(mrz) if mrz is not None else None

        message = self._summarize(document_type, mrz_found, flags, score)
        return DocumentValidationResult(
            document_type=document_type,
            classification_confidence=float(confidence),
            validation_score=score,
            score_breakdown=breakdown,
            score_ledger=ledger,
            flags=flags,
            fields=list(fields.values()),
            mrz=schemas_mrz,
            mrz_found=mrz_found,
            barcodes=list(barcodes),
            message=message,
        )

    def _degraded_result(self, message: str, code: str) -> DocumentValidationResult:
        flag = self._mkflag(code, message, Severity.WARNING)
        ledger = [
            {
                "code": code,
                "severity": "warning",
                "reason": message,
                "deduction": WARNING_DEDUCTION,
                "balance": round(100.0 - WARNING_DEDUCTION, 2),
            },
            {
                "code": "remaining_points",
                "severity": "info",
                "reason": "points left after all named deductions = final score",
                "deduction": 0.0,
                "balance": round(100.0 - WARNING_DEDUCTION, 2),
            },
        ]
        return DocumentValidationResult(
            document_type=DocumentType.UNKNOWN,
            classification_confidence=0.0,
            validation_score=0,
            score_breakdown=build_score_breakdown(flag_deductions=WARNING_DEDUCTION),
            score_ledger=ledger,
            flags=[flag],
            fields=[],
            mrz=None,
            mrz_found=False,
            message=message,
        )

    @staticmethod
    def _mkflag(code: str, message: str, severity: Severity) -> ValidationFlag:
        return ValidationFlag(code=code, message=message, severity=severity)

    @staticmethod
    def _summarize(
        document_type: DocumentType,
        mrz_found: bool,
        flags: Sequence[ValidationFlag],
        score: int,
    ) -> str:
        high = [f for f in flags if f.severity == Severity.HIGH]
        n_high = len(high)
        note = (
            f"{n_high} high-severity evidence flag(s); "
            + "; ".join(f"{f.code}: {f.severity.value}" for f in high)
            if high else "no high-severity evidence flags"
        )
        return (
            f"Classified as {document_type.value} (MRZ={'yes' if mrz_found else 'no'}), "
            f"data-coherence score {score}/100. {note} This score measures "
            "whether the extracted DATA hangs together; it is not a fraud "
            "verdict and ignores image authenticity / face-match (later stages)."
        )


def _to_schemas_mrz(mrz: MRZResult) -> Optional[SchemasMRZResult]:
    """Map the parser's MRZResult onto the schemas contract."""
    return SchemasMRZResult(
        mrz_format=mrz.mrz_format,
        recognized=mrz.recognized,
        lines=list(mrz.lines),
        data=dict(mrz.data),
        identifiers=dict(mrz.identifiers),
        check_digits=dict(mrz.check_digits),
        check_details=list(mrz.check_details),
        message=mrz.message,
    )