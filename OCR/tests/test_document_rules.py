"""Tests for the document rule engine -- pure logic, no OCR / images."""

import pytest

import document_rules
from mrz_parser import parse_mrz
from schemas import DocumentType, ExtractedField, FieldSource, Severity

SPECIMEN_TD3_LINES = [
    "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<",
    "L898902C<3UTO6908061F9406236ZE184226B<<<<<14",
]


def fields(**kwargs) -> dict:
    """Build an ExtractedField map. Defaults = a complete passport set."""
    base = {
        "document_number": "L898902C",
        "surname": "ERIKSSON",
        "given_names": "ANNA MARIA",
        "date_of_birth": "1969-08-06",
        "date_of_expiry": "1994-06-23",
        "nationality": "UTO",
        "sex": "F",
    }
    base.update(kwargs)
    out = {}
    for name, value in base.items():
        out[name] = ExtractedField(
            name=name,
            value="" if value is None else value,
            source=FieldSource.VISUAL,
            confidence=0.9,
        )
    return out


def _codes(flags):
    return {f.code for f in flags}


def _make_pan(surname="SINGH", status="P", seq="1234", corrupt=None):
    """Build a checksum-valid PAN via the reverse-engineered mod-36 scheme."""
    words = [w for w in surname.split() if w.isalpha()]
    init = words[-1][0] if words else "X"
    candidate = int(seq)
    while True:
        seq = f"{candidate:04d}"
        s = "ALK" + status + init + seq
        check = document_rules._pan_mod36_check_char(s)
        if check.isalpha():  # the 10th char must be a letter
            break
        candidate += 1
    pan = s + check
    return corrupt(pan) if corrupt else pan


# --- required-field presence -------------------------------------------------
def test_all_required_fields_present_produces_no_flags():
    f = fields()
    flags = document_rules.check_required_fields(DocumentType.PASSPORT, f)
    assert "missing_required_field" not in _codes(flags)


def test_missing_required_field_is_flagged():
    f = fields(document_number=None)
    flags = document_rules.check_required_fields(DocumentType.PASSPORT, f)
    assert any(
        fl.code == "missing_required_field" and fl.field == "document_number"
        for fl in flags
    )


def test_aadhaar_back_only_requires_no_visual_name_dob():
    # The physical back of an Aadhaar prints no holder name/DOB (guardian +
    # address + QR only). An honest back-only capture must not be penalised
    # for the fields that live on the front -- even with zero fields
    # extracted, no required-field flag may fire.
    flags = document_rules.check_required_fields(
        DocumentType.AADHAAR, {}, input_side="back"
    )
    assert "missing_required_field" not in _codes(flags)


def test_aadhaar_front_and_unknown_side_keep_required_fields():
    for side in ("front", ""):
        flags = document_rules.check_required_fields(
            DocumentType.AADHAAR, {}, input_side=side
        )
        assert any(
            fl.code == "missing_required_field"
            and fl.field in ("surname", "date_of_birth")
            for fl in flags
        )
    assert all(fl.severity == Severity.WARNING for fl in flags)


def test_required_fields_are_document_type_aware():
    # Aadhaar does not require expiry; passport does.
    f = fields(date_of_expiry=None)
    assert "missing_required_field" not in _codes(
        document_rules.check_required_fields(DocumentType.AADHAAR, f)
    )
    assert any(
        fl.field == "date_of_expiry"
        for fl in document_rules.check_required_fields(DocumentType.PASSPORT, f)
    )


def test_unknown_type_has_no_required_fields():
    f = fields(surname=None, given_names=None)
    flags = document_rules.check_required_fields(DocumentType.UNKNOWN, f)
    assert "missing_required_field" not in _codes(flags)


# --- document-number format ---------------------------------------------------
def test_format_mismatch_is_flagged_loosely():
    f = fields(document_number="12AB345678XX99")  # not a passport-ish number
    flags = document_rules.check_document_number_format(DocumentType.PASSPORT, f)
    assert "document_number_format" in _codes(flags)


def test_format_match_passes():
    f = fields(document_number="L898902C")
    flags = document_rules.check_document_number_format(DocumentType.PASSPORT, f)
    assert "document_number_format" not in _codes(flags)


def test_indian_style_number_passes():
    # Modern Indian passport numbers carry 2-3 leading letters (e.g. AB series).
    for num in ("AB1234567", "Z1234567", "M2877889", "ABC1234567"):
        f = fields(document_number=num)
        flags = document_rules.check_document_number_format(DocumentType.PASSPORT, f)
        assert "document_number_format" not in _codes(flags), num


def test_aadhaar_12_digit_rule():
    ok = fields(document_number="123412341234")
    assert "document_number_format" not in _codes(
        document_rules.check_document_number_format(DocumentType.AADHAAR, ok)
    )
    bad = fields(document_number="1234-1234-1234")
    assert "document_number_format" in _codes(
        document_rules.check_document_number_format(DocumentType.AADHAAR, bad)
    )


def test_unknown_type_skips_format_check():
    f = fields(document_number="anything!!")
    assert not document_rules.check_document_number_format(DocumentType.UNKNOWN, f)


# --- PAN strict structure -------------------------------------------------------
def test_pan_checksum_valid_clean_document():
    pan = _make_pan(surname="SINGH KUMAR ARJUN", status="P")
    f = fields(document_number=pan, surname="SINGH KUMAR ARJUN")
    flags = document_rules.check_pan_structure(f)
    codes = _codes(flags)
    assert "pan_checksum_ok" in codes
    assert "pan_name_char_match" in codes
    assert "pan_structure_invalid" not in codes
    assert "pan_status_code_invalid" not in codes
    assert "pan_checksum_failed" not in codes


def test_pan_status_code_invalid():
    pan = _make_pan(surname="SINGH", status="P")
    bad = pan[:3] + "X" + pan[4:]
    f = fields(document_number=bad, surname="SINGH")
    flags = document_rules.check_pan_structure(f)
    assert any(fl.code == "pan_status_code_invalid"
               and fl.severity == Severity.WARNING for fl in flags)


def test_pan_5th_char_mismatch_with_name():
    pan = _make_pan(surname="SHARMA", status="P")
    f = fields(document_number=pan, surname="MEHTA")
    flags = document_rules.check_pan_structure(f)
    assert any(fl.code == "pan_name_char_mismatch" for fl in flags)


def test_pan_5th_char_matches_last_word_surname():
    pan = _make_pan(surname="ARJUN KUMAR SINGH", status="P")
    assert pan[4] == "S"
    f = fields(document_number=pan, surname="ARJUN KUMAR SINGH")
    flags = document_rules.check_pan_structure(f)
    assert "pan_name_char_mismatch" not in _codes(flags)


def test_pan_checksum_failure_flags_altered_number():
    pan = _make_pan(surname="SINGH", status="P")
    tampered = pan[:9] + ("A" if pan[9] != "A" else "B")
    assert tampered != pan
    f = fields(document_number=tampered, surname="SINGH")
    flags = document_rules.check_pan_structure(f)
    failed = [fl for fl in flags if fl.code == "pan_checksum_failed"]
    assert len(failed) == 1
    assert failed[0].severity == Severity.WARNING


def test_pan_structure_invalid_on_short_number():
    f = fields(document_number="ABC1234", surname="SINGH")
    flags = document_rules.check_pan_structure(f)
    assert any(fl.code == "pan_structure_invalid" for fl in flags)


def test_pan_missing_number_skips_structure():
    f = fields(document_number=None)
    assert document_rules.check_pan_structure(f) == []


def test_pan_structure_wired_into_run_all_rules():
    pan = _make_pan(surname="SINGH", status="P")
    f = fields(document_number=pan, surname="SINGH")
    flags = document_rules.run_all_rules(DocumentType.PAN_CARD, f)
    codes = _codes(flags)
    assert "pan_checksum_ok" in codes
    assert "pan_name_char_match" in codes


def test_aadhaar_verhoeff_rule_flags_tampered_number():
    import verhoeff

    valid = verhoeff.make_aadhaar_number("23456789012")
    f = fields(document_number=valid)
    flags = document_rules.check_aadhaar_number_checksum(f)
    assert any(fl.code == "aadhaar_checksum_ok" for fl in flags)
    assert not any(fl.code == "aadhaar_checksum_failed" for fl in flags)

    tampered = "234567890187"  # last digit changed from the check digit
    assert tampered != valid
    f2 = fields(document_number=tampered)
    flags2 = document_rules.check_aadhaar_number_checksum(f2)
    assert any(fl.code == "aadhaar_checksum_failed" for fl in flags2)
    assert flags2[0].severity == Severity.HIGH


def test_aadhaar_verhoeff_runs_within_run_all_rules():
    import verhoeff

    valid = verhoeff.make_aadhaar_number("23456789012")
    f = fields(document_number=valid, surname="SINGH", date_of_birth="15/08/1995")
    flags = document_rules.run_all_rules(DocumentType.AADHAAR, f)
    assert any(fl.code == "aadhaar_checksum_ok" for fl in flags)


# --- MRZ compliance ------------------------------------------------------------
def test_clean_mrz_generates_info_verified_flag():
    mrz = parse_mrz(SPECIMEN_TD3_LINES)
    flags = document_rules.check_mrz_compliance(mrz)
    codes = _codes(flags)
    assert "mrz_checks_verified" in codes
    assert "mrz_composite_check_failed" not in codes
    assert "mrz_field_check_failed" not in codes


def test_tampered_mrz_composite_is_high_field_is_warning():
    mrz = parse_mrz([
        SPECIMEN_TD3_LINES[0],
        "L898902D<3UTO6908061F9406236ZE184226B<<<<<14",
    ])
    flags = document_rules.check_mrz_compliance(mrz)
    composite = [f for f in flags if f.code == "mrz_composite_check_failed"]
    field = [f for f in flags if f.code == "mrz_field_check_failed"]
    assert len(composite) == 1
    assert composite[0].severity == Severity.HIGH
    assert len(field) == 1  # document_number field check also fails
    assert field[0].severity == Severity.WARNING
    # the HIGH message must be neutral about the cause
    assert "OCR error, physical" in composite[0].message


def test_unrecognized_mrz_is_warning():
    mrz = parse_mrz(["SHORT", "LINES"])
    flags = document_rules.check_mrz_compliance(mrz)
    assert any(f.code == "mrz_unrecognized"
               and f.severity == Severity.WARNING for f in flags)


def test_no_mrz_flag_absence_no_op():
    assert document_rules.check_mrz_compliance(None) == []


# --- cross-source MRZ vs visual -------------------------------------------------
def test_mrz_visual_dates_match():
    mrz = parse_mrz(SPECIMEN_TD3_LINES)
    f = fields(date_of_birth="06/08/1969", date_of_expiry="23/06/1994")
    flags = document_rules.check_cross_source_consistency(mrz, f, reference_year=2026)
    assert "cross_source_date_mismatch" not in _codes(flags)


def test_mrz_visual_dates_mismatch():
    mrz = parse_mrz(SPECIMEN_TD3_LINES)
    f = fields(date_of_birth="12/08/1974", date_of_expiry="23/06/1994")
    flags = document_rules.check_cross_source_consistency(mrz, f, reference_year=2026)
    assert any(
        fl.code == "cross_source_date_mismatch" and fl.field == "date_of_birth"
        for fl in flags
    )
    assert all(fl.severity == Severity.WARNING for fl in flags)


def test_mrz_visual_doc_number_mismatch_only_with_visual_source():
    mrz = parse_mrz(SPECIMEN_TD3_LINES)
    f = fields(document_number="X9999999")
    flags = document_rules.check_cross_source_consistency(mrz, f, reference_year=2026)
    assert any(fl.code == "cross_source_number_mismatch" for fl in flags)


def test_mrz_visual_same_date_different_format_not_flagged():
    # The exact comparison the design calls out: '1974-08-12' vs MRZ '740812'
    mrz = parse_mrz(SPECIMEN_TD3_LINES)
    f = fields(date_of_birth="1969-08-06", date_of_expiry="1994-06-23")
    flags = document_rules.check_cross_source_consistency(mrz, f, reference_year=1969)
    assert "cross_source_date_mismatch" not in _codes(flags)


def test_unparseable_visual_date_skipped_not_mismatch():
    mrz = parse_mrz(SPECIMEN_TD3_LINES)
    f = fields(date_of_birth="gibberish", date_of_expiry="1994-06-23")
    flags = document_rules.check_cross_source_consistency(mrz, f, reference_year=2026)
    assert "cross_source_date_mismatch" not in _codes(flags)


# --- blacklist -----------------------------------------------------------------
def test_no_blacklist_fn_produces_info_flag():
    f = fields()
    flags = document_rules.run_blacklist_check(f, None)
    assert any(
        fl.code == "blacklist_not_configured" and fl.severity == Severity.INFO
        for fl in flags
    )


def test_blacklist_hit():
    f = fields()
    flags = document_rules.run_blacklist_check(f, lambda _: True)
    assert any(fl.code == "blacklist_hit" for fl in flags)


def test_blacklist_clear():
    f = fields()
    flags = document_rules.run_blacklist_check(f, lambda _: False)
    assert any(fl.code == "blacklist_clear" for fl in flags)


def test_blacklist_lookup_failure_is_warning_not_swallowed():
    f = fields()
    def boom(_):
        raise RuntimeError("db down")
    flags = document_rules.run_blacklist_check(f, boom)
    failed = [fl for fl in flags if fl.code == "blacklist_lookup_failed"]
    assert len(failed) == 1
    assert failed[0].severity == Severity.WARNING


def test_blacklist_none_result_is_warning():
    f = fields()
    flags = document_rules.run_blacklist_check(f, lambda _: None)
    assert any(fl.code == "blacklist_lookup_failed" for fl in flags)


def test_blacklist_query_built_from_fields():
    f = fields(document_number="L898902C", surname="ERIKSSON", given_names=None)
    q = document_rules.build_blacklist_query(f)
    assert q == {"document_number": "L898902C", "surname": "ERIKSSON"}


# --- run_all ---------------------------------------------------------------------
def test_run_all_flags_combined():
    mrz = parse_mrz(SPECIMEN_TD3_LINES)
    f = fields()
    flags = document_rules.run_all_rules(
        DocumentType.PASSPORT, f, mrz=mrz,
        lookup_fn=lambda _: False, reference_year=2026,
    )
    codes = _codes(flags)
    assert "missing_required_field" not in codes
    assert "mrz_checks_verified" in codes
    assert "blacklist_clear" in codes


# --- per-type strategy (anchors / channels / checksums) --------------------------
def _barcode(channel, data=None, signature_present=False):
    from schemas import BarcodeResult
    return BarcodeResult(
        channel=channel,
        format="QRCODE",
        raw="<decoded>",
        data=data or {},
        signature_present=signature_present,
    )


def test_strategy_declares_channels_anchor_checksum_per_type():
    strat = document_rules.DOCUMENT_STRATEGY
    assert strat[DocumentType.AADHAAR].anchor == "aadhaar_qr"
    assert strat[DocumentType.AADHAAR].checksum == "verhoeff"
    assert "qr" in strat[DocumentType.AADHAAR].channels
    assert strat[DocumentType.DRIVING_LICENSE].anchor == "dl_barcode"
    assert "barcode" in strat[DocumentType.DRIVING_LICENSE].channels
    assert strat[DocumentType.PASSPORT].anchor == "mrz"
    assert strat[DocumentType.RESIDENCE_PERMIT].anchor == "mrz"
    # types without a machine-readable zone demand no anchor (never a false
    # negative from a zone that the type cannot carry)
    assert strat[DocumentType.PAN_CARD].anchor is None
    assert strat[DocumentType.VOTER_ID].anchor is None
    assert strat[DocumentType.UNKNOWN].anchor is None


# --- secure-anchor presence -------------------------------------------------------
def test_aadhaar_without_qr_reports_missing_anchor():
    flags = document_rules.check_secure_anchor_presence(
        DocumentType.AADHAAR, mrz=None, barcodes=[]
    )
    assert any(
        fl.code == "secure_anchor_missing" and fl.severity == Severity.WARNING
        for fl in flags
    )


def test_aadhaar_with_qr_anchor_satisfied():
    flags = document_rules.check_secure_anchor_presence(
        DocumentType.AADHAAR, mrz=None,
        barcodes=[_barcode("aadhaar_qr", {"uid": "234567890124"})],
    )
    assert "secure_anchor_missing" not in _codes(flags)


def test_unclassified_barcode_does_not_satisfy_aadhaar_anchor():
    flags = document_rules.check_secure_anchor_presence(
        DocumentType.AADHAAR, mrz=None,
        barcodes=[_barcode("unclassified")],
    )
    assert "secure_anchor_missing" in _codes(flags)


def test_dl_missing_barcode_reports_missing_anchor():
    flags = document_rules.check_secure_anchor_presence(
        DocumentType.DRIVING_LICENSE, mrz=None, barcodes=[]
    )
    assert "secure_anchor_missing" in _codes(flags)


def test_dl_barcode_anchor_satisfied():
    flags = document_rules.check_secure_anchor_presence(
        DocumentType.DRIVING_LICENSE, mrz=None,
        barcodes=[_barcode("dl_barcode", {"document_number": "MH0120300567890"})],
    )
    assert "secure_anchor_missing" not in _codes(flags)


def test_pan_requires_no_anchor():
    flags = document_rules.check_secure_anchor_presence(
        DocumentType.PAN_CARD, mrz=None, barcodes=[]
    )
    assert "secure_anchor_missing" not in _codes(flags)


def test_mrz_anchor_satisfied_by_recognized_mrz():
    mrz = parse_mrz(SPECIMEN_TD3_LINES)
    assert mrz.recognized
    flags = document_rules.check_secure_anchor_presence(
        DocumentType.PASSPORT, mrz=mrz, barcodes=[]
    )
    assert "secure_anchor_missing" not in _codes(flags)


def test_mrz_anchor_missing_when_mrz_unreadable():
    flags = document_rules.check_secure_anchor_presence(
        DocumentType.PASSPORT, mrz=None, barcodes=[]
    )
    assert "secure_anchor_missing" in _codes(flags)


# --- Aadhaar QR cross-source consistency ------------------------------------------
def test_aadhaar_qr_signed_and_checksum_ok_on_clean_document():
    import verhoeff
    number = verhoeff.make_aadhaar_number("23456789012")
    f = fields(document_number=number, date_of_birth="15/08/1995")
    qr = _barcode(
        "aadhaar_qr",
        {"uid": number, "dob": "15/08/1995"},
        signature_present=True,
    )
    flags = document_rules.check_aadhaar_qr_consistency(f, [qr])
    codes = _codes(flags)
    assert "aadhaar_qr_signed_payload" in codes
    assert "aadhaar_qr_checksum_ok" in codes
    assert "aadhaar_qr_number_mismatch" not in codes
    assert "aadhaar_qr_dob_mismatch" not in codes


def test_aadhaar_qr_checksum_failure_high_on_forged_number():
    import verhoeff
    number = verhoeff.make_aadhaar_number("23456789012")
    forged = ("1" if number[0] != "1" else "2") + number[1:]
    assert forged != number
    f = fields(document_number=forged)
    qr = _barcode("aadhaar_qr", {"uid": forged, "dob": "15/08/1995"})
    flags = document_rules.check_aadhaar_qr_consistency(f, [qr])
    failed = next(fl for fl in flags if fl.code == "aadhaar_qr_checksum_failed")
    assert failed.severity == Severity.HIGH


def test_aadhaar_qr_number_mismatch_high():
    import verhoeff
    number = verhoeff.make_aadhaar_number("23456789012")
    other = verhoeff.make_aadhaar_number("99999999997")
    assert other != number
    f = fields(document_number=number)
    qr = _barcode("aadhaar_qr", {"uid": other, "dob": "15/08/1995"})
    flags = document_rules.check_aadhaar_qr_consistency(f, [qr])
    flag = next(fl for fl in flags if fl.code == "aadhaar_qr_number_mismatch")
    assert flag.severity == Severity.HIGH


def test_aadhaar_qr_dob_mismatch_warning():
    import verhoeff
    number = verhoeff.make_aadhaar_number("23456789012")
    f = fields(document_number=number, date_of_birth="01/01/2000")
    qr = _barcode("aadhaar_qr", {"uid": number, "dob": "15/08/1995"})
    flags = document_rules.check_aadhaar_qr_consistency(f, [qr])
    flag = next(fl for fl in flags if fl.code == "aadhaar_qr_dob_mismatch")
    assert flag.severity == Severity.WARNING


def test_aadhaar_qr_consistency_ignored_when_no_qr():
    import verhoeff
    number = verhoeff.make_aadhaar_number("23456789012")
    f = fields(document_number=number)
    assert document_rules.check_aadhaar_qr_consistency(f, []) == []


def test_aadhaar_qr_name_match_and_gender_match_info_flags():
    import verhoeff
    number = verhoeff.make_aadhaar_number("23456789012")
    f = fields(
        document_number=number,
        surname="SINGH KESHAV KUMAR",   # order differs from QR full name
        sex="M",
    )
    qr = _barcode("aadhaar_qr", {
        "uid": number,
        "name": "KESHAV KUMAR SINGH",
        "gender": "MALE",
        "dob": "15/08/1995",
    })
    flags = document_rules.check_aadhaar_qr_consistency(f, [qr])
    codes = _codes(flags)
    assert "aadhaar_qr_name_match" in codes
    assert "aadhaar_qr_gender_match" in codes
    assert "aadhaar_qr_name_mismatch" not in codes
    assert "aadhaar_qr_gender_mismatch" not in codes


def test_aadhaar_qr_name_mismatch_is_warning():
    import verhoeff
    number = verhoeff.make_aadhaar_number("23456789012")
    f = fields(document_number=number, surname="RAHUL SHARMA")
    qr = _barcode("aadhaar_qr", {
        "uid": number,
        "name": "KESHAV KUMAR SINGH",
        "gender": "MALE",
        "dob": "15/08/1995",
    })
    flags = document_rules.check_aadhaar_qr_consistency(f, [qr])
    flag = next(fl for fl in flags if fl.code == "aadhaar_qr_name_mismatch")
    assert flag.severity == Severity.WARNING


def test_aadhaar_qr_gender_mismatch_is_warning():
    import verhoeff
    number = verhoeff.make_aadhaar_number("23456789012")
    f = fields(document_number=number, surname="KESHAV SINGH", sex="M")
    qr = _barcode("aadhaar_qr", {
        "uid": number,
        "name": "KESHAV SINGH",
        "gender": "FEMALE",
        "dob": "15/08/1995",
    })
    flags = document_rules.check_aadhaar_qr_consistency(f, [qr])
    flag = next(fl for fl in flags if fl.code == "aadhaar_qr_gender_mismatch")
    assert flag.severity == Severity.WARNING


# --- side-aware anchor (Aadhaar QR lives on the back) --------------------------
def test_aadhaar_front_only_missing_qr_is_neutral_note_not_evidence():
    flags = document_rules.check_secure_anchor_presence(
        DocumentType.AADHAAR, mrz=None, barcodes=[], input_side="front"
    )
    assert "secure_anchor_missing" not in _codes(flags)
    assert any(
        fl.code == "anchor_not_verifiable" and fl.severity == Severity.INFO
        for fl in flags
    )


def test_aadhaar_unknown_side_missing_qr_is_still_warning():
    flags = document_rules.check_secure_anchor_presence(
        DocumentType.AADHAAR, mrz=None, barcodes=[], input_side=""
    )
    assert "secure_anchor_missing" in _codes(flags)


def test_aadhaar_front_only_with_qr_present_satisfies_anchor():
    flags = document_rules.check_secure_anchor_presence(
        DocumentType.AADHAAR, mrz=None,
        barcodes=[_barcode("aadhaar_qr", {"uid": "234567890124"})],
        input_side="front",
    )
    assert "anchor_not_verifiable" not in _codes(flags)
    assert "secure_anchor_missing" not in _codes(flags)


# --- DL barcode cross-source consistency -------------------------------------------
def test_dl_barcode_number_mismatch_is_high():
    f = fields(document_number="MH0120300567890")
    qr = _barcode("dl_barcode", {"document_number": "MH0120300567891"})
    flag = next(
        fl for fl in document_rules.check_dl_barcode_consistency(f, [qr])
        if fl.code == "dl_barcode_number_mismatch"
    )
    assert flag.severity == Severity.HIGH


def test_dl_barcode_matching_passes_silently():
    f = fields(
        document_number="MH0120300567890", date_of_birth="15/08/1995"
    )
    qr = _barcode(
        "dl_barcode",
        {"document_number": "MH0120300567890", "date_of_birth": "15/08/1995"},
    )
    flags = document_rules.check_dl_barcode_consistency(f, [qr])
    assert not any(fl.code.startswith("dl_barcode") for fl in flags)


def test_dl_barcode_dob_mismatch_warning():
    f = fields(
        document_number="MH0120300567890", date_of_birth="01/01/2000"
    )
    qr = _barcode(
        "dl_barcode",
        {"document_number": "MH0120300567890", "date_of_birth": "15/08/1995"},
    )
    flag = next(
        fl for fl in document_rules.check_dl_barcode_consistency(f, [qr])
        if fl.code == "dl_barcode_dob_mismatch"
    )
    assert flag.severity == Severity.WARNING


def test_run_all_rules_wires_barcode_channels():
    import verhoeff
    number = verhoeff.make_aadhaar_number("23456789012")
    f = fields(document_number=number, date_of_birth="15/08/1995")
    qr = _barcode("aadhaar_qr", {"uid": number, "dob": "15/08/1995"})
    flags = document_rules.run_all_rules(
        DocumentType.AADHAAR, f, barcodes=[qr], lookup_fn=lambda _: False
    )
    codes = _codes(flags)
    assert "aadhaar_checksum_ok" in codes
    assert "aadhaar_qr_checksum_ok" in codes
    assert "secure_anchor_missing" not in codes