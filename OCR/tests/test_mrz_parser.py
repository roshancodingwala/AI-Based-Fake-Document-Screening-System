"""Tests for the ICAO 9303 MRZ parser.

Ground truth for every fixture below is a REAL, published ICAO Doc 9303
specimen with known-correct check digits -- NOT self-generated fixtures:

  * TD3 (passport)      Doc 9303 Part 4 worked example (ERIKSSON passport,
                        document number L898902C with per-field check digits
                        3 / 1 / 6 / 1 and composite check digit 4).
  * TD1 (ID card)       Doc 9303 Part 5 App. B worked example (Utopia ID,
                        doc number D23145890, checks 7 / 2 / 9, composite 6).
  * TD2 (ID card)       Doc 9303 Part 6 App. B worked example (doc number
                        D23145890, checks 7 / 2 / 9, composite 6).

Field-offset layouts were verified against ICAO Doc 9303 before implementation
(see README "Verification matrix").
"""

import pytest

import mrz_parser

SPECIMEN_TD3_LINES = [
    "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<",
    "L898902C<3UTO6908061F9406236ZE184226B<<<<<14",
]
SPECIMEN_TD1_LINES = [
    "I<UTOD231458907<<<<<<<<<<<<<<<",
    "7408122F1204159UTO<<<<<<<<<<<6",
    "ERIKSSON<<ANNA<MARIA<<<<<<<<<<",
]
SPECIMEN_TD2_LINES = [
    "I<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<",
    "D231458907UTO7408122F1204159<<<<<<<6",
]


# ---------------------------------------------------------------------------
# Check-digit algorithm -- verified against the real ICAO specimen values
# ---------------------------------------------------------------------------
def test_check_digit_algorithm_matches_icao_specimen():
    # Each check digit printed in the real specimen must equal what the
    # 7-3-1 algorithm computes over its field.
    l2 = SPECIMEN_TD3_LINES[1]
    assert mrz_parser.compute_check_digit(l2[0:9]) == 3   # document number
    assert mrz_parser.compute_check_digit(l2[13:19]) == 1  # date of birth
    assert mrz_parser.compute_check_digit(l2[21:27]) == 6  # expiry
    assert mrz_parser.compute_check_digit(l2[28:42]) == 1  # personal number
    # composite over positions 1-10, 14-20, 22-43 (1-based)
    composite = l2[0:10] + l2[13:20] + l2[21:43]
    assert mrz_parser.compute_check_digit(composite) == 4


def test_char_value_mapping():
    assert mrz_parser.char_value("<") == 0
    assert mrz_parser.char_value("7") == 7
    assert mrz_parser.char_value("A") == 10
    assert mrz_parser.char_value("Z") == 35
    with pytest.raises(ValueError):
        mrz_parser.char_value("ä")


def test_workbook_example_ab2134():
    # ICAO 9303 workbook example: AB2134<<< -> check digit 5.
    assert mrz_parser.compute_check_digit("AB2134<<<") == 5


# ---------------------------------------------------------------------------
# TD3 -- real ICAO specimen parsing
# ---------------------------------------------------------------------------
def test_parse_td3_specimen_fields():
    result = mrz_parser.parse_mrz(SPECIMEN_TD3_LINES)
    assert result.recognized is True
    assert result.mrz_format.value == "TD3"
    d = result.data
    assert d["document_type"] == "P<"
    assert d["issuing_country"] == "UTO"
    assert d["document_number"] == "L898902C<"
    assert d["nationality"] == "UTO"
    assert d["date_of_birth"] == "690806"
    assert d["sex"] == "F"
    assert d["date_of_expiry"] == "940623"
    assert d["personal_number"] == "ZE184226B<<<<<"
    assert result.identifiers["primary_identifier"] == "ERIKSSON"
    assert result.identifiers["secondary_identifiers"] == "ANNA MARIA"


def test_parse_td3_specimen_check_digits_all_valid():
    result = mrz_parser.parse_mrz(SPECIMEN_TD3_LINES)
    assert result.check_digits == {
        "document_number": True,
        "date_of_birth": True,
        "date_of_expiry": True,
        "personal_number": True,
        "composite": True,
    }


def test_tampered_field_breaks_its_own_and_composite_checksum():
    # Change the printed document number but leave its (now-wrong) check
    # digit untouched: BOTH the field checksum AND the composite must fail.
    tampered = [
        SPECIMEN_TD3_LINES[0],
        "L898902D<3UTO6908061F9406236ZE184226B<<<<<14",
    ]
    result = mrz_parser.parse_mrz(tampered)
    assert result.recognized is True
    assert result.check_digits["document_number"] is False
    assert result.check_digits["date_of_birth"] is True
    assert result.check_digits["composite"] is False


def test_tampered_dob_breaks_dob_and_composite():
    # 690806 -> 680806: changes the printed DOB but not its check digit.
    tampered = [
        SPECIMEN_TD3_LINES[0],
        "L898902C<3UTO6808061F9406236ZE184226B<<<<<14",
    ]
    result = mrz_parser.parse_mrz(tampered)
    assert result.check_digits["date_of_birth"] is False
    assert result.check_digits["composite"] is False


def test_sex_change_does_not_break_composite():
    # Sex (position 21) is intentionally excluded from the composite check.
    changed_sex = [
        SPECIMEN_TD3_LINES[0],
        "L898902C<3UTO6908061M9406236ZE184226B<<<<<14",
    ]
    result = mrz_parser.parse_mrz(changed_sex)
    assert result.check_digits["date_of_birth"] is True
    assert result.check_digits["composite"] is True


# ---------------------------------------------------------------------------
# TD1 & TD2 -- real ICAO specimens parsing
# ---------------------------------------------------------------------------
def test_parse_td1_specimen():
    result = mrz_parser.parse_mrz(SPECIMEN_TD1_LINES)
    assert result.recognized is True
    assert result.mrz_format.value == "TD1"
    assert result.data["document_number"] == "D23145890"
    assert result.data["date_of_birth"] == "740812"
    assert result.data["date_of_expiry"] == "120415"
    assert result.data["nationality"] == "UTO"
    assert result.data["sex"] == "F"
    assert result.data["document_type"] == "I<"
    assert result.identifiers["primary_identifier"] == "ERIKSSON"
    assert result.identifiers["secondary_identifiers"] == "ANNA MARIA"
    # TD1 specimen: check digits 7 (doc), 2 (dob), 9 (expiry), 6 (composite)
    assert result.check_digits["document_number"] is True
    assert result.check_digits["date_of_birth"] is True
    assert result.check_digits["date_of_expiry"] is True
    assert result.check_digits["composite"] is True


def test_parse_td2_specimen():
    result = mrz_parser.parse_mrz(SPECIMEN_TD2_LINES)
    assert result.recognized is True
    assert result.mrz_format.value == "TD2"
    assert result.data["document_number"] == "D23145890"
    assert result.data["date_of_birth"] == "740812"
    assert result.data["date_of_expiry"] == "120415"
    assert result.data["optional_data"] == "<<<<<<<"
    assert result.identifiers["primary_identifier"] == "ERIKSSON"
    assert result.identifiers["secondary_identifiers"] == "ANNA MARIA"
    assert result.check_digits["document_number"] is True
    assert result.check_digits["composite"] is True


def test_td1_tamper_composite_breaks():
    # Change the printed document number D23145890 -> D23145897, leaving the
    # (now wrong) check digit '7' in place.
    result = mrz_parser.parse_mrz([
        "I<UTOD231458977<<<<<<<<<<<<<<<",
        SPECIMEN_TD1_LINES[1],
        SPECIMEN_TD1_LINES[2],
    ])
    assert result.recognized is True
    assert result.check_digits["document_number"] is False
    assert result.check_digits["composite"] is False


def test_parse_damaged_line_does_not_raise():
    # A letter drifting into a check-digit column (e.g. OCR dropping one
    # interior column shifts the layout) must yield a recognized=True result
    # with that check reported INVALID -- never an exception.
    line2 = ("L898902C<3UTO6908061F9406236ZE184226B<<<<<14")[:-1]
    mangled = "M28778899IND9509148M2410269<<<<8".ljust(44, "<")
    result = mrz_parser.parse_mrz([
        "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<",
        mangled,
    ])
    assert result.recognized is True
    assert result.check_digits["document_number"] is False


# ---------------------------------------------------------------------------
# Format detection / malformed input
# ---------------------------------------------------------------------------
def test_detect_format():
    assert mrz_parser.detect_format(SPECIMEN_TD1_LINES).value == "TD1"
    assert mrz_parser.detect_format(SPECIMEN_TD2_LINES).value == "TD2"
    assert mrz_parser.detect_format(SPECIMEN_TD3_LINES).value == "TD3"
    assert mrz_parser.detect_format(["abc", "def"]).value == "NONE"


def test_malformed_lines_do_not_raise():
    result = mrz_parser.parse_mrz(["SHORT_LINE", "ALSO_SHORT"])
    assert result.recognized is False
    assert result.message != ""


def test_invalid_characters_reported():
    result = mrz_parser.parse_mrz([
        "I<UTOD231458907<<<<<<<<<<<<<<<",
        "7408122F12ä4159UTO<<<<<<<<<<<6",
        "ERIKSSON<<ANNA<MARIA<<<<<<<<<<",
    ])
    assert result.recognized is False
    assert "outside" in result.message


# ---------------------------------------------------------------------------
# Century inference
# ---------------------------------------------------------------------------
def test_infer_century_prefers_nearest_century():
    assert mrz_parser.infer_century(69, 1970) == 1969
    assert mrz_parser.infer_century(69, 2026, prefer_past=True) == 1969
    assert mrz_parser.infer_century(12, 2026) == 2012
    assert mrz_parser.infer_century(99, 1980) == 1999
    # nearest-century applies for non-birth dates (expiry).
    assert mrz_parser.infer_century(30, 2026) == 2030
    # prefer_past (DOB) forces the previous century when YY > ref YY.
    assert mrz_parser.infer_century(30, 2026, prefer_past=True) == 1930


def test_mrz_yyyymmdd_to_iso():
    assert mrz_parser.mrz_yyyymmdd_to_iso("690806", 1969) == "1969-08-06"
    assert mrz_parser.mrz_yyyymmdd_to_iso("740812", 2026) == "1974-08-12"
    assert mrz_parser.mrz_yyyymmdd_to_iso("120415", 1975) == "2012-04-15"
    assert mrz_parser.mrz_yyyymmdd_to_iso("not-a-date", 2026) is None
    assert mrz_parser.mrz_yyyymmdd_to_iso("130000", 2026) is None
    assert mrz_parser.mrz_yyyymmdd_to_iso("000000", 2026) is None


# ---------------------------------------------------------------------------
# Name-field parsing
# ---------------------------------------------------------------------------
def test_name_field_parsing():
    assert mrz_parser.parse_name_field(
        "ERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<"
    ) == ("ERIKSSON", "ANNA MARIA")
    assert mrz_parser.parse_name_field("MUSTERMANN<<ERIKA") == ("MUSTERMANN", "ERIKA")
    assert mrz_parser.parse_name_field("<") == ("", "")
    assert mrz_parser.parse_name_field("SINGLENESS") == ("SINGLENESS", "")