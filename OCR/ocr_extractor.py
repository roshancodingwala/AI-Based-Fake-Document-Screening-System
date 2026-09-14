"""OCR extraction layer (PaddleOCR with lazy import + Mock).

Contract with preprocessing: an extractor consumes a
``PreprocessedDocument`` and READS ONLY the OCR-facing copies
(``clahe_gray`` / ``ocr_ready``). It never touches ``original_rgb`` or
``original_gray``, which are reserved for the forensic / tamper-analysis
stage. The tests enforce this by constructing contradictory pairs of
forensic and OCR copies.

PaddleOCR is imported lazily inside ``extract()`` (never at module import),
so importing this module cannot hang on a model download and works on
machines without paddle installed. If the OCR backend is unavailable, an
``extract`` call degrades to ``recognized=False`` instead of raising, so
the validation engine can keep producing evidence-only output.

``MockOCRExtractor`` is a deterministic raster reader used by tests and
the demo: it segments ``ocr_ready`` into text-line bands from the
horizontal projection and emits one line per band. Its "text" is derived
from the actual pixels (one glyph symbol per dark run), so the
`reads-the-OCR-copy, never-the-forensic-copy` contract is exercised for
real.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from preprocessing import PreprocessedDocument

#: Showcase-only stand-in for the real PaddleOCR backend. Real OCR is the
#: production path; the mock keeps the pipeline testable end-to-end without
#: a ~100 MB model download.
DEFAULT_OCR_LANG: str = "en"
#: Fraction of image width of dark pixels needed to call a row 'text'.
_MOCK_MIN_ROW_DENSITY: float = 0.02
#: Minimum dark-pixel count for a text row regardless of image width.
_MOCK_MIN_PIXELS_PER_ROW: int = 5


@dataclass
class OCRTextLine:
    """One recognized text line with fractional bbox (0.0-1.0)."""

    text: str
    confidence: float
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1 (fractional)


@dataclass
class OCRExtractionResult:
    """Raw output of one OCR pass.

    `read_from` records which preprocessing copy was consumed ('clahe_gray'
    or 'ocr_ready'); `recognized=False` means no usable text was obtained
    (backend missing, timeout, or truly empty image) -- never an exception.
    """

    read_from: str = "clahe_gray"
    lines: list[OCRTextLine] = field(default_factory=list)
    recognized: bool = False
    elapsed_s: float = 0.0
    message: str = ""


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _box_to_fractional(box, width: int, height: int) -> tuple[float, float, float, float]:
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    return (
        _clamp01(min(xs) / width),
        _clamp01(min(ys) / height),
        _clamp01(max(xs) / width),
        _clamp01(max(ys) / height),
    )


class PaddleOCRExtractor:
    """PP-OCR engine wrapper with lazy import.

    ``extract`` reads ``clahe_gray`` (re-cast to 3-channel BGR, which is
    what PaddleOCR expects); the binary ``ocr_ready`` copy is fed only in
    debug/demo mode because thresholded input hurts PP-OCR accuracy.
    """

    def __init__(self, lang: str = DEFAULT_OCR_LANG) -> None:
        self.lang = lang
        self._engine = None  # lazy

    def _get_engine(self):
        if self._engine is None:
            from paddleocr import PaddleOCR

            try:
                self._engine = PaddleOCR(lang=self.lang, use_angle_cls=True)
            except TypeError:
                # older paddleocr releases dropped baggable kwargs
                self._engine = PaddleOCR(lang=self.lang)
        return self._engine

    def extract(self, preprocessed: PreprocessedDocument) -> OCRExtractionResult:
        start = time.perf_counter()
        gray = preprocessed.clahe_gray
        result = OCRExtractionResult(read_from="clahe_gray", lines=[])
        if gray.shape[0] < 2 or gray.shape[1] < 2:
            result.message = "image too small to OCR"
            return result
        try:
            engine = self._get_engine()
            bgr = cv2_gray_to_bgr(gray)
            height, width = gray.shape[:2]
            raw = engine.ocr(bgr, cls=True)
        except ImportError as exc:
            result.elapsed_s = time.perf_counter() - start
            result.message = f"OCR backend unavailable: {exc}"
            return result
        except Exception as exc:  # model download failure/timeout/etc.
            result.elapsed_s = time.perf_counter() - start
            result.message = f"OCR engine failed: {exc}"
            return result

        entries = _entries_from_paddle_result(raw)
        for box, (text, score) in entries:
            result.lines.append(
                OCRTextLine(
                    text=str(text),
                    confidence=_clamp01(float(score)),
                    bbox=_box_to_fractional(box, width, height),
                )
            )
        result.recognized = bool(result.lines)
        result.elapsed_s = time.perf_counter() - start
        if not result.recognized:
            result.message = "no text lines detected"
        return result


def _is_point_pair(value) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)
    )


def _is_box(value) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) >= 4
        and all(_is_point_pair(p) for p in value)
    )


def _looks_like_entry_list(seq) -> bool:
    """True when ``seq`` is a flat list of ``[box, [text, score]]`` entries."""
    if not isinstance(seq, list) or not seq:
        return False
    first = seq[0]
    if first is None or not isinstance(first, (list, tuple)) or len(first) != 2:
        return False
    box, label = first[0], first[1]
    is_label = (
        isinstance(label, (list, tuple))
        and len(label) == 2
        and isinstance(label[0], str)
        and isinstance(label[1], (int, float))
        and not isinstance(label[1], bool)
    )
    return _is_box(box) and is_label


def _entries_from_paddle_result(raw, max_depth: int = 5):
    """Normalize the varying return shapes of ``PaddleOCR.ocr`` across
    versions into a flat list of ``(box, (text, score))`` entries.

    Recognized shapes (single image input):
      * [[box, [text, score]], ...]          -- raw is the entry list
      * [[[box, [text, score]], ...]]        -- raw[0] is the entry list
      * [None]                               -- empty detection
    Anything else yields an empty list (graceful, never an exception).

    A bounded breadth-first walk returns the first node that satisfies the
    strict entry shape, so nesting depth differences never crash parsing.
    """
    queue = [raw]
    for _ in range(max_depth):
        if not queue:
            break
        node = queue.pop(0)
        if _looks_like_entry_list(node):
            return node
        if isinstance(node, list):
            queue.extend(child for child in node if isinstance(child, list))
    for node in queue:
        if _looks_like_entry_list(node):
            return node
    return []


def cv2_gray_to_bgr(gray: np.ndarray) -> np.ndarray:
    """Gray (2-D) -> 3-channel BGR so any OCR backend that wants color can
    consume the OCR copy. Raises on invalid input."""
    import cv2

    if gray.ndim != 2:
        raise ValueError("expected a 2-D grayscale array")
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


class MockOCRExtractor:
    """Deterministic raster reader for tests and demos.

    Segments ``ocr_ready`` by horizontal projection into line bands; every
    band yields one line whose 'text' is one '#"-glyph per contiguous dark
    run (so the output is genuinely derived from the OCR copy's pixels and
    mutating the forensic copy never changes it).
    """

    def __init__(
        self,
        use_copy: str = "ocr_ready",
        min_row_density: float = _MOCK_MIN_ROW_DENSITY,
        min_pixels_per_row: int = _MOCK_MIN_PIXELS_PER_ROW,
    ) -> None:
        if use_copy not in ("ocr_ready", "clahe_gray"):
            raise ValueError("use_copy must be 'ocr_ready' or 'clahe_gray'")
        self.use_copy = use_copy
        self.min_row_density = min_row_density
        self.min_pixels_per_row = min_pixels_per_row

    def _mask(self, preprocessed: PreprocessedDocument) -> np.ndarray:
        copy = preprocessed.ocr_ready if self.use_copy == "ocr_ready" else preprocessed.clahe_gray
        if self.use_copy == "clahe_gray":
            # generic dark-pixel mask on continuous gray
            return copy <= 128
        # ocr_ready is strictly 0/255, text is 0
        return copy == 0

    def _line_bands(self, mask: np.ndarray, width: int):
        row_counts = mask.sum(axis=1)
        threshold = max(int(width * self.min_row_density), self.min_pixels_per_row)
        active = row_counts > threshold
        bands = []
        y = 0
        while y < len(active):
            if not active[y]:
                y += 1
                continue
            y0 = y
            while y < len(active) and active[y]:
                y += 1
            bands.append((y0, y))
        return bands

    def extract(self, preprocessed: PreprocessedDocument) -> OCRExtractionResult:
        start = time.perf_counter()
        mask = self._mask(preprocessed)
        result = OCRExtractionResult(read_from=self.use_copy, lines=[])
        if mask.shape[0] < 2 or mask.shape[1] < 2:
            result.message = "image too small to OCR"
            return result
        height, width = mask.shape
        if not np.any(mask):
            result.message = "no text detected in OCR copy"
            result.elapsed_s = time.perf_counter() - start
            return result
        for idx, (y0, y1) in enumerate(self._line_bands(mask, width)):
            band_cols = np.where(mask[y0:y1, :].any(axis=0))[0]
            if band_cols.size == 0:
                continue
            x0, x1 = band_cols.min(), band_cols.max()
            runs = self._count_dark_runs(mask[y0:y1, :])
            n_chars = max(1, runs)
            result.lines.append(
                OCRTextLine(
                    text="#" * n_chars,
                    confidence=0.95,
                    bbox=(
                        _clamp01(x0 / width),
                        _clamp01(y0 / height),
                        _clamp01((x1 + 1) / width),
                        _clamp01((y1) / height),
                    ),
                )
            )
        result.recognized = bool(result.lines)
        result.elapsed_s = time.perf_counter() - start
        if not result.recognized:
            result.message = "no text lines detected"
        return result

    @staticmethod
    def _count_dark_runs(band_mask: np.ndarray) -> int:
        """Count contiguous dark columns within the band (glyph count)."""
        col_any = band_mask.any(axis=0)
        transitions = np.diff(col_any.astype(np.int8))
        return int((transitions == 1).sum()) or (0 if not col_any.any() else 1)


def available_backends() -> list[str]:
    """Names of OCR backends importable in this environment (for the demo)."""
    backends = []
    if _importable("paddleocr"):
        backends.append("paddleocr")
    backends.append("mock")
    return backends


def _importable(name: str) -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, AttributeError, ValueError):
        return False