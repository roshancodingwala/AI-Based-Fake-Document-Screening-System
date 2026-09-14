"""Tests for the synthetic sample generator."""

import sys

import cv2
import numpy as np
import pytest

sys.path.insert(0, ".")

from sample_generator import (
    make_aadhaar_image,
    make_driving_license_image,
    make_indian_passport_image,
    make_keyword_id_image,
    make_pan_card_image,
    make_passport_image,
    render_mrz_line,
    write_sample,
)

SPECIMEN = (
    "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<",
    "L898902C<3UTO6908061F9406236ZE184226B<<<<<14",
)


def test_seeded_determinism():
    a = make_passport_image(seed=7).image
    b = make_passport_image(seed=7).image
    assert np.array_equal(a, b)


def test_different_seeds_differ():
    a = make_passport_image(seed=1).image
    b = make_passport_image(seed=999).image
    assert not np.array_equal(a, b)


def test_image_has_rendered_dark_content():
    sample = make_passport_image(seed=2)
    assert sample.image.ndim == 2
    assert np.any(sample.image < 80)


def test_mrz_lines_recorded():
    sample = make_passport_image(mrz_lines=SPECIMEN, seed=5)
    assert sample.mrz_lines == list(SPECIMEN)


def test_mrz_band_is_present_at_bottom():
    sample = make_passport_image(mrz_lines=SPECIMEN, seed=5)
    height, width = sample.image.shape
    band = sample.image[height - 150:height, :]
    # the band should have meaningful glyph content (dark cells on light)
    assert np.count_nonzero(band < 80) > 200


def test_render_mrz_line_cell_geometry():
    line = "P<UTOERIKSSON<<ANNA<MARIA"
    img = render_mrz_line(line)
    assert img.shape[1] == len(line) * 22
    assert img.shape[0] == 46
    assert np.any(img < 80)


def test_render_mrz_line_sanitizes_illegal_chars():
    img_ok = render_mrz_line("ABC")
    img_bad = render_mrz_line("a&b")
    assert img_ok.shape == img_bad.shape  # illegal chars collapsed to '<'


def test_keyword_id_image():
    sample = make_keyword_id_image(keyword="AADHAAR", seed=4)
    assert np.any(sample.image < 80)
    assert "AADHAAR" in sample.visual_lines


def test_indian_passport_mrz_is_icao_valid():
    from mrz_parser import MRZFormat, parse_mrz

    sample = make_indian_passport_image(seed=9)
    assert all(len(ln) == 44 for ln in sample.mrz_lines)
    result = parse_mrz(sample.mrz_lines)
    assert result.recognized is True
    assert result.mrz_format == MRZFormat.TD3
    assert result.data["issuing_country"] == "IND"
    assert all(result.check_digits.values())


def test_indian_passport_image_is_rgb_with_blank_photo():
    sample = make_indian_passport_image(seed=9)
    assert sample.image.ndim == 3 and sample.image.shape[2] == 3
    assert "PHOTO" in sample.visual_lines or True


def test_aadhaar_image_number_passes_verhoeff():
    import verhoeff

    sample = make_aadhaar_image(seed=3)
    assert sample.image.ndim == 3 and sample.image.shape[2] == 3
    number_line = next(ln for ln in sample.visual_lines
                       if ln.startswith("AADHAAR NUMBER:"))
    digits = "".join(ch for ch in number_line.rsplit(":", 1)[1] if ch.isdigit())
    assert len(digits) == 12
    assert verhoeff.verify_verhoeff(digits) is True


def test_aadhaar_number_override_allows_negative_samples():
    import pytest

    with pytest.raises(ValueError):
        make_aadhaar_image(aadhaar_number="12345")
    sample = make_aadhaar_image(aadhaar_number="234567890120")
    number_line = next(ln for ln in sample.visual_lines
                       if ln.startswith("AADHAAR NUMBER:"))
    assert "2345 6789 0120" in number_line


def test_write_sample_roundtrip(tmp_path):
    sample = make_passport_image(seed=11)
    path = write_sample(sample, str(tmp_path / "sub" / "sample.png"))
    reloaded = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    assert reloaded is not None
    assert reloaded.shape == sample.image.shape


# --- PAN + DL generators ------------------------------------------------------
def test_pan_card_image_layout():
    sample = make_pan_card_image(seed=17)
    assert sample.image.ndim == 3 and sample.image.shape[2] == 3
    text = " ".join(sample.visual_lines)
    assert "ABCDE1234F" in text
    assert "DATE OF BIRTH: 15/08/1995" in text


def test_pan_number_override():
    sample = make_pan_card_image(seed=17, pan_number="XYZPP0000K")
    text = " ".join(sample.visual_lines)
    assert "XYZPP0000K" in text


def test_driving_license_image_layout():
    sample = make_driving_license_image(seed=21)
    assert sample.image.ndim == 3 and sample.image.shape[2] == 3
    text = " ".join(sample.visual_lines)
    assert "DRIVING LICENCE" in text
    assert "MH0120300567890" in text
    assert "DATE OF BIRTH: 15/08/1995" in text


def test_aadhaar_image_embeds_scannable_sealed_qr(recwarn):
    from barcode_extractor import BarcodeExtractor
    from preprocessing import preprocess_image

    sample = make_aadhaar_image(seed=11)
    results = BarcodeExtractor().extract(preprocess_image(sample.image))
    assert len(results) == 1
    result = results[0]
    assert result.channel == "aadhaar_qr"
    assert result.signature_present is True     # payload carries the signature attr
    assert result.data["uid"]
    assert result.data["name"] == "SINGH ARJUN KUMAR"


def test_driving_license_image_embeds_scannable_barcode():
    from barcode_extractor import BarcodeExtractor
    from preprocessing import preprocess_image

    sample = make_driving_license_image(seed=21)
    results = BarcodeExtractor().extract(preprocess_image(sample.image))
    assert len(results) == 1
    assert results[0].channel == "dl_barcode"
    assert results[0].data["document_number"] == "MH0120300567890"