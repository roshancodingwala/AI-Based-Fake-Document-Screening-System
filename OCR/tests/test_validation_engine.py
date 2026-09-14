"""Tests for the validation engine -- the only wiring module in Module 1.

These tests pin the engine's invariants:
  * a clean ICAO specimen scores high; a tampered composite scores less;
  * UNKNOWN is scored with a named penalty and NEVER coerced;
  * blacklist lookups are injected and their failures are surfaced as flags;
  * a bad image or missing OCR backend degrades to a flagged result, never
    an exception;
  * score_breakdown always contains every canonical key.
"""

import sys
from datetime import date

import numpy as np
import pytest

sys.path.insert(0, ".")

from ocr_extractor import OCRExtractionResult, OCRTextLine
from schemas import (
    BREAKDOWN_KEYS,
    BarcodeResult,
    DocumentType,
    ExtractedField,
    FieldSource,
    Severity,
)
from validation_engine import (
    HIGH_DEDUCTION,
    UNKNOWN_TYPE_PENALTY,
    EngineOptions,
    ValidationEngine,
    _to_schemas_mrz,
    classify_document,
    compute_score,
    default_type_hints,
    default_visual_recognizer,
    fields_from_mrz,
    find_mrz_block,
    merge_fields,
)

# Real ICAO 9303 specimen (Doc 9303 Part 4) -- all check digits valid.
SPECIMEN_PASSPORT = (
    "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<",
    "L898902C<3UTO6908061F9406236ZE184226B<<<<<14",
)
# Composite digit changed 4 -> 8: field checks still pass, composite fails.
TAMPERED_COMPOSITE = (
    "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<",
    "L898902C<3UTO6908061F9406236ZE184226B<<<<<18",
)
# Built with valid check digits, expiry 2035 -> not expired at reference date.
VALID_FUTURE_PASSPORT = (
    "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<",
    "AB123456<4UTO0001018F3501014ZE184226B<<<<<14",
)
REFERENCE = date(2026, 9, 12)


def engine(**kwargs):
    return ValidationEngine(
        EngineOptions(
            reference_date=REFERENCE,
            blacklist_lookup=kwargs.pop("black", None),
            ocr_extractor=kwargs.pop("ocr", None),
            barcode_extractor=kwargs.pop("barcode", None),
            visual_recognizer=kwargs.pop("visual", None),
            type_hints_fn=kwargs.pop("hints", None),
        )
    )


# --- clean vs tampered ------------------------------------------------------
def test_clean_passport_high_score_and_verified():
    result = engine().validate_mrz_lines(list(SPECIMEN_PASSPORT))
    assert result.document_type == DocumentType.PASSPORT
    assert result.mrz_found is True
    assert result.validation_score >= 85
    codes = [f.code for f in result.flags]
    assert "mrz_checks_verified" in codes
    assert not any(f.code == "mrz_composite_check_failed" for f in result.flags)
    assert set(BREAKDOWN_KEYS).issubset(result.score_breakdown.keys())


def test_tampered_composite_flagged_high_and_lower_score():
    clean = engine().validate_mrz_lines(list(SPECIMEN_PASSPORT))
    tampered = engine().validate_mrz_lines(list(TAMPERED_COMPOSITE))
    codes = [f.code for f in tampered.flags]
    assert "mrz_composite_check_failed" in codes
    flag = next(f for f in tampered.flags if f.code == "mrz_composite_check_failed")
    assert flag.severity == Severity.HIGH
    assert tampered.validation_score <= clean.validation_score - HIGH_DEDUCTION


def test_valid_future_expiry_is_not_expired():
    result = engine().validate_mrz_lines(list(VALID_FUTURE_PASSPORT))
    codes = [f.code for f in result.flags]
    assert "expired" not in codes
    assert result.validation_score >= 90


# --- UNKNOWN handling -------------------------------------------------------
def test_no_evidence_is_unknown_with_penalty():
    result = engine().validate_mrz_lines(["SOME","GARBAGE","LINES"])
    assert result.document_type == DocumentType.UNKNOWN
    assert result.classification_confidence == 0.0
    assert result.score_breakdown["unknown_type_penalty"] == UNKNOWN_TYPE_PENALTY


def test_unknown_mrz_type_not_forced_to_known():
    # TD1 (3x30) beginning with an unrecognized type char sequence
    lines = (
        "E<UTOD231458907<<<<<<<<<<<<<<<",
        "7408122F1204159UTO<<<<<<<<<<<6",
        "ERIKSSON<<ANNA<MARIA<<<<<<<<<<",
    )
    from mrz_parser import parse_mrz
    if parse_mrz(list(lines)).recognized:
        result = engine().validate_mrz_lines(list(lines))
        assert result.document_type == DocumentType.UNKNOWN
        assert result.classification_confidence == pytest.approx(0.5)


# --- blacklist injection ----------------------------------------------------
def test_blacklist_none_is_info_flag():
    result = engine().validate_mrz_lines(list(SPECIMEN_PASSPORT))
    assert any(f.code == "blacklist_not_configured" for f in result.flags)


def test_blacklist_hit_is_surfaced_not_decided():
    def lookup(query):
        return True
    result = engine(black=lookup).validate_mrz_lines(list(SPECIMEN_PASSPORT))
    assert any(f.code == "blacklist_hit" for f in result.flags)
    assert not any(f.code == "blacklist_clear" for f in result.flags)


def test_blacklist_clear():
    result = engine(black=lambda _q: False).validate_mrz_lines(list(SPECIMEN_PASSPORT))
    assert any(f.code == "blacklist_clear" for f in result.flags)


def test_blacklist_exception_becomes_warning_flag():
    def boom(_q):
        raise RuntimeError("db down")
    result = engine(black=boom).validate_mrz_lines(list(SPECIMEN_PASSPORT))
    flag = next(f for f in result.flags if f.code == "blacklist_lookup_failed")
    assert flag.severity == Severity.WARNING
    assert "NOT" in flag.message  # never treated as a clear


def test_blacklist_none_result_not_swallowed():
    result = engine(black=lambda _q: None).validate_mrz_lines(list(SPECIMEN_PASSPORT))
    assert any(f.code == "blacklist_lookup_failed" for f in result.flags)


# --- graceful degradation ----------------------------------------------------
def test_bad_image_degrades_gracefully():
    result = engine().validate_image(None)  # not even an array
    assert result.document_type == DocumentType.UNKNOWN
    assert any(f.code == "image_preprocessing_failed" for f in result.flags)
    assert 0 <= result.validation_score <= 100


def test_ocr_backend_failure_degrades_gracefully():
    class ExplodingOCR:
        def extract(self, preprocessed):
            raise RuntimeError("model dead")

    result = engine(ocr=ExplodingOCR()).validate_image(_blank_image())
    assert any(f.code == "ocr_extraction_failed" for f in result.flags)
    assert result.document_type == DocumentType.UNKNOWN


def _blank_image():
    return np.full((300, 500), 255, np.uint8)


# --- end-to-end with a fake OCR extractor -------------------------------------
class FakeOCR:
    def __init__(self, lines):
        self.lines = lines

    def extract(self, preprocessed):
        return OCRExtractionResult(
            read_from="ocr_ready",
            lines=[
                OCRTextLine(text=t, confidence=0.99, bbox=(0.0, 0.0, 1.0, 1.0))
                for t in self.lines
            ],
            recognized=True,
        )


def test_end_to_end_image_pipeline_finds_mrz():
    fake = FakeOCR(list(SPECIMEN_PASSPORT))
    result = engine(ocr=fake).validate_image(_blank_image())
    assert result.mrz_found is True
    assert result.document_type == DocumentType.PASSPORT
    assert any(f.code == "ocr_read_from" for f in result.flags)


def test_end_to_end_forensic_copy_not_used_by_ocr():
    fake = FakeOCR(["NO_MRZ_HERE_JUST_TEXT"])
    result = engine(ocr=fake).validate_image(_blank_image())
    assert result.mrz_found is False
    assert "ocr_extraction_failed" not in [f.code for f in result.flags]


def test_end_to_end_aadhaar_card_classifies_and_checks_verhoeff():
    import verhoeff

    number = verhoeff.make_aadhaar_number("23456789012")
    grouped = f"{number[0:4]} {number[4:8]} {number[8:12]}"
    tampered_digit = "0" if number[-1] != "0" else "1"
    tampered = number[:-1] + tampered_digit
    tampered_grouped = f"{tampered[0:4]} {tampered[4:8]} {tampered[8:12]}"
    lines = [
        "GOVERNMENT OF INDIA",
        "UNIQUE IDENTIFICATION AUTHORITY OF INDIA",
        "NAME: SINGH ARJUN KUMAR",
        "DOB: 15/08/1995",
        "SEX: MALE",
        f"AADHAAR NUMBER: {grouped}",
    ]
    result = engine(ocr=FakeOCR(lines)).validate_image(_blank_image())
    assert result.document_type == DocumentType.AADHAAR
    assert any(f.code == "aadhaar_checksum_ok" for f in result.flags)
    assert result.validation_score >= 75

    tampered_lines = lines[:-1] + [f"AADHAAR NUMBER: {tampered_grouped}"]
    result2 = engine(ocr=FakeOCR(tampered_lines)).validate_image(_blank_image())
    assert result2.document_type == DocumentType.AADHAAR
    assert any(f.code == "aadhaar_checksum_failed" for f in result2.flags)
    assert result2.validation_score < result.validation_score


# --- barcode channels wired through the engine -----------------------------------
class FakeBarcodeExtractor:
    def __init__(self, results):
        self.results = results

    def extract(self, preprocessed):
        return list(self.results)


def test_aadhaar_qr_channel_wired_into_image_pipeline():
    import verhoeff
    from schemas import BarcodeResult

    number = verhoeff.make_aadhaar_number("23456789012")
    grouped = f"{number[0:4]} {number[4:8]} {number[8:12]}"
    lines = [
        "GOVERNMENT OF INDIA",
        "UNIQUE IDENTIFICATION AUTHORITY OF INDIA",
        "NAME: SINGH ARJUN KUMAR",
        "DOB: 15/08/1995",
        "SEX: MALE",
        f"AADHAAR NUMBER: {grouped}",
    ]
    qr = BarcodeResult(
        channel="aadhaar_qr",
        format="QRCODE",
        raw="<xml>",
        data={
            "uid": number,
            "name": "SINGH ARJUN KUMAR",
            "gender": "M",
            "dob": "15/08/1995",
        },
        signature_present=True,
    )
    result = engine(
        ocr=FakeOCR(lines), barcode=FakeBarcodeExtractor([qr])
    ).validate_image(_blank_image())

    assert result.document_type == DocumentType.AADHAAR
    assert len(result.barcodes) == 1
    assert result.barcodes[0].channel == "aadhaar_qr"
    codes = {f.code for f in result.flags}
    assert "aadhaar_qr_signed_payload" in codes
    assert "aadhaar_qr_checksum_ok" in codes
    assert "aadhaar_qr_number_mismatch" not in codes
    assert "secure_anchor_missing" not in codes


def test_aadhaar_qr_mismatch_deduces_score():
    import verhoeff
    from schemas import BarcodeResult

    number = verhoeff.make_aadhaar_number("23456789012")
    other = verhoeff.make_aadhaar_number("99999999997")
    grouped_other = f"{other[0:4]} {other[4:8]} {other[8:12]}"
    lines = [
        "GOVERNMENT OF INDIA",
        "UNIQUE IDENTIFICATION AUTHORITY OF INDIA",
        "DOB: 15/08/1995",
        f"AADHAAR NUMBER: {grouped_other}",
    ]
    qr = BarcodeResult(
        channel="aadhaar_qr",
        format="QRCODE",
        raw="<xml>",
        data={"uid": number, "name": "SINGH ARJUN KUMAR", "dob": "15/08/1995"},
    )
    result = engine(
        ocr=FakeOCR(lines), barcode=FakeBarcodeExtractor([qr])
    ).validate_image(_blank_image())
    codes = {f.code for f in result.flags}
    assert "aadhaar_qr_number_mismatch" in codes
    assert result.validation_score < 90


def test_dl_barcode_channel_wired_into_image_pipeline():
    from schemas import BarcodeResult

    lines = [
        "DRIVING LICENCE",
        f"NAME: SINGH ARJUN KUMAR",
        "DATE OF BIRTH: 15/08/1995",
        "LICENCE NUMBER: MH 01 2030 0567890",
        "VALID TILL: 27/11/2032",
    ]
    barcode = BarcodeResult(
        channel="dl_barcode",
        format="QRCODE",
        raw='{"licenceNo":"MH0120300567890"}',
        data={"document_number": "MH0120300567890"},
    )
    result = engine(
        ocr=FakeOCR(lines), barcode=FakeBarcodeExtractor([barcode])
    ).validate_image(_blank_image())

    assert result.document_type == DocumentType.DRIVING_LICENSE
    assert any(b.channel == "dl_barcode" for b in result.barcodes)
    codes = {f.code for f in result.flags}
    assert "secure_anchor_missing" not in codes
    assert "dl_barcode_number_mismatch" not in codes


def test_visual_only_aadhaar_reports_secure_anchor_missing():
    import verhoeff

    number = verhoeff.make_aadhaar_number("23456789012")
    grouped = f"{number[0:4]} {number[4:8]} {number[8:12]}"
    lines = [
        "GOVERNMENT OF INDIA",
        "UNIQUE IDENTIFICATION AUTHORITY OF INDIA",
        "DOB: 15/08/1995",
        f"AADHAAR NUMBER: {grouped}",
    ]
    result = engine(ocr=FakeOCR(lines)).validate_image(_blank_image())
    assert result.document_type == DocumentType.AADHAAR
    codes = {f.code for f in result.flags}
    assert "secure_anchor_missing" in codes
    assert "aadhaar_checksum_ok" in codes


# --- helper pure functions -----------------------------------------------------
def test_find_mrz_block_with_noise():
    lines = ["date: 2023-01-01", "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<",
             "L898902C<3UTO6908061F9406236ZE184226B<<<<<14", "signature"]
    mrz = find_mrz_block(lines)
    assert mrz is not None and mrz.recognized
    assert find_mrz_block(["hello", "world"]) is None


def test_find_mrz_block_relaxed_trailing_fillers_dropped():
    from mrz_parser import MRZFormat

    line1 = ("P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<")[:-11]
    line2 = ("L898902C<3UTO6908061F9406236ZE184226B<<<<<14")[:-11]
    assert len(line1) == 33 and len(line2) == 33
    mrz = find_mrz_block([line1, line2])
    assert mrz is not None and mrz.recognized
    assert mrz.mrz_format == MRZFormat.TD3
    assert mrz.data["document_number"] == "L898902C<"


def test_find_mrz_block_short_line_ignored():
    # Far below the credible short-filler band: must NOT be massaged into
    # an MRZ, otherwise noise text would be fabricated into a reading.
    assert find_mrz_block(["P<UTO", "L8989"]) is None


def test_find_mrz_block_uppercase_normalization():
    # OCR occasionally returns lowercase letters in the MRZ band even though
    # ICAO prints only upper-case. Discovery must normalize case first.
    line1 = "P<UTOERIKSSON<<ANNA<MARlA<<<<<<<<<<<<<<<<<<<".ljust(44, "<")
    line2 = "L898902C<3UTO6908061F9406236ZE184226B<<<<<14"
    mrz = find_mrz_block([line1, line2])
    assert mrz is not None and mrz.recognized
    assert mrz.data["document_number"] == "L898902C<"


def test_fields_from_mrz_iso_and_identifiers():
    mrz = find_mrz_block(list(SPECIMEN_PASSPORT))
    fields = fields_from_mrz(mrz, 2026)
    assert fields["date_of_birth"].value == "1969-08-06"
    assert fields["date_of_expiry"].value == "1994-06-23"
    assert fields["surname"].value == "ERIKSSON"
    assert fields["given_names"].value == "ANNA MARIA"
    assert fields["document_number"].value == "L898902C"
    assert fields["date_of_birth"].source == FieldSource.MRZ


def test_merge_fields_precedence():
    visual = {
        "surname": ExtractedField(name="surname", value="VISUAL_NAME",
                                  source=FieldSource.VISUAL, confidence=0.5),
    }
    mrz_fields = {
        "surname": ExtractedField(name="surname", value="MRZ_NAME",
                                  source=FieldSource.MRZ, confidence=1.0),
        "given_names": ExtractedField(name="given_names", value="MARIA",
                                      source=FieldSource.MRZ, confidence=1.0),
    }
    merged = merge_fields(visual, mrz_fields)
    assert merged["surname"].source == FieldSource.VISUAL  # visual kept
    assert merged["given_names"].source == FieldSource.MRZ  # gap filled


def test_classify_document_rules():
    from mrz_parser import parse_mrz
    mrz = parse_mrz(list(SPECIMEN_PASSPORT))
    assert classify_document(mrz, {}) == (DocumentType.PASSPORT, 0.98)
    assert classify_document(None, {}) == (DocumentType.UNKNOWN, 0.0)
    hints = {DocumentType.AADHAAR: 0.7}
    assert classify_document(None, hints)[0] == DocumentType.AADHAAR


def test_compute_score_breakdown_always_complete():
    _, breakdown, _ = compute_score([], {}, DocumentType.PASSPORT)
    assert breakdown["flag_deductions"] == 0.0
    assert breakdown["remaining_points"] == 100.0
    assert set(BREAKDOWN_KEYS).issubset(breakdown.keys())


def test_compute_score_unknown_penalty_applied():
    _, breakdown, _ = compute_score([], {}, DocumentType.UNKNOWN)
    assert breakdown["unknown_type_penalty"] == UNKNOWN_TYPE_PENALTY
    assert breakdown["remaining_points"] == 100.0 - UNKNOWN_TYPE_PENALTY


def test_compute_score_confidence_deduction():
    fields = {
        "surname": ExtractedField(name="surname", value="X",
                                  source=FieldSource.VISUAL, confidence=0.3),
    }
    score, breakdown, _ = compute_score([], fields, DocumentType.PASSPORT)
    assert breakdown["confidence_deductions"] == 2.0
    assert score < 100


def test_score_ledger_traces_each_finding_and_balance():
    from validation_engine import HIGH_DEDUCTION, WARNING_DEDUCTION
    from schemas import ValidationFlag, Severity as Sev

    flags = [
        ValidationFlag(code="aadhaar_checksum_failed", message="bad checksum",
                       severity=Sev.HIGH),
        ValidationFlag(code="secure_anchor_missing", message="no QR",
                       severity=Sev.WARNING),
        ValidationFlag(code="machine_channel_read", message="qr decoded",
                       severity=Sev.INFO),
    ]
    score, breakdown, ledger = compute_score(flags, {}, DocumentType.AADHAAR)
    assert ledger[0] == {"code": "aadhaar_checksum_failed", "severity": "high",
                         "reason": "bad checksum", "deduction": HIGH_DEDUCTION,
                         "balance": 100.0 - HIGH_DEDUCTION}
    assert ledger[1]["deduction"] == WARNING_DEDUCTION
    assert ledger[1]["balance"] == 100.0 - HIGH_DEDUCTION - WARNING_DEDUCTION
    assert ledger[2]["deduction"] == 0.0  # INFO costs nothing
    assert ledger[-1]["code"] == "remaining_points"
    assert ledger[-1]["balance"] == breakdown["remaining_points"]
    assert score == breakdown["remaining_points"]


def test_score_ledger_mode_skips_mrz_never_breaks():
    from validation_engine import EngineOptions, ValidationEngine

    result = ValidationEngine(
        EngineOptions(skip_mrz=True, skip_barcodes=True)
    ).validate_image(__import__("numpy").zeros((100, 100, 3), dtype="uint8"))
    assert result.score_ledger
    assert result.score_ledger[-1]["code"] == "remaining_points"


def test_default_visual_recognizer_extracts_label_value():
    lines = [
        OCRTextLine(
            text="Document No: AB123456", confidence=0.9,
            bbox=(0.2, 0.3, 0.8, 0.4),
        ),
        OCRTextLine(
            text="Date of Birth: 12/08/1974", confidence=0.85,
            bbox=(0.2, 0.5, 0.8, 0.6),
        ),
        OCRTextLine(text="random line", confidence=0.5, bbox=(0, 0, 0.1, 0.1)),
    ]
    fields = default_visual_recognizer(lines)
    assert fields["document_number"].value == "AB123456"
    assert fields["date_of_birth"].value == "12/08/1974"
    assert fields["document_number"].source == FieldSource.VISUAL
    assert fields["document_number"].confidence == 0.9


def test_default_type_hints_keyword_mapping():
    lines = [OCRTextLine(text="ELECTION COMMISSION VOTER ID", confidence=0.9,
                        bbox=(0, 0, 1, 1))]
    hints = default_type_hints(lines)
    assert DocumentType.VOTER_ID in hints
    assert hints[DocumentType.VOTER_ID] > 0.5


def test_default_type_hints_residence_keyword_is_exact_phrase():
    # single-char substrings must never vote; only exact phrases count
    lines = [OCRTextLine(text="RESIDENCE PERMIT OF THE TEST", confidence=0.9,
                        bbox=(0, 0, 1, 1))]
    hints = default_type_hints(lines)
    assert DocumentType.RESIDENCE_PERMIT in hints
    assert hints[DocumentType.RESIDENCE_PERMIT] > 0.3


def test_schemas_mrz_mapping():
    mrz = find_mrz_block(list(SPECIMEN_PASSPORT))
    schemas = _to_schemas_mrz(mrz)
    assert schemas.recognized is True
    assert schemas.mrz_format.value == "TD3"
    assert schemas.check_digits["composite"] is True


# --- best-effort path -------------------------------------------------------
import verhoeff

_ACHHAAR_NUMBER = verhoeff.make_aadhaar_number("23456789012")
ACHHAAR_STYLE_LINES = [
    "GOVERNMENT OF INDIA",
    "UNIQUE IDENTIFICATION AUTHORITY OF INDIA",
    "NAME: SINGH ARJUN KUMAR",
    "DOB: 15/08/1995",
    f"AADHAAR NUMBER: {_ACHHAAR_NUMBER[0:4]} {_ACHHAAR_NUMBER[4:8]} "
    f"{_ACHHAAR_NUMBER[8:12]}",
]


def _best_effort_engine(**kwargs):
    return ValidationEngine(
        EngineOptions(
            reference_date=REFERENCE,
            ocr_extractor=kwargs.pop("ocr", None),
            visual_recognizer=kwargs.pop("visual", None),
            type_hints_fn=kwargs.pop("hints", None),
            templates=kwargs.pop("templates", ()) or (),
        )
    )


def test_best_effort_auto_detects_aadhaar_from_hints():
    fake = FakeOCR(ACHHAAR_STYLE_LINES)
    result = _best_effort_engine(ocr=fake).validate_best_effort(_blank_image())
    assert result.document_type == DocumentType.AADHAAR
    assert any(f.code == "aadhaar_checksum_ok" for f in result.flags)


def test_best_effort_forced_type_is_respected_and_conflict_flagged():
    # Image OCR says Aadhaar; caller forces passport.
    fake = FakeOCR(ACHHAAR_STYLE_LINES)
    result = _best_effort_engine(ocr=fake).validate_best_effort(
        _blank_image(), forced_type=DocumentType.PASSPORT
    )
    assert result.document_type == DocumentType.PASSPORT
    codes = [f.code for f in result.flags]
    assert "type_hint_conflict" in codes
    conflict = next(f for f in result.flags if f.code == "type_hint_conflict")
    assert conflict.severity == Severity.WARNING


def test_best_effort_forced_type_without_conflict():
    # Empty OCR evidence -> no auto-detect conflict, but forced type is used.
    fake = FakeOCR(["NO_RELEVANT_KEYWORDS_HERE"])
    result = _best_effort_engine(ocr=fake).validate_best_effort(
        _blank_image(), forced_type=DocumentType.VOTER_ID
    )
    assert result.document_type == DocumentType.VOTER_ID
    assert not any(f.code == "type_hint_conflict" for f in result.flags)


def test_best_effort_candidates_priority():
    from mrz_parser import parse_mrz

    engine = _best_effort_engine()
    mrz = parse_mrz(list(SPECIMEN_PASSPORT))
    hints = {DocumentType.AADHAAR: 0.9, DocumentType.PAN_CARD: 0.3}
    cands = engine._best_effort_candidates(mrz, hints)
    assert cands == [DocumentType.PASSPORT]  # MRZ type wins over hints

    cands_none = engine._best_effort_candidates(None, hints)
    assert cands_none == [DocumentType.AADHAAR, DocumentType.PAN_CARD]

    cands_forced = engine._best_effort_candidates(
        mrz, hints, forced_type=DocumentType.DRIVING_LICENSE
    )
    assert cands_forced == [DocumentType.DRIVING_LICENSE, DocumentType.PASSPORT]

    assert engine._best_effort_candidates(None, {}) == []


def test_best_effort_runs_templates_for_candidate_types(monkeypatch):
    # A registered template supplies a high-confidence field via ROI OCR;
    # the best-effort pass must pull it in even though the free-text name
    # recognizer never read a number.
    import validation_engine

    template = SimpleNamespace(document_type=DocumentType.AADHAAR)
    template_field = ExtractedField(
        name="document_number", value="999988887777",
        source=FieldSource.TEMPLATE, confidence=1.0,
    )

    monkeypatch.setattr(
        validation_engine,
        "recognize_template_fields",
        lambda bgr, template_, ocr_crop: [template_field],
    )

    fake_ocr = FakeOCR(ACHHAAR_STYLE_LINES)
    engine = ValidationEngine(
        EngineOptions(
            reference_date=REFERENCE,
            ocr_extractor=fake_ocr,
            templates=[template],
        )
    )
    result = engine.validate_best_effort(_blank_image())
    assert result.document_type == DocumentType.AADHAAR
    assert any(
        f.name == "document_number" and f.value == "999988887777"
        for f in result.fields
    )


from types import SimpleNamespace


def test_dual_aadhaar_without_qr_emits_anchor_crop_hint():
    # Both sides supplied, Aadhaar forced, but no QR decoded -> the officer
    # gets an actionable "crop the QR" hint, not just the generic warning.
    engine = ValidationEngine(
        EngineOptions(
            reference_date=REFERENCE,
            ocr_extractor=FakeOCR(ACHHAAR_STYLE_LINES),
            input_sides="both",
        )
    )
    result = engine.validate_best_effort(
        _blank_image(), forced_type=DocumentType.AADHAAR
    )
    hint = next(f for f in result.flags if f.code == "anchor_crop_hint")
    assert hint.severity == Severity.INFO


def test_dual_aadhaar_with_qr_has_no_crop_hint():
    qr = BarcodeResult(
        channel="aadhaar_qr", format="QRCODE", raw="x",
        data={"uid": _ACHHAAR_NUMBER, "dob": "15/08/1995"},
        signature_present=True,
    )
    engine = ValidationEngine(
        EngineOptions(
            reference_date=REFERENCE,
            ocr_extractor=FakeOCR([]),
            barcode_extractor=SimpleNamespace(extract=lambda pp: [qr]),
            input_sides="both",
        )
    )
    result = engine.validate_best_effort(
        _blank_image(), forced_type=DocumentType.AADHAAR
    )
    assert "anchor_crop_hint" not in [f.code for f in result.flags]