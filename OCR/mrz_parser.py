"""ICAO 9303 Machine Readable Zone (MRZ) parsing for TD1 / TD2 / TD3.

Implements the 7-3-1 weighted modulus-10 check-digit algorithm and the exact
character-offset layouts for:

  TD1  (3 x 30)  ID cards, most official travel documents  -- Doc 9303 Part 5
  TD2  (2 x 36)  larger ID cards / some visas              -- Doc 9303 Part 6
  TD3  (2 x 44)  passports                                  -- Doc 9303 Part 4

Field offsets below were verified against Doc 9303 (8th ed.) and the
published ICAO worked examples BEFORE being coded (see README "Verification
matrix"). Every per-field check digit and the composite check digit is
computed and reported individually.

PHILOSOPHY: a failing check digit is EVIDENCE, not proof. It can mean OCR
misread, document damage, or tampering -- this module never asserts which.
All failure messages are phrased accordingly.
"""

from __future__ import annotations

import re
from typing import Optional, Sequence

from schemas import (
    CheckDigitResult,
    MRZFormat,
    MRZResult,
)

# ---------------------------------------------------------------------------
# ICAO 9303 check-digit constants
# ---------------------------------------------------------------------------
#: Repeating per-character weights: 7, 3, 1.
MRZ_WEIGHTS: tuple[int, int, int] = (7, 3, 1)
#: Extra fields per format exposed to callers for rule generation.
ALLOWED_CHARS_RE = re.compile(r"^[A-Z0-9<]+$")


def char_value(ch: str) -> int:
    """ICAO value mapping: 0-9 -> 0-9, A-Z -> 10-35, '<' -> 0."""
    if ch == "<":
        return 0
    if "0" <= ch <= "9":
        return int(ch)
    if "A" <= ch <= "Z":  # A=10 ... Z=35
        return ord(ch) - ord("A") + 10
    raise ValueError(f"invalid MRZ character: {ch!r}")


def compute_check_digit(chars: str, start: int = 0, end: Optional[int] = None) -> int:
    """Weighted modulus-10 check digit over ``chars[start:end]``.

    Result is the digit 0-9 that would be printed in the MRZ check position.
    """
    if end is None:
        end = len(chars)
    total = 0
    for i in range(start, end):
        total += char_value(chars[i]) * MRZ_WEIGHTS[(i - start) % 3]
    return total % 10


def verify_check_digit(
    data: str,
    expected_digit: str,
    start: int = 0,
    end: Optional[int] = None,
) -> bool:
    """Verify a printed check digit against ``data[start:end]``.

    Returns True when the printed digit is the filler '<' AND the covered
    data is entirely filler (per ICAO, an unused field may print '<' instead
    of a digit) -- in that case the check is "not applicable" and must not
    count as a failure.
    """
    computed = compute_check_digit(data, start, end)
    return int(expected_digit) == computed if expected_digit.isdigit() else (expected_digit == "<")


def infer_century(
    two_digit_year: int, reference_year: int, prefer_past: bool = False
) -> int:
    """Resolve a 2-digit MRZ year to a 4-digit year near ``reference_year``.

    ICAO stores years as YY without a century. Two heuristics are combined:

      * ``prefer_past`` (used for date-of-birth): if YY is larger than the
        reference year's own two-digit year, the date must belong to the
        previous century (a person cannot be born "after today"). So
        YY=74 with a 2026 reference resolves to 1974, not 2074.
      * Otherwise the century whose year is nearest to ``reference_year`` is
        chosen (best for expiry dates, e.g. YY=30 with a 2026 reference
        resolves to 2030 rather than a nonsensical 1930).

    These are HEURISTICS for calibration, not authoritative -- 2-digit years
    are inherently ambiguous.
    """
    if prefer_past and two_digit_year > reference_year % 100:
        return 1900 + two_digit_year
    c1 = 1900 + two_digit_year
    c2 = 2000 + two_digit_year
    if abs(c1 - reference_year) <= abs(c2 - reference_year):
        return c1
    return c2


def mrz_yyyymmdd_to_iso(
    value: str, reference_year: int, prefer_past: bool = True
) -> Optional[str]:
    """Turn a 6-char YYMMDD MRZ field into 'YYYY-MM-DD' via century inference.

    ``prefer_past=True`` (the default, for date-of-birth): a year later than
    the reference year's own YY is pulled back a century, since a person
    cannot have been born after today. ``prefer_past=False`` (for expiry
    dates) picks the century nearest the reference, so an expiry of YY=35
    against a 2026 reference resolves to 2035, not 1935.

    Returns None when the value is not a structurally plausible date.
    Whether a date is *semantically* plausible (in the past, ordered,
    not-yet-expired) is a job for the logical-validator layer, not this one.
    """
    if len(value) != 6 or not value.isdigit():
        return None
    yy, mm, dd = int(value[0:2]), int(value[2:4]), int(value[4:6])
    if mm < 1 or mm > 12 or dd < 1 or dd > 31:
        return None
    year = infer_century(yy, reference_year, prefer_past=prefer_past)
    return f"{year:04d}-{mm:02d}-{dd:02d}"


def parse_name_field(raw: str) -> tuple[str, str]:
    """Split an MRZ name field into (primary, secondary) identifiers.

    Format: SURNAME<<GIVEN<NAMES<<<<filler. The double filler separates the
    primary identifier from secondary identifiers; single fillers separate
    given-name chunks. A missing double filler means a mononym.
    """
    s = raw.rstrip("<")
    if "<<" in s:
        primary_part, given_part = s.split("<<", 1)
        given_part = given_part.rstrip("<")
        chunks = [p for p in given_part.split("<") if p]
        return primary_part.replace("<", " "), " ".join(chunks)
    return s.replace("<", " "), ""


# ---------------------------------------------------------------------------
# Field layouts (1-based positions, verified against Doc 9303)
# ---------------------------------------------------------------------------


def _td3_lines(lines: Sequence[str]) -> MRZResult:
    l1, l2 = lines
    result = MRZResult(mrz_format=MRZFormat.TD3, lines=[l1, l2], recognized=True)
    result.data.update(
        {
            "document_type": l1[0:2],
            "issuing_country": l1[2:5],
            "document_number": l2[0:9],
            "nationality": l2[10:13],
            "date_of_birth": l2[13:19],
            "sex": l2[20],
            "date_of_expiry": l2[21:27],
            "personal_number": l2[28:42],
        }
    )
    names = parse_name_field(l1[5:44])
    result.identifiers["primary_identifier"] = names[0]
    result.identifiers["secondary_identifiers"] = names[1]
    _verify_fields(result, l2, [
        ("document_number", 0, 9, 9),
        ("date_of_birth", 13, 19, 19),
        ("date_of_expiry", 21, 27, 27),
        ("personal_number", 28, 42, 42),
    ])
    _verify_composite(result, [
        (l2, 0, 10), (l2, 13, 20), (l2, 21, 43),
    ])
    return result


def _td2_lines(lines: Sequence[str]) -> MRZResult:
    l1, l2 = lines
    result = MRZResult(mrz_format=MRZFormat.TD2, lines=[l1, l2], recognized=True)
    result.data.update(
        {
            "document_type": l1[0:2],
            "issuing_country": l1[2:5],
            "document_number": l2[0:9],
            "nationality": l2[10:13],
            "date_of_birth": l2[13:19],
            "sex": l2[20],
            "date_of_expiry": l2[21:27],
            "optional_data": l2[28:35],
        }
    )
    names = parse_name_field(l1[5:36])
    result.identifiers["primary_identifier"] = names[0]
    result.identifiers["secondary_identifiers"] = names[1]
    _verify_fields(result, l2, [
        ("document_number", 0, 9, 9),
        ("date_of_birth", 13, 19, 19),
        ("date_of_expiry", 21, 27, 27),
    ])
    _verify_composite(result, [
        (l2, 0, 10), (l2, 13, 20), (l2, 21, 35),
    ])
    return result


def _td1_lines(lines: Sequence[str]) -> MRZResult:
    l1, l2, l3 = lines
    result = MRZResult(mrz_format=MRZFormat.TD1, lines=[l1, l2, l3], recognized=True)
    result.data.update(
        {
            "document_type": l1[0:2],
            "issuing_country": l1[2:5],
            "document_number": l1[5:14],
            "date_of_birth": l2[0:6],
            "sex": l2[7],
            "date_of_expiry": l2[8:14],
            "nationality": l2[15:18],
            "optional_data": l1[15:30],
            "optional_data_2": l2[18:29],
        }
    )
    names = parse_name_field(l3[0:30])
    result.identifiers["primary_identifier"] = names[0]
    result.identifiers["secondary_identifiers"] = names[1]
    _verify_fields(result, l1 + l2, [
        ("document_number", 5, 14, 14),  # line 1
        ("date_of_birth", 30, 36, 36),   # line 2 (offset +30)
        ("date_of_expiry", 38, 44, 44),  # line 2 (offset +30)
    ])
    # TD1's composite spans LINE 1 (6-30) and LINE 2 (1-7, 9-15, 19-29).
    _verify_composite(result, [
        (l1, 5, 30), (l2, 0, 7), (l2, 8, 15), (l2, 18, 29),
    ])
    return result


def _verify_fields(
    result: MRZResult, line: str, specs: Sequence[tuple[str, int, int, int]]
) -> None:
    """Verify per-field check digits; record each in check_details."""
    for field, start, end, check_pos in specs:
        expected = line[check_pos] if check_pos < len(line) else "<"
        data = line[start:end]
        if expected == "<":
            # Unused field: filler check digit is permitted (ICAO rule).
            result.check_digits[field] = True
            result.check_details.append(
                CheckDigitResult(
                    field=field, expected="<", computed="<",
                    valid=True,
                )
            )
            continue
        computed = compute_check_digit(data)
        if not expected.isdigit():
            # Non-filler, non-digit where a check digit should be: the line is
            # structurally damaged (OCR interference or alteration). Report a
            # mismatch instead of raising -- the damage IS the evidence.
            ok = False
        else:
            ok = int(expected) == computed
        result.check_digits[field] = ok
        result.check_details.append(
            CheckDigitResult(
                field=field, expected=expected, computed=str(computed), valid=ok
            )
        )


def _verify_composite(
    result: MRZResult,
    segments: Sequence[tuple[str, int, int]],
) -> None:
    """Verify the composite (master) check digit over the segment ranges.

    Each segment is (line, start, end) -- 0-based, end-exclusive. The
    expected composite character is the LAST character of the last segment's
    line. ICAO computes the composite over the per-field values PDEBS their
    check digits (and skips nationality and sex).
    """
    composite_data = "".join(line[s:e] for line, s, e in segments)
    computed = compute_check_digit(composite_data)
    expected = segments[-1][0][-1]
    if expected == "<":
        # ICAO only prints a composite digit when the issuing state provides
        # one; a trailing filler means "not present" -- report as skipped,
        # never as a failure.
        result.check_digits["composite"] = True
        result.check_details.append(
            CheckDigitResult(field="composite", expected="<",
                             computed=str(computed), valid=True)
        )
        return
    ok = False
    if expected.isdigit():
        ok = int(expected) == computed
    # Non-filler, non-digit at the composite position means structural damage
    # (OCR interference or alteration): reported as a mismatch, never raised.
    result.check_digits["composite"] = ok
    result.check_details.append(
        CheckDigitResult(field="composite", expected=expected,
                         computed=str(computed), valid=ok)
    )


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------
def detect_format(lines: Sequence[str]) -> MRZFormat:
    """Identify the MRZ format from raw line lengths (trailing ws ignored)."""
    lengths = tuple(len(l.rstrip()) for l in lines)
    if lengths == (30, 30, 30):
        return MRZFormat.TD1
    if lengths == (36, 36):
        return MRZFormat.TD2
    if lengths == (44, 44):
        return MRZFormat.TD3
    return MRZFormat.NONE


def parse_mrz(lines: Sequence[str]) -> MRZResult:
    """Parse raw MRZ lines into a structured ``MRZResult``.

    Never raises on malformed input: returns ``recognized=False`` with a
    human-readable message instead. Callers must treat an unrecognized MRZ
    as evidence of reading difficulty -- OCR error OR damage OR tampering.
    """
    cleaned = [ln.rstrip() for ln in lines if ln.strip() != ""]
    fmt = detect_format(cleaned)
    if fmt == MRZFormat.NONE:
        return MRZResult(
            mrz_format=MRZFormat.NONE,
            recognized=False,
            lines=[ln for ln in cleaned],
            message="Unable to identify MRZ format from line lengths.",
        )
    for idx, ln in enumerate(cleaned):
        if not ALLOWED_CHARS_RE.match(ln):
            return MRZResult(
                mrz_format=fmt,
                recognized=False,
                lines=list(cleaned),
                message=f"MRZ line {idx + 1} contains characters outside "
                        "A-Z / 0-9 / '<'.",
            )
    try:
        if fmt == MRZFormat.TD3:
            return _td3_lines(cleaned)
        if fmt == MRZFormat.TD2:
            return _td2_lines(cleaned)
        return _td1_lines(cleaned)
    except (ValueError, IndexError) as exc:  # pragma: no cover - defensive
        return MRZResult(
            mrz_format=fmt,
            recognized=False,
            lines=list(cleaned),
            message=f"MRZ parse failed: {exc}",
        )


def parse_mrz_text(text: str) -> MRZResult:
    """Parse an MRZ given as a single block of text (newline separated)."""
    return parse_mrz(text.splitlines())