"""OpenCV pre-processing for document images.

Pipeline:  deskew -> grayscale -> CLAHE -> adaptive (local) threshold.

Deskew here is a REFINEMENT for small residual tilt AFTER upstream
perspective correction -- it is clamped to a small max angle so it can never
"correct" a genuinely 90-degree-rotated capture into something worse.

TWO-COPY CONTRACT
    `preprocess_image` returns BOTH:
      * a deskewed, PIXEL-UNTOUCHED copy (for later forensic / tamper
        analysis, which needs real pixel statistics, not thresholded
        artifacts), and
      * a separate OCR-ready copy (grayscale + CLAHE + adaptive threshold).
    The two are genuinely independent arrays -- mutating one must never
    affect the other (enforced by a test, not by assumption).

ANGLE CONVENTION (verified empirically -- see tests/test_preprocessing.py)
    `estimate_skew_angle` returns the signed rotation (degrees) to apply via
    `cv2.getRotationMatrix2D` to straighten the image. It is measured as a
    length-weighted mean of Hough-detected text-line directions: for a
    region rotated by ``theta`` via ``getRotationMatrix2D(center, theta, 1.0)``
    the estimator returns ``-theta``, so ``deskew(img, estimate(img))`` fully
    corrects it.
    (OpenCV's ``minAreaRect`` angle is NOT used: its returned angle/size are
    version-dependent -- observed returning +80 for a -10 deg tilt on
    OpenCV 4.11 -- and require fragile w/h heuristics. PCA likewise biases to
    0 for wide multi-line blocks.)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np


def _empty_uint8():
    return np.zeros((1, 1), dtype=np.uint8)

# ---------------------------------------------------------------------------
# Tunable constants -- STARTING VALUES for calibration against real
# checkpoint-camera samples, not authoritative.
# ---------------------------------------------------------------------------
#: Upper bound (degrees) for deskew correction. Kept small on purpose: this
#: handles residual tilt only; real 90-degree rotations are the upstream
#: perspective-correction stage's job.
MAX_DESKEW_ANGLE_DEG: float = 8.0
#: CLAHE clip limit for contrast limiting. Calibrated so faint
#: gray-on-gray text separation grows measurably (text/bg mean gap), while
#: already-maximal-contrast text is left close to untouched.
CLAHE_CLIP_LIMIT: float = 4.0
#: CLAHE tile grid.
CLAHE_TILE_GRID: tuple[int, int] = (8, 8)
#: Adaptive threshold block size (auto-raised to odd).
ADAPTIVE_BLOCK_SIZE: int = 35
#: Adaptive threshold constant subtracted from the mean.
ADAPTIVE_C: int = 10
#: Minimum white pixels before skew estimation is attempted.
SKEW_MIN_POINTS: int = 50
#: Text is considered dark (0) on light (255) after our binarization.
_TEXT_VALUE: int = 0
#: Canny hysteresis thresholds on the binary edge map.
_CANNY_LOW: int = 100
_CANNY_HIGH: int = 200
#: Hough accumulator threshold (votes).
_HOUGH_THRESHOLD: int = 60
#: Min Hough line length (px) -- text baselines are longer than specks.
_HOUGH_MIN_LENGTH: int = 40
#: Max gap between Hough collinear fragments.
_HOUGH_MAX_GAP: int = 10
#: Lines shorter than this (px) are ignored for angle weighting.
_MIN_LINE_WEIGHT: int = 20


@dataclass
class PreprocessedDocument:
    """Output of ``preprocess_image``.

    ``original_rgb`` (or ``original_gray`` for single-channel input) is the
    deskewed, pixel-untouched copy for forensic analysis. ``clahe_gray`` and
    ``ocr_ready`` are the OCR-facing copies (thresholded is strictly 0/255).
    """

    original_rgb: Optional[np.ndarray] = None
    original_gray: Optional[np.ndarray] = None
    clahe_gray: np.ndarray = field(default_factory=_empty_uint8)
    ocr_ready: np.ndarray = field(default_factory=_empty_uint8)
    detected_angle: float = 0.0
    applied_angle: float = 0.0
    clamped: bool = False
    flags: list[str] = field(default_factory=list)


def to_gray(image: np.ndarray) -> np.ndarray:
    """Convert BGR -> gray. Idempotent for single-channel input."""
    if image.ndim == 2:
        return image
    if image.ndim == 3 and image.shape[2] == 1:
        return image[:, :, 0]
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def apply_clahe(
    gray: np.ndarray,
    clip_limit: float = CLAHE_CLIP_LIMIT,
    tile_grid: tuple[int, int] = CLAHE_TILE_GRID,
) -> np.ndarray:
    """Contrast enhancement via CLAHE on a grayscale image."""
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid)
    return clahe.apply(gray)


def adaptive_threshold(
    gray: np.ndarray,
    block_size: int = ADAPTIVE_BLOCK_SIZE,
    c: int = ADAPTIVE_C,
) -> np.ndarray:
    """Local adaptive threshold -> STRICTLY binary 0/255 (text dark = 0).

    Local (per-block) thresholding is used instead of a global one because
    checkpoint photos have uneven lighting across the surface.
    """
    if block_size % 2 == 0:
        block_size += 1
    if block_size < 3:
        block_size = 3
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY, block_size, c,
    )
    return binary


def estimate_skew_angle(
    gray: np.ndarray,
    min_points: int = SKEW_MIN_POINTS,
) -> float:
    """Estimate the residual rotation needed to straighten ``gray``.

    Implementation: adaptive-threshold, edge-detect, probabilistic Hough,
    then a length-weighted mean of detected line angles (folded to the
    [-45, 45] band). Returns the signed angle (degrees) to feed
    ``cv2.getRotationMatrix2D`` to straighten the image -- positive rotates
    clockwise visually, per the sign convention verified empirically in
    tests (a ``+theta``-rotated image reads back as ``-theta``).

    Uses line directions, NOT PCA: a wide multi-line block has an x-extent
    that is almost invariant to small rotations, which biases PCA strongly
    toward 0 (a bias readily demonstrated on synthetic wide bars). Line
    baselines rotate with the text, so they are the faithful signal.

    Returns 0.0 when the image is essentially empty (no edges detected).
    """
    binary = adaptive_threshold(gray)
    if np.count_nonzero(binary <= _TEXT_VALUE) < min_points:
        return 0.0
    text_on_white = (binary == _TEXT_VALUE).astype(np.uint8) * 255
    edges = cv2.Canny(text_on_white, _CANNY_LOW, _CANNY_HIGH)
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180, _HOUGH_THRESHOLD,
        minLineLength=_HOUGH_MIN_LENGTH, maxLineGap=_HOUGH_MAX_GAP,
    )
    if lines is None or len(lines) == 0:
        return 0.0
    angles = []
    weights = []
    for x1, y1, x2, y2 in lines.reshape(-1, 4):
        length = math.hypot(x2 - x1, y2 - y1)
        if length < _MIN_LINE_WEIGHT:
            continue
        ang = math.degrees(math.atan2(y2 - y1, x2 - x1))
        if ang > 45.0:
            ang -= 90.0
        elif ang < -45.0:
            ang += 90.0
        angles.append(ang)
        weights.append(length)
    if not angles:
        return 0.0
    angles_arr = np.asarray(angles)
    weights_arr = np.asarray(weights)
    return float(np.average(angles_arr, weights=weights_arr))


def deskew(image: np.ndarray, angle: float) -> np.ndarray:
    """Rotate ``image`` by ``angle`` degrees about its center via
    ``getRotationMatrix2D`` (verifiable sign convention, see module doc).

    The canvas is expanded so no content is clipped; edges are replicated.
    """
    h, w = image.shape[:2]
    center = (w / 2.0, h / 2.0)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    abs_cos = abs(matrix[0, 0])
    abs_sin = abs(matrix[0, 1])
    new_w = int(h * abs_sin + w * abs_cos)
    new_h = int(h * abs_cos + w * abs_sin)
    matrix[0, 2] += (new_w - w) / 2.0
    matrix[1, 2] += (new_h - h) / 2.0
    return cv2.warpAffine(
        image, matrix, (new_w, new_h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )


def preprocess_image(
    image: np.ndarray,
    *,
    max_angle: float = MAX_DESKEW_ANGLE_DEG,
    clahe_clip_limit: float = CLAHE_CLIP_LIMIT,
    clahe_tile_grid: tuple[int, int] = CLAHE_TILE_GRID,
    adaptive_block_size: int = ADAPTIVE_BLOCK_SIZE,
    adaptive_c: int = ADAPTIVE_C,
) -> PreprocessedDocument:
    """Full pre-processing pipeline honoring the two-copy contract.

    ``image`` is expected BGR (OpenCV convention) or grayscale.
    """
    if image.ndim not in (2, 3):
        raise ValueError("image must be 2-D gray or 3-channel BGR")

    input_is_gray = image.ndim == 2
    gray_base = to_gray(image)
    detected = estimate_skew_angle(gray_base)
    applied = max(-max_angle, min(detected, max_angle))
    clamped = abs(detected) > max_angle

    # 1) forensic copy: deskewed, pixel values untouched
    deskewed = deskew(image, applied)
    # 2) OCR-ready copies, derived independently
    gray = to_gray(deskewed)
    if input_is_gray:
        # the deskewed gray doubles as the untouched forensic copy
        original_gray = deskewed
        original_rgb = None
    else:
        original_rgb = deskewed
        original_gray = None
    clahe_gray = apply_clahe(gray, clahe_clip_limit, clahe_tile_grid)
    ocr_ready = adaptive_threshold(clahe_gray, adaptive_block_size, adaptive_c)

    flags = []
    if abs(detected) > max_angle:
        flags.append("skew_clamped")
    if float(np.std(gray)) < 1.0:
        flags.append("blank_image")

    return PreprocessedDocument(
        original_rgb=original_rgb,
        original_gray=original_gray,
        clahe_gray=clahe_gray,
        ocr_ready=ocr_ready,
        detected_angle=detected,
        applied_angle=applied,
        clamped=clamped,
        flags=flags,
    )