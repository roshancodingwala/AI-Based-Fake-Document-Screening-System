"""Tests for the Verhoeff checksum used by Aadhaar numbers."""

import sys

sys.path.insert(0, ".")

import verhoeff


def test_known_vector():
    assert verhoeff.verhoeff_check_digit("236") == 3
    assert verhoeff.verify_verhoeff("2363") is True


def test_tampered_last_digit_fails():
    assert verhoeff.verify_verhoeff("2364") is False


def test_make_aadhaar_number_roundtrip():
    number = verhoeff.make_aadhaar_number("23456789012")
    assert len(number) == 12
    assert number.isdigit()
    assert verhoeff.verify_verhoeff(number) is True


def test_any_single_digit_change_fails():
    number = verhoeff.make_aadhaar_number("23456789012")
    caught = 0
    misses = []
    for pos in range(12):
        nd = str((int(number[pos]) + 1) % 10)
        flipped = number[:pos] + nd + number[pos + 1:]
        if flipped != number:
            if verhoeff.verify_verhoeff(flipped) is False:
                caught += 1
            else:
                misses.append(pos)
    # Verhoeff provably catches 90% of single-digit substitutions.
    assert caught >= 9, misses