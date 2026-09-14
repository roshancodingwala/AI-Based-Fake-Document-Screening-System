"""Tests for OpenCV pre-processing using SYNTHETICALLY generated images.

Images are built with cv2.rectangle / cv2.line (rectangular shapes standing
in for text/patterns) and rotated by a KNOWN angle via cv2.getRotationMatrix2D,
so every geometric claim is measured, never assumed. No real document photos
are needed.

Backs this claim with tests:
  * grayscale conversion is idempotent
  * CLAHE measurably increases LOCAL contrast for faint gray-on-gray text on
    a patterned background (pure black-on-white already has max contrast)
  * adaptive threshold output is strictly binary {0,255}
  * skew estimation recovers a known rotation angle within tolerance, and is
    ~0 for an upright image
  * sign convention between angle estimate and deskew correction is verified
    EMPIRICALLY (a sign error doubles the tilt instead of fixing it)
  * the forensic copy and the OCR copies are independent arrays
"""

import cv2
import numpy as np
import pytest

import preprocessing


def _rotate(img, angle, border=255):
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(img, m, (w, h), borderValue=border)


def make_synthetic_document(
    width=800,
    height=500,
    text_value=20,
    background=220,
    pattern=True,
    tilt=0.0,
    seed=42,
    with_mask=False,
):
    """A light, patterned 'paper' with several dark horizontal 'text lines'.

    With ``with_mask=True``, returns ``(image, text_mask)`` where the mask is
    True exactly over the drawn text bars (enables measuring the actual
    text-vs-background separation, i.e., what an OCR stage cares about).
    """
    rng = np.random.default_rng(seed)
    img = np.full((height, width), background, np.uint8)
    mask = np.zeros((height, width), bool)
    if pattern:
        for _ in range(40):
            x0 = int(rng.integers(0, width - 60))
            y0 = int(rng.integers(0, height - 40))
            val = int(rng.integers(int(background) - 25, int(background) + 15))
            cv2.rectangle(img, (x0, y0), (x0 + 60, y0 + 40), val, -1)
    bar_height = 12
    top = height // 4
    for i in range(5):
        y = top + i * (bar_height + 22)
        cv2.rectangle(
            img, (int(width * 0.08), y),
            (int(width * 0.9), y + bar_height), text_value, -1,
        )
        mask[y:y + bar_height, int(width * 0.08):int(width * 0.9)] = True
    if tilt:
        img = _rotate(img, tilt)
    if with_mask:
        return img, mask
    return img


def text_background_separation(img, text_mask):
    """Mean |text - background| intensity gap; 0 means the two cannot be
    told apart by intensity alone, max 255."""
    text = img[text_mask]
    background = img[~text_mask]
    if text.size == 0 or background.size == 0:
        return 0.0
    return float(abs(text.mean() - background.mean()))


# --- grayscale idempotency ----------------------------------------------------
def test_grayscale_conversion_is_idempotent():
    gray = make_synthetic_document()
    once = preprocessing.to_gray(gray)
    twice = preprocessing.to_gray(once)
    assert np.array_equal(once, twice)
    assert once.ndim == 2


def test_grayscale_from_bgr():
    img = make_synthetic_document()
    bgr = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    gray = preprocessing.to_gray(bgr)
    assert gray.ndim == 2
    assert np.array_equal(gray, img)


# --- CLAHE on genuinely low-contrast input ------------------------------------
def test_clahe_increases_local_contrast_for_low_contrast_text():
    # faint gray text (150) on patterned light background (185-220): low
    # contrast, exactly the case CLAHE exists for.
    img, mask = make_synthetic_document(
        text_value=150, background=205, pattern=True, seed=7, with_mask=True,
    )
    before = text_background_separation(img, mask)
    after = text_background_separation(preprocessing.apply_clahe(img), mask)
    assert before > 0, "synthetic must actually be distinguishable"
    assert after > before * 1.05, (
        f"CLAHE should widen text/bg separation, got {before:.1f} -> {after:.1f}"
    )


def test_clahe_weakly_affects_high_contrast_input():
    # pure black-on-white already has maximal separation; CLAHE cannot add
    # much and should not make it worse.
    img, mask = make_synthetic_document(
        text_value=0, background=255, pattern=False, seed=7, with_mask=True,
    )
    before = text_background_separation(img, mask)
    after = text_background_separation(preprocessing.apply_clahe(img), mask)
    assert after < before * 1.15


# --- adaptive threshold binary --------------------------------------------------
def test_adaptive_threshold_is_strictly_binary():
    img = make_synthetic_document()
    binary = preprocessing.adaptive_threshold(preprocessing.apply_clahe(img))
    assert set(np.unique(binary)).issubset({0, 255})
    assert binary.dtype == np.uint8


def test_adaptive_threshold_preserves_shape_of_foreground():
    img = make_synthetic_document()
    binary = preprocessing.adaptive_threshold(preprocessing.apply_clahe(img))
    # some foreground (text=0) and some background (255) must both exist
    assert np.any(binary == 0)
    assert np.any(binary == 255)


# --- skew estimation -------------------------------------------------------------
@pytest.mark.parametrize("tilt", [7.0, -7.0, 5.0, -5.0])
def test_skew_estimation_recovers_known_angle(tilt):
    img = make_synthetic_document(tilt=tilt, seed=11)
    est = preprocessing.estimate_skew_angle(img)
    # sign convention: a getRotationMatrix2D(+tilt) image reads back as -tilt
    assert abs(est - (-tilt)) < 0.75, f"tilt {tilt} -> estimated {est:.3f}"


def test_skew_estimation_upright_image_is_near_zero():
    img = make_synthetic_document(tilt=0.0, seed=13)
    est = preprocessing.estimate_skew_angle(img)
    assert abs(est) < 0.5, f"upright image estimated at {est:.3f}"


def test_empty_image_reports_zero_skew():
    blank = np.full((400, 400), 255, np.uint8)
    assert preprocessing.estimate_skew_angle(blank) == 0.0


# --- sign convention (empirical) ---------------------------------------------------
def test_deskew_sign_convention_residual_smaller_than_tilt():
    # If the sign of the estimated angle were applied backwards, deskewing
    # would DOUBLE the tilt and this assertion would fail.
    tilt = 10.0
    img = make_synthetic_document(tilt=tilt, seed=5)
    est = preprocessing.estimate_skew_angle(img)
    # estimate is the rotation to apply via getRotationMatrix2D
    fixed = preprocessing.deskew(img, est)
    residual = preprocessing.estimate_skew_angle(fixed)
    assert abs(residual) < abs(tilt) / 2, (
        f"residual {residual:.3f} should be smaller than original tilt "
        f"{tilt} -- sign convention is backwards!"
    )
    assert abs(residual) < 0.75


def test_preprocess_image_applies_correction():
    img = make_synthetic_document(tilt=6.0, seed=9)
    pp = preprocessing.preprocess_image(img)
    assert pp.detected_angle == pytest.approx(-6.0, abs=0.75)
    # the OCR-ready copy is now upright
    residual = preprocessing.estimate_skew_angle(pp.ocr_ready)
    assert abs(residual) < 0.75


def test_deskew_clamps_large_angles():
    img = make_synthetic_document(tilt=30.0, seed=3)
    pp = preprocessing.preprocess_image(img)
    assert pp.clamped is True
    assert abs(pp.applied_angle) <= preprocessing.MAX_DESKEW_ANGLE_DEG + 1e-9
    assert "skew_clamped" in pp.flags


# --- two-copy independence ----------------------------------------------------------
def test_forensic_and_ocr_copies_are_independent():
    img = cv2.cvtColor(
        make_synthetic_document(tilt=4.0, seed=17), cv2.COLOR_GRAY2BGR
    )
    pp = preprocessing.preprocess_image(img)
    assert pp.original_rgb is not None

    snap_clahe = pp.clahe_gray.copy()
    snap_ocr = pp.ocr_ready.copy()

    # mutate the forensic copy hard
    pp.original_rgb[:] = np.zeros_like(pp.original_rgb)
    assert np.array_equal(pp.clahe_gray, snap_clahe)
    assert np.array_equal(pp.ocr_ready, snap_ocr)

    # mutate the OCR copy; forensic + other OCR copy unaffected
    pp.ocr_ready[:] = 0
    assert np.array_equal(pp.clahe_gray, snap_clahe)
    assert not np.array_equal(pp.ocr_ready, snap_ocr)
    assert np.unique(pp.original_rgb).tolist() == [0]

    # mutate clahe copy; ocr copy (all zero now) unaffected
    pp.clahe_gray[:] = 123
    assert np.count_nonzero(pp.ocr_ready) == 0


def test_gray_input_independent_copies():
    img = make_synthetic_document(tilt=4.0, seed=19)
    pp = preprocessing.preprocess_image(img)
    assert pp.original_gray is not None
    snap = pp.original_gray.copy()
    snap_clahe = pp.clahe_gray.copy()
    snap_ocr = pp.ocr_ready.copy()
    pp.original_gray[0, 0] = 0
    pp.original_gray[5, 5] = 7
    assert np.array_equal(pp.ocr_ready, snap_ocr)
    assert np.array_equal(pp.clahe_gray, snap_clahe)
    assert not np.array_equal(pp.original_gray, snap)


def test_copies_do_not_share_memory():
    img = cv2.cvtColor(
        make_synthetic_document(tilt=2.0, seed=21), cv2.COLOR_GRAY2BGR
    )
    pp = preprocessing.preprocess_image(img)
    base = pp.original_rgb.flatten().copy()
    # writing into clahe_gray must never alias the forensic copy
    pp.clahe_gray[:] = np.roll(pp.clahe_gray, 1, axis=0)
    assert np.array_equal(pp.original_rgb.flatten(), base)