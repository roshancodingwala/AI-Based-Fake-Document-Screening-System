"""Tests for structure-aware template ROI OCR.

Covers the schema contract, the crop/recognize helpers (using stubbed OCR so
no model is needed), field-value normalization, the merge policy in the
validation engine, and one engine-level plumbing test with a scripted fake
extractor (deterministic per-call output).
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ocr_extractor import OCRTextLine
from schemas import (
    DocumentType,
    ExtractedField,
    FieldSource,
    ROIField,
)
from template_recognizer import (
    AADHAAR_LETTER_TEMPLATE,
    PAN_CARD_TEMPLATE,
    DRIVING_LICENSE_TEMPLATE,
    _CLEANERS,
    crop_roi,
    recognize_template_fields,
)
from validation_engine import (
    EngineOptions,
    ValidationEngine,
    merge_template_fields,
)


def test_aadhaar_template_covers_expected_fields():
    names = {roi.name for roi in AADHAAR_LETTER_TEMPLATE.rois}
    assert names == {
        "surname",
        "date_of_birth",
        "sex",
        "document_number",
        "issue_date",
    }
    assert AADHAAR_LETTER_TEMPLATE.document_type == DocumentType.AADHAAR


def test_aadhaar_template_rois_are_valid_fractions():
    for roi in AADHAAR_LETTER_TEMPLATE.rois:
        assert 0.0 <= roi.x0 < roi.x1 <= 1.0
        assert 0.0 <= roi.y0 < roi.y1 <= 1.0


def test_crop_roi_geometry():
    canvas = np.zeros((200, 400, 3), dtype=np.uint8)
    canvas[:, :] = (30, 60, 90)
    roi = ROIField(name="test", x0=0.25, y0=0.25, x1=0.75, y1=0.6)
    crop = crop_roi(canvas, roi)
    assert crop.shape == (int(200 * 0.35), int(400 * 0.5), 3)
    assert np.all(crop == (30, 60, 90))


def test_recognize_template_fields_maps_roi_to_field_with_stub_ocr():
    canvas = np.zeros((300, 600, 3), dtype=np.uint8)
    colors = {
        "surname": (10, 10, 10),
        "date_of_birth": (50, 50, 50),
        "sex": (90, 90, 90),
        "document_number": (130, 130, 130),
        "issue_date": (170, 170, 170),
    }
    # paint each ROI with its unique color
    flat = {}
    for roi in AADHAAR_LETTER_TEMPLATE.rois:
        canvas[int(roi.y0 * 300):int(roi.y1 * 300),
               int(roi.x0 * 600):int(roi.x1 * 600)] = colors[roi.name]
        flat[roi.name] = (roi.x0, roi.y0, roi.x1, roi.y1)

    def stub(crop_bgr):
        center = crop_bgr[int(crop_bgr.shape[0] / 2), int(crop_bgr.shape[1] / 2)]
        for name, (r, g, b) in colors.items():
            if tuple(center) == (r, g, b):
                # document_number's cleaner strips to digits-only, so this one
                # must actually BE digits or the field is legitimately dropped.
                text = "224541818796" if name == "document_number" else f"value_{name}"
                return OCRTextLine(text=text, confidence=0.9, bbox=(0, 0, 1, 1))
        return None

    fields = recognize_template_fields(canvas, AADHAAR_LETTER_TEMPLATE, stub)
    by_name = {f.name: f for f in fields}
    assert set(by_name) == set(colors)
    for name, field in by_name.items():
        expected = "224541818796" if name == "document_number" else f"value_{name}"
        assert field.value == expected
        assert field.source == FieldSource.TEMPLATE
        assert field.bbox == flat[name]


def test_recognize_template_fields_normalizes_values():
    canvas = np.zeros((100, 100, 3), dtype=np.uint8)
    template = AADHAAR_LETTER_TEMPLATE
    # drive the cleaner through fixed text per ROI using the color trick
    colors = {roi.name: (i * 30 + 5,) * 3 for i, roi in enumerate(template.rois)}
    dirty = {
        "surname": "Keshav Kumar",
        "date_of_birth": "Date of Birth/D0B: 17/12/2006",
        "sex": "Male/MALE",
        "document_number": "224 541 818 796",
        "issue_date": "issued: 24/02/2015",
    }
    for roi in template.rois:
        canvas[int(roi.y0 * 100):int(roi.y1 * 100),
               int(roi.x0 * 100):int(roi.x1 * 100)] = colors[roi.name]

    def stub(crop_bgr):
        center = crop_bgr[int(crop_bgr.shape[0] / 2), int(crop_bgr.shape[1] / 2)]
        for roi in template.rois:
            if tuple(center) == colors[roi.name]:
                return OCRTextLine(text=dirty[roi.name], confidence=0.9,
                                   bbox=(0, 0, 1, 1))
        return None

    by_name = {f.name: f for f in recognize_template_fields(canvas, template, stub)}
    assert by_name["document_number"].value == "224541818796"
    assert by_name["date_of_birth"].value == "17/12/2006"
    assert by_name["issue_date"].value == "24/02/2015"
    assert by_name["sex"].value == "MALE"
    assert by_name["surname"].value == "Keshav Kumar"


def test_document_number_cleaner_keeps_alnum_for_pan_and_dl():
    cleaner = _CLEANERS["document_number"]
    # PAN (ABCDE1234F) and DL (MH0120300567890) numbers are alphanumeric:
    # only spaces/punctuation/upcasing are normalized away.
    assert cleaner(" abcde 1234f ") == "ABCDE1234F"
    assert cleaner("MH 01 2030 0567890") == "MH0120300567890"
    assert cleaner("224 541 818 796") == "224541818796"


def _field(name, value, confidence, source=FieldSource.VISUAL):
    return ExtractedField(name=name, value=value, source=source,
                          confidence=confidence, bbox=None)


def test_merge_template_fields_fills_missing():
    visual = {"surname": _field("surname", "Keshav Kumar", 0.94)}
    template = {
        "surname": _field("surname", "Keshav Kumar", 0.96, FieldSource.TEMPLATE),
        "document_number": _field("document_number", "224541818796", 0.99,
                                  FieldSource.TEMPLATE),
    }
    merged = merge_template_fields(visual, template)
    # surname existed -> fill-only, the higher-confidence template read is NOT
    # allowed to clobber it; document_number was missing -> filled.
    assert merged["surname"].source == FieldSource.VISUAL
    assert merged["document_number"].source == FieldSource.TEMPLATE


def test_merge_template_fields_overrides_allowed_fields_only():
    low_visual_number = _field("document_number", "2222", 0.8)
    high_template_number = _field("document_number", "224541818796", 0.99,
                                  FieldSource.TEMPLATE)
    merged = merge_template_fields(
        {"document_number": low_visual_number},
        {"document_number": high_template_number},
    )
    number = merged["document_number"]
    assert number.value == "224541818796"
    assert number.source == FieldSource.TEMPLATE


def test_merge_template_fields_never_overrides_with_lower_confidence():
    visual = {"document_number": _field("document_number", "224541818796", 0.99)}
    template = {"document_number": _field("document_number", "000000000000", 0.9,
                                          FieldSource.TEMPLATE)}
    merged = merge_template_fields(visual, template)
    assert merged["document_number"].value == "224541818796"
    assert merged["document_number"].source == FieldSource.VISUAL


PINNED_SEQUENCE = [
    "Government of India Aadhaar card",
    "Keshav Kumar",
    "Date of Birth/D0B: 17/12/2006",
    "Male/MALE",
    "224 541 818 796",
    "Aadhaar no. issued 24/02/2015",
]


class ScriptedExtractor:
    """Mimics the engine's OCR call order: full page first, then each ROI in
    template order, returning the next pinned string per call."""

    def __init__(self):
        self.calls = 0

    @property
    def recognized(self):
        return True

    def extract(self, preprocessed):
        text = PINNED_SEQUENCE[self.calls % len(PINNED_SEQUENCE)]
        self.calls += 1
        return OCRExtractionResultStub([OCRTextLine(text=text, confidence=0.95,
                                                    bbox=(0.0, 0.0, 1.0, 1.0))])


class OCRExtractionResultStub:
    def __init__(self, lines):
        self.lines = lines
        self.recognized = bool(lines)
        self.read_from = "clahe_gray"
        self.message = ""


def test_engine_applies_matching_template():
    engine = ValidationEngine(
        EngineOptions(ocr_extractor=ScriptedExtractor(),
                      templates=(AADHAAR_LETTER_TEMPLATE,))
    )
    import cv2
    image = np.zeros((200, 300, 3), dtype=np.uint8)
    result = engine.validate_image(image)
    by_name = {f.name: f for f in result.fields}
    assert result.document_type == DocumentType.AADHAAR
    assert by_name["document_number"].value == "224541818796"
    assert by_name["document_number"].source == FieldSource.TEMPLATE
    assert by_name["surname"].source == FieldSource.TEMPLATE
    assert by_name["issue_date"].value == "24/02/2015"
    codes = {flag.code for flag in result.flags}
    assert "template_roi_applied" in codes
    assert result.validation_score > 0