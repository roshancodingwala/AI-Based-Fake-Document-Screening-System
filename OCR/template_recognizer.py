"""Structure-aware template ROI OCR.

Where the free-text recognizer scans the whole page and regexes labels out,
template recognition uses a registered ``schemas.DocumentTemplate`` -- a set
of fractional ROIs -- to crop exactly where a printed field lives and OCR
only inside that region. A geometry-bound crop is far more robust to stray
text (disclaimers, QR codes, background print) than whole-page regexing,
which is the way to get box-accurate extraction for fixed-layout documents
(the "perfect intelligent OCR" route).

The engine wires this on top of the same OCR extractor: each ROI is cropped
from the CLAHE copy (the same copy a normal OCR pass consumes), upsampled,
preprocessed and OCR'd on its own. Values are normalized per field
(``document_number`` -> digits only, date fields -> a single date token),
so a crop that is slightly off still yields a clean value instead of prose.
"""

from __future__ import annotations

import re
from typing import Callable, Optional, Sequence

import cv2
import numpy as np

from ocr_extractor import OCRTextLine
from preprocessing import preprocess_image
from schemas import DocumentTemplate, DocumentType, ExtractedField, FieldSource, ROIField

#: Upscaling factor for ROI crops -- small regions OCR far better at 3x.
_UPSAMPLE: int = 3

FieldCleaner = Callable[[str], str]

_DATE_TOKEN = re.compile(r"\d{1,4}[/.-]\d{1,2}[/.-]\d{2,4}")
_SEX_TOKEN = re.compile(r"(male|female|M|F)", re.I)
_SPACE_RUN = re.compile(r"\s+")


def _clean_date(text: str) -> str:
    match = _DATE_TOKEN.search(text)
    return match.group(0) if match else _SPACE_RUN.sub("", text)


def _clean_sex(text: str) -> str:
    match = _SEX_TOKEN.search(text)
    return match.group(1).upper() if match else text.strip()


_CLEANERS: dict[str, FieldCleaner] = {
    # Keep A-Z/0-9 only: Aadhaar (digits), PAN (ABCDE1234F) and DL
    # (MH01200500889) numbers all survive; spaces/dashes/fillers are dropped.
    "document_number": lambda text: re.sub(r"[^A-Z0-9]", "", text.upper()),
    "date_of_birth": _clean_date,
    "date_of_expiry": _clean_date,
    "issue_date": _clean_date,
    "sex": _clean_sex,
}


# ---------------------------------------------------------------------------
# Registered templates
# ---------------------------------------------------------------------------
#: Paper Aadhaar letter layout (the common "Aadhaar letter" format, matched
#: against a real photo): header band, then Name / Date of Birth / Sex rows,
#: the 12-digit Aadhaar number near the bottom. Fractions measured from a
#: 1755 x 1240 photo (ROIs span value regions, wider than the glyph run so a
#: slightly skewed scan never clips a letter).
AADHAAR_LETTER_TEMPLATE = DocumentTemplate(
    document_type=DocumentType.AADHAAR,
    rois=[
        ROIField(name="surname", x0=0.31, y0=0.220, x1=0.72, y1=0.272),
        ROIField(name="date_of_birth", x0=0.30, y0=0.280, x1=0.99, y1=0.325),
        ROIField(name="sex", x0=0.30, y0=0.330, x1=0.60, y1=0.375),
        ROIField(name="document_number", x0=0.28, y0=0.795, x1=0.72, y1=0.860),
        ROIField(name="issue_date", x0=0.005, y0=0.180, x1=0.100, y1=0.800),
    ],
)

#: Paper PAN card letter layout (income-tax department): header band, the
#: large Permanent Account Number, then a Name / Father's Name / DOB grid.
#: Fractions measured from ``make_pan_card_image`` (900 x 600).
PAN_CARD_TEMPLATE = DocumentTemplate(
    document_type=DocumentType.PAN_CARD,
    rois=[
        ROIField(name="document_number", x0=0.30, y0=0.270, x1=0.88, y1=0.420),
        ROIField(name="surname", x0=0.47, y0=0.530, x1=0.92, y1=0.620),
        ROIField(name="date_of_birth", x0=0.47, y0=0.800, x1=0.92, y1=0.885),
    ],
)

#: New-style smart-card driving licence layout: photo box left, right-column
#: Name / DOB / Blood group / Address grid, licence number and validity on
#: the bottom row. Fractions measured from ``make_driving_license_image``
#: (1100 x 690).
DRIVING_LICENSE_TEMPLATE = DocumentTemplate(
    document_type=DocumentType.DRIVING_LICENSE,
    rois=[
        ROIField(name="surname", x0=0.42, y0=0.238, x1=0.97, y1=0.320),
        ROIField(name="date_of_birth", x0=0.42, y0=0.370, x1=0.97, y1=0.450),
        ROIField(name="document_number", x0=0.24, y0=0.890, x1=0.55, y1=0.960),
        ROIField(name="date_of_expiry", x0=0.81, y0=0.835, x1=0.995, y1=0.945),
    ],
)

DEFAULT_TEMPLATES: Sequence[DocumentTemplate] = (
    AADHAAR_LETTER_TEMPLATE,
    PAN_CARD_TEMPLATE,
    DRIVING_LICENSE_TEMPLATE,
)


# ---------------------------------------------------------------------------
# Per-ROI OCR
# ---------------------------------------------------------------------------
def crop_roi(bgr: np.ndarray, roi: ROIField) -> np.ndarray:
    """Crop one fractional ROI out of a BGR image."""
    height, width = bgr.shape[:2]
    x0, y0 = int(round(roi.x0 * width)), int(round(roi.y0 * height))
    x1, y1 = int(round(roi.x1 * width)), int(round(roi.y1 * height))
    x0, x1 = min(x0, x1), max(x0, x1)
    y0, y1 = min(y0, y1), max(y0, y1)
    if x1 - x0 < 1 or y1 - y0 < 1:
        raise ValueError(f"empty ROI crop for {roi.name}")
    return bgr[y0:y1, x0:x1]


def engine_ocr_crop(
    extractor: object, crop_bgr: np.ndarray
) -> Optional[OCRTextLine]:
    """OCR one crop through the same extractor the main pipeline uses.

    Returns the best-confidence line, or ``None`` when nothing was read.
    """
    scaled = cv2.resize(
        crop_bgr,
        None,
        fx=_UPSAMPLE,
        fy=_UPSAMPLE,
        interpolation=cv2.INTER_CUBIC,
    )
    result = extractor.extract(preprocess_image(scaled))
    if not result.recognized or not result.lines:
        return None
    return max(result.lines, key=lambda line: line.confidence)


def recognize_template_fields(
    bgr: np.ndarray,
    template: DocumentTemplate,
    ocr_crop: Callable[[np.ndarray], Optional[OCRTextLine]],
) -> list[ExtractedField]:
    """Run OCR inside every ROI of ``template`` on ``bgr``.

    ``ocr_crop`` is injected so tests and callers can fake or isolate the
    OCR step (the engine supplies ``engine_ocr_crop``). Values are field-wise
    normalized so an off target crop never leaks prose into a value.
    """
    out: list[ExtractedField] = []
    for roi in template.rois:
        line = ocr_crop(crop_roi(bgr, roi))
        if line is None or not line.text.strip():
            continue
        value = line.text.strip()
        cleaner = _CLEANERS.get(roi.name)
        if cleaner is not None:
            value = cleaner(value)
        if not value:
            continue
        out.append(
            ExtractedField(
                name=roi.name,
                value=value,
                source=FieldSource.TEMPLATE,
                confidence=line.confidence,
                bbox=(roi.x0, roi.y0, roi.x1, roi.y1),
            )
        )
    return out