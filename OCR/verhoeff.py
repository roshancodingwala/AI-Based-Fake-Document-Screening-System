"""Verhoeff checksum -- the algorithm the UIDAI uses for Aadhaar numbers.

A 12-digit Aadhaar number embeds a Verhoeff check digit as its final digit,
so an altered or mis-OCR'd number fails the checksum ~90% of the time. The
checksum is structural evidence only (a passing checksum proves nothing by
itself -- numbers are not secret); a FAILING checksum is strong evidence of a
mis-OCR or a fabricated number.
"""

from __future__ import annotations

_D: list[list[int]] = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]

_P: list[list[int]] = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]

_INV: list[int] = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def _digits(number) -> list[int]:
    if not isinstance(number, str):
        number = str(number)
    return [int(ch) for ch in number if ch.isdigit()]


def verhoeff_check_digit(number) -> int:
    """Compute the Verhoeff check digit for ``number`` (without check digit)."""
    c = 0
    for i, digit in enumerate(reversed(_digits(number))):
        c = _D[c][_P[(i + 1) % 8][digit]]
    return _INV[c]


def verify_verhoeff(number) -> bool:
    """Validate a number whose final digit is its Verhoeff check digit."""
    c = 0
    for i, digit in enumerate(reversed(_digits(number))):
        c = _D[c][_P[i % 8][digit]]
    return c == 0


def make_aadhaar_number(prefix: str) -> str:
    """Complete an 11-digit Aadhaar prefix with its Verhoeff check digit."""
    return str(prefix).strip() + str(verhoeff_check_digit(prefix))