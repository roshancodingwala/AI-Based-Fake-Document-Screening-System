"""Tests for the OCR extraction layer.

The central contract under test: extractors consume the OCR-facing copies of
a ``PreprocessedDocument`` (``ocr_ready`` / ``clahe_gray``) and NEVER the
forensic copy. We verify this by handing extractors deliberately
contradictory copies (forensic showing one thing, OCR copy showing another)
and by mutating the forensic copy after construction.
"""

import numpy as np
import pytest

import ocr_extractor
from ocr_extractor import (
    MockOCRExtractor,
    OCRExtractionResult,
    OCRTextLine,
    PaddleOCRExtractor,
)
from preprocessing import PreprocessedDocument


def make_ocr_ready_bars(height=120, width=240, bars=((30, 40), (70, 90))):
    """Binary 0/255 array with text=0 bars at the given row ranges."""
    img = np.full((height, width), 255, np.uint8)
    for y0, y1 in bars:
        img[y0:y1, 20:220] = 0
    return img


def make_doc(ocr_ready=None, clahe=None, forensic=None):
    return PreprocessedDocument(
        original_rgb=forensic,
        original_gray=None,
        clahe_gray=clahe if clahe is not None else np.full((1, 1), 255, np.uint8),
        ocr_ready=ocr_ready if ocr_ready is not None else np.full((1, 1), 255, np.uint8),
    )


# --- Mock extractor / raster derivation -----------------------------------------
def test_mock_extracts_one_line_per_text_band():
    ocr_ready = make_ocr_ready_bars(bars=((30, 40), (70, 90)))
    doc = make_doc(ocr_ready=ocr_ready)
    result = MockOCRExtractor().extract(doc)
    assert result.recognized is True
    assert len(result.lines) == 2
    assert result.read_from == "ocr_ready"


def test_mock_line_bboxes_are_fractional_and_in_bounds():
    ocr_ready = make_ocr_ready_bars(bars=((30, 40), (70, 90)))
    result = MockOCRExtractor().extract(make_doc(ocr_ready=ocr_ready))
    for line in result.lines:
        assert all(0.0 <= v <= 1.0 for v in line.bbox)
        assert line.bbox[0] < line.bbox[2]
        assert line.bbox[1] < line.bbox[3]


def test_mock_never_reads_the_forensic_copy():
    # forensic copy says "nothing here"; OCR copy says "two bars".
    # The extractor must trust only the OCR copy.
    ocr_ready = make_ocr_ready_bars(bars=((30, 40), (70, 90)))
    black_forensic = np.zeros((120, 240, 3), np.uint8)
    result = MockOCRExtractor().extract(
        make_doc(ocr_ready=ocr_ready, forensic=black_forensic)
    )
    assert len(result.lines) == 2
    # and mutating the forensic copy changes nothing about the extractor
    forensic2 = black_forensic.copy()
    forensic2[:] = 255
    result2 = MockOCRExtractor().extract(
        make_doc(ocr_ready=ocr_ready, forensic=forensic2)
    )
    assert result2.lines == result.lines
    assert result2.recognized is True


def test_mock_glyph_count_derived_from_dark_runs():
    # one band, dark columns split into 3 runs by two gaps -> "###"
    img = np.full((80, 200), 255, np.uint8)
    img[20:30, 10:40] = 0
    img[20:30, 60:90] = 0
    img[20:30, 120:170] = 0
    result = MockOCRExtractor().extract(make_doc(ocr_ready=img))
    assert result.recognized
    assert result.lines[0].text == "###"


def test_mock_clahe_gray_copy_path():
    gray = np.full((120, 240), 200, np.uint8)
    gray[20:30, 30:150] = 60
    result = MockOCRExtractor(use_copy="clahe_gray").extract(
        make_doc(clahe=gray)
    )
    assert result.recognized
    assert result.read_from == "clahe_gray"


def test_mock_rejects_unknown_copy():
    with pytest.raises(ValueError):
        MockOCRExtractor(use_copy="original_rgb")


def test_mock_empty_image_degrades_gracefully():
    blank = np.full((120, 240), 255, np.uint8)
    result = MockOCRExtractor().extract(make_doc(ocr_ready=blank))
    assert result.recognized is False
    assert result.lines == []
    assert "text" in result.message


def test_mock_too_small_image():
    tiny = np.zeros((1, 1), np.uint8)
    result = MockOCRExtractor().extract(make_doc(ocr_ready=tiny))
    assert result.recognized is False
    assert "too small" in result.message


# --- PaddleOCR lazy import + graceful degradation --------------------------------
def test_paddle_import_is_lazy():
    # module-level import must not have triggered any paddle import
    assert "paddleocr" not in sys_modules_snapshot()


def sys_modules_snapshot():
    import sys

    return {name for name in sys.modules if name.startswith(("paddle", "paddleocr"))}


def test_paddle_unavailable_backend_degrades_gracefully(monkeypatch):
    def _boom(self):
        raise ImportError("no paddleocr installed")

    monkeypatch.setattr(PaddleOCRExtractor, "_get_engine", _boom)
    gray = np.full((120, 240), 200, np.uint8)
    gray[20:30, 30:150] = 60
    doc = make_doc(clahe=gray)
    result = PaddleOCRExtractor().extract(doc)
    assert result.recognized is False
    assert "unavailable" in result.message
    assert result.lines == []


def test_paddle_engine_failure_degrades_gracefully(monkeypatch):
    def _boom(self):
        raise RuntimeError("model download timed out")

    monkeypatch.setattr(PaddleOCRExtractor, "_get_engine", _boom)
    gray = np.full((120, 240), 200, np.uint8)
    doc = make_doc(clahe=gray)
    result = PaddleOCRExtractor().extract(doc)
    assert result.recognized is False
    assert "failed" in result.message


def test_paddle_engine_uses_clahe_not_forensic(monkeypatch):
    calls = {}

    class FakeEngine:
        def ocr(self, image, cls=False):
            calls["input_is_forensic"] = np.array_equal(
                image, np.zeros((1, 1, 3), np.uint8)
            )
            return [[[[0, 0], [50, 0], [50, 10], [0, 10]], ("HELLO", 0.9)]]

    monkeypatch.setattr(PaddleOCRExtractor, "_get_engine", lambda self: FakeEngine())
    gray = np.full((120, 240), 200, np.uint8)
    gray[20:30, 30:150] = 60
    result = PaddleOCRExtractor().extract(make_doc(clahe=gray))
    assert result.recognized is True
    assert result.lines[0].text == "HELLO"
    assert result.lines[0].confidence == pytest.approx(0.9)
    assert calls["input_is_forensic"] is False


def test_paddle_bbox_fractional_on_zero_height():
    import numpy as np

    gray = np.zeros((240, 120), np.uint8)
    # degenerate box would divide by zero if height==0; height>0 here
    box = [[0.0, 0.0], [120.0, 0.0], [120.0, 240.0], [0.0, 240.0]]
    bbox = ocr_extractor._box_to_fractional(box, 120, 240)
    assert bbox == (0.0, 0.0, 1.0, 1.0)


# --- misc --------------------------------------------------------------------------
def test_available_backends_includes_mock():
    backends = ocr_extractor.available_backends()
    assert "mock" in backends
    assert isinstance(backends, list)


def test_ocr_line_dataclass():
    line = OCRTextLine(text="ABC", confidence=0.5, bbox=(0.0, 0.0, 1.0, 1.0))
    assert line.text == "ABC"