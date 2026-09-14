"""Machine-readable channel extractor: QR / 2D barcodes.

Every document type is validated through its own evidence channels (see
``document_rules.DOCUMENT_STRATEGY``). Several of those channels are
machine-readable zones that are far more robust than whole-page OCR or a
regex:

  * Aadhaar (``aadhaar_qr``) -- the UIDAI letter/card QR holds a
    zlib-compressed XML payload attributed directly to UIDAI: ``uid``,
    ``name``, ``gender``, ``dob``/``yob`` and the address block. Because it
    is machine-typed (not OCR'd), a decoded payload is an authoritative
    cross-check against the visually OCR'd fields.
  * Driving licence (``dl_barcode``) -- the 2D barcode on smart cards
    encodes the licence number (and usually name/DOB). State payload
    layouts vary, so this decoder is deliberately best-effort: it pulls the
    licence-number-shaped token and fills what else it can.

Decoding is lazy and graceful: ``zxingcpp`` is tried first (fast, handles
dense/full-size QR and DataMatrix), ``cv2.QRCodeDetector`` is the fallback,
and a missing backend degrades to "no barcodes" -- never an exception. The
reader consumes the deskewed forensic copy (the untouched pixels), NOT the
thresholded OCR copies, because quiet-zone / contrast decisions belong to
the raw image.

The payload parsers below are pure functions (feed them a decoded string)
so the ICAO-adjacent / UIDAI semantics stay unit-testable with zero
hardware.
"""

from __future__ import annotations

import base64
import re
import time
import xml.etree.ElementTree as ET
from typing import Callable, List, Optional, Tuple
from zlib import decompress as _zlib_decompress
from zlib import error as _zlib_error

from preprocessing import PreprocessedDocument
from schemas import BarcodeResult

# ---------------------------------------------------------------------------
# Aadhaar QR payload
# ---------------------------------------------------------------------------
#: UIDAI "PrintLetterBarcodeData" attribute vocabulary.
_AADHAAR_XML_FIELDS: Tuple[str, ...] = (
    "uid", "name", "gender", "yob", "dob", "phone", "email",
    "co", "house", "street", "lm", "loc", "vtc", "subdist", "dist",
    "state", "pc",
)


def _first_nonempty_xml(root: ET.Element, key: str) -> Optional[str]:
    value = root.get(key)
    if value and value.strip():
        return value.strip()
    # Some verifiers nest fields as child elements instead of attributes.
    elem = root.find(key)
    if elem is not None and elem.text and elem.text.strip():
        return elem.text.strip()
    return None


def parse_aadhaar_payload(data: object) -> Optional[dict]:
    """Decode one UIDAI QR payload into a field dict.

    The QR stores the *compressed* XML (the payload is large, the QR stays
    scannable), so ``data`` normally arrives as raw bytes (``zxingcpp``'s
    ``result.bytes``). Robust handling: try zlib on the raw bytes, on a
    base64 decode, and finally treat the input as the XML itself. Returns
    None when nothing decodes to a UIDAI-style element.
    """
    if not data:
        return None
    candidates: List[bytes] = []
    if isinstance(data, str):
        try:
            candidates.append(data.encode("latin1"))
        except (UnicodeEncodeError, AttributeError):
            return None
        try:
            candidates.append(data.encode("utf-8"))
        except Exception:
            pass
    elif isinstance(data, (bytes, bytearray)):
        candidates.append(bytes(data))
    else:
        try:
            candidates.append(bytes(data))
        except Exception:
            return None

    try:
        candidates.append(base64.b64decode(candidates[0]))
    except (ValueError, TypeError):
        pass

    text: Optional[str] = None
    for blob in candidates:
        if not blob:
            continue
        try:
            text = _zlib_decompress(blob).decode("utf-8", "replace")
        except _zlib_error:
            continue
        break
    if text is None:
        # not compressed -- fall through and try the decoded bytes as XML
        text = candidates[0].decode("utf-8", "replace") if candidates else ""

    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None

    data = {k: v for k, v in ((k, _first_nonempty_xml(root, k)) for k in _AADHAAR_XML_FIELDS) if v}
    if not data.get("uid") and not (data.get("name") or data.get("dob")):
        return None
    signature = root.get("signature")
    data["_signature_present"] = bool(signature and signature.strip())
    return data


# ---------------------------------------------------------------------------
# Driving-licence 2D barcode (state-specific; best-effort)
# ---------------------------------------------------------------------------
#: Smart-card licence-number shape: STATE(2) + RTO(2) + YEAR(4) + SERIAL(7+).
_DL_NUMBER_RE = re.compile(r"[A-Z]{2}\s*\d{2}\s*\d{4}\s*\d{7,11}")
_DL_DOB_RE = re.compile(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{4}")


def parse_dl_barcode(raw: str) -> dict:
    """Best-effort DL barcode -> field dict.

    Smart-card layouts are state-specific; many encode a JSON blob
    (``licenceNo``/``name``/``dob``), others a delimited string. JSON is
    tried first, then regex fallbacks. ``document_number`` is the field
    that matters -- the number-shaped token is what cross-source rules use.
    """
    text = "".join(ch for ch in raw if ch.isprintable() or ch.isspace())
    text = re.sub(r"\s+", " ", text).upper()
    data: dict = {}

    try:
        import json

        obj = json.loads(text)
        if isinstance(obj, dict):
            for key, value in obj.items():
                k = str(key).lower().replace("_", "").replace(" ", "").replace("-", "")
                v = str(value).strip().upper()
                if not v:
                    continue
                if k in ("licenceno", "licenseno", "dlno") or "licence" in k or "license" in k:
                    data["document_number"] = _DL_NUMBER_RE.search(v).group(0).replace(" ", "") \
                        if _DL_NUMBER_RE.search(v) else v
                elif k in ("name", "holdername"):
                    data["surname"] = v
                elif k in ("dob", "dateofbirth", "birthdate"):
                    m = _DL_DOB_RE.search(v)
                    if m:
                        data["date_of_birth"] = m.group(0)
                elif k in ("validtill", "expirydate", "validuntil"):
                    m = _DL_DOB_RE.search(v)
                    if m:
                        data["date_of_expiry"] = m.group(0)
    except (ValueError, TypeError):
        pass

    # regex fallbacks fill whatever the JSON pass missed
    m = _DL_NUMBER_RE.search(text)
    if m and "document_number" not in data:
        data["document_number"] = re.sub(r"\s+", "", m.group(0))
    m = _DL_DOB_RE.search(text)
    if m and "date_of_birth" not in data:
        data["date_of_birth"] = m.group(0)

    data["_raw"] = raw
    return data


# ---------------------------------------------------------------------------
# Decoding backends
# ---------------------------------------------------------------------------
def _format_name(entry) -> str:
    for attr in ("symbology", "format"):
        value = getattr(entry, attr, None)
        if value is None:
            continue
        name = getattr(value, "name", None)
        if name:
            return str(name).replace(" ", "").upper() or str(value)
        return str(value)
    return "UNKNOWN"


def _entry_bytes(entry) -> Optional[bytes]:
    try:
        return bytes(getattr(entry, "bytes")) or None
    except Exception:
        return None


def _decode_with_zxingcpp(image) -> List[Tuple[str, str, bytes]]:
    """Return [(format_name, text, raw_bytes), ...] via zxingcpp (preferred)."""
    import zxingcpp  # lazy: absence degrades gracefully

    entries = zxingcpp.read_barcodes(image)
    out: List[Tuple[str, str, bytes]] = []
    for entry in entries:
        if not getattr(entry, "valid", False):
            continue
        raw = _entry_bytes(entry) or b""
        try:
            text = raw.decode("utf-8", "replace")
        except Exception:
            text = ""
        out.append((_format_name(entry), text, raw))
    return out


def _decode_with_cv2(image) -> List[Tuple[str, str, bytes]]:
    """Fallback: cv2 QRCodeDetector (QR only)."""
    import cv2  # lazy

    converter = cv2.cvtColor if image.ndim == 3 else lambda im, _c: im
    gray = converter(image, cv2.COLOR_BGR2GRAY)
    # ``detectAndDecodeMulti`` returns (ok, decoded[], points[], straight[]).
    ok, decoded, _pts, _straight = cv2.QRCodeDetector().detectAndDecodeMulti(gray)
    if not ok:
        return []
    out: List[Tuple[str, str, bytes]] = []
    for text in decoded:
        if text:
            out.append(("QRCODE", text, text.encode("latin1", "replace")))
    return out


def _resize(image, factor: float):
    """Resize an image; a no-op at factor 1.0."""
    if abs(factor - 1.0) < 1e-6:
        return image
    import cv2  # lazy

    h, w = image.shape[:2]
    return cv2.resize(
        image,
        (max(1, int(w * factor)), max(1, int(h * factor))),
        interpolation=cv2.INTER_CUBIC,
    )


def _iter_scaled(image):
    """Normalized decode copies: from ~1500px up to ~3000px longest side.

    A phone photo of a card back often carries a QR that spans a small
    fraction of the frame; global decoders miss it at native resolution.
    Upscaling toward a target module size (a few pixels per module) is the
    standard fix, while very large frames are downscaled so memory stays
    bounded. The raw copy is always tried first.
    """
    h, w = image.shape[:2]
    longest = max(h, w) or 1
    factors: list[float] = [1.0]
    for target in (1500, 2500, 3000):
        factor = min(3.0, max(0.5, target / longest))
        if all(abs(factor - prev) > 0.05 for prev in factors):
            factors.append(factor)
    return [_resize(image, factor) for factor in factors]


class BarcodeExtractor:
    """Decode every machine-readable zone on a preprocessed document.

    ``decode_fn`` is injectable for tests; by default it tries zxingcpp then
    OpenCV. The output is a list of ``BarcodeResult`` per read: the channel
    is classified (``aadhaar_qr`` / ``dl_barcode`` / ``unclassified``) and
    every parsed payload is attached. Resolution failures of an *expected*
    channel are surfaced by the rules layer (``secure_anchor_missing``), not
    here.
    """

    def __init__(self, decode_fn: Optional[Callable] = None) -> None:
        self._decode_fn = decode_fn
        self._warned_missing = False

    def _read(self, image) -> List[Tuple[str, str, bytes]]:
        if self._decode_fn is not None:
            try:
                return self._decode_fn(image)
            except Exception:
                return []  # an injected/pluggable decoder must never crash us
        if image is None or image.size == 0:
            return []
        decoded: List[Tuple[str, str, bytes]] = []
        seen: set = set()
        for scaled in _iter_scaled(image):
            for candidate in self._try_decoders(scaled):
                key = (candidate[0], candidate[1])
                if key not in seen:
                    seen.add(key)
                    decoded.append(candidate)
        return decoded

    def _try_decoders(self, scaled) -> List[Tuple[str, str, bytes]]:
        """zxingcpp first (fast, dense-only-tolerant), cv2 as a second reader
        at the same scale -- a QR one reader misses is often caught by the
        other."""
        if scaled is None or scaled.size == 0:
            return []
        try:
            found = _decode_with_zxingcpp(scaled)
            if found:
                return found
        except ImportError:
            pass
        except Exception:
            pass  # a decoder bug must not crash the pipeline
        try:
            return _decode_with_cv2(scaled)
        except ImportError:
            return []
        except Exception:
            return []

    @staticmethod
    def _channel_for(decode: Tuple[str, str, bytes], payload: Optional[dict]) -> str:
        fmt, text, raw = decode
        if fmt in ("QRCODE",) and payload is not None:
            return "aadhaar_qr"
        if fmt in ("QRCODE", "DATAMATRIX", "PDF417") and text:
            try:
                dl = parse_dl_barcode(text)
            except Exception:
                dl = {}
            if dl.get("document_number"):
                return "dl_barcode"
        return "unclassified"

    def extract(self, preprocessed: PreprocessedDocument) -> List[BarcodeResult]:
        """Scan a preprocessed document and return classified reads."""
        start = time.perf_counter()
        # Machine-read only the deskewed forensic copy (real pixels). The
        # thresholded OCR copies introduce halftones that hurt QR readings.
        image = preprocessed.original_rgb
        if image is None:
            image = preprocessed.original_gray
        if image is None:
            image = preprocessed.clahe_gray
        if image is None or image.size == 0:
            return []

        results: List[BarcodeResult] = []
        for decode in self._read(image):
            fmt, text, raw = decode
            payload: Optional[dict] = None
            if fmt in ("QRCODE",):
                payload = parse_aadhaar_payload(raw if raw else text)
            channel = self._channel_for(decode, payload)
            if channel == "aadhaar_qr" and payload is not None:
                results.append(
                    BarcodeResult(
                        channel="aadhaar_qr",
                        format=fmt,
                        raw=text,
                        data={k: v for k, v in payload.items() if not k.startswith("_")},
                        signature_present=bool(payload.get("_signature_present")),
                    )
                )
            elif channel == "dl_barcode":
                dl = parse_dl_barcode(text)
                data = {k: v for k, v in dl.items() if not k.startswith("_")}
                results.append(
                    BarcodeResult(
                        channel="dl_barcode",
                        format=fmt,
                        raw=text,
                        data=data,
                        signature_present=False,
                    )
                )
            elif channel == "unclassified":
                results.append(
                    BarcodeResult(
                        channel="unclassified",
                        format=fmt,
                        raw=text,
                        data={},
                        signature_present=False,
                    )
                )
        return results


# ---------------------------------------------------------------------------
# Payload -> fields mapping (used by the engine's field assembly)
# ---------------------------------------------------------------------------
#: Aadhaar QR payload keys -> module field names.
_AADHAAR_QR_FIELD_MAP: dict = {
    "uid": "document_number",
    "name": "surname",       # full name -- fills the primary-identifier slot
    "gender": "sex",
    "dob": "date_of_birth",
}


def _normalise_date(value: str) -> str:
    """Leave DD/MM/YYYY (UIDAI prints day-first) untouched."""
    return value


def fields_from_barcode_result(result: BarcodeResult) -> dict:
    """Map a classified ``BarcodeResult`` to ``ExtractedField``s."""
    out = {}
    if result.channel == "aadhaar_qr":
        for payload_key, field_name in _AADHAAR_QR_FIELD_MAP.items():
            value = result.data.get(payload_key)
            if value:
                out[field_name] = value
    elif result.channel == "dl_barcode":
        for field_name in ("document_number", "surname", "date_of_birth", "date_of_expiry"):
            value = result.data.get(field_name)
            if value:
                out[field_name] = value
    return out