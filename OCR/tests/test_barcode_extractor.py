"""Tests for the machine-readable (QR / 2D barcode) channel.

Covers the UIDAI payload decoders (pure functions -> no hardware), the DL
barcode best-effort parser, payload -> module-field mapping, classification
via an injected decode function, graceful degradation when a decoder crashes,
and one true raster round-trip solved through the default decoder stack.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from barcode_extractor import (
    BarcodeExtractor,
    fields_from_barcode_result,
    parse_aadhaar_payload,
    parse_dl_barcode,
)
from preprocessing import PreprocessedDocument
from schemas import BarcodeResult


def _aadhaar_xml(
    uid="234567890124",
    name="SINGH ARJUN KUMAR",
    dob="15/08/1995",
    yob="1995",
    signed=True,
):
    signature = ' signature="abc123def456"' if signed else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<PrintLetterBarcodeData'
        f' uid="{uid}" name="{name}" gender="M" yob="{yob}" dob="{dob}"'
        ' co="NAME OF FATHER" house="42" street="MAIN ROAD" lm="" loc="KHANPUR"'
        ' vtc="KHANPUR RODAN" subdist="ROHTAK" dist="ROHTAK" state="HARYANA"'
        f' pc="124001"{signature}/>'
    )


# --- Aadhaar payload parsing -------------------------------------------------
def test_aadhaar_payload_parses_compressed_bytes():
    import zlib

    xml = _aadhaar_xml().encode("utf-8")
    data = parse_aadhaar_payload(zlib.compress(xml))
    assert data is not None
    assert data["uid"] == "234567890124"
    assert data["name"] == "SINGH ARJUN KUMAR"
    assert data["dob"] == "15/08/1995"
    assert data["_signature_present"] is True


def test_aadhaar_payload_parses_plain_xml_string():
    data = parse_aadhaar_payload(_aadhaar_xml())
    assert data is not None
    assert data["uid"] == "234567890124"
    assert data["state"] == "HARYANA"


def test_aadhaar_payload_parses_base64_compressed():
    import base64
    import zlib

    blob = base64.b64encode(zlib.compress(_aadhaar_xml().encode("utf-8")))
    data = parse_aadhaar_payload(blob)
    assert data is not None
    assert data["uid"] == "234567890124"
    assert data["_signature_present"] is True


def test_aadhaar_payload_unsigned_xml_sets_signature_false():
    data = parse_aadhaar_payload(_aadhaar_xml(signed=False))
    assert data is not None
    assert data["_signature_present"] is False


def test_aadhaar_payload_rejects_garbage():
    assert parse_aadhaar_payload(b"not-a-qr-payload") is None
    assert parse_aadhaar_payload("") is None
    assert parse_aadhaar_payload(None) is None


# --- DL barcode parsing ------------------------------------------------------
def test_dl_barcode_parses_json_payload():
    raw = '{"licenceNo":"MH0120300567890","name":"SINGH ARJUN KUMAR","dob":"15/08/1995"}'
    data = parse_dl_barcode(raw)
    assert data["document_number"] == "MH0120300567890"
    assert data["surname"] == "SINGH ARJUN KUMAR"
    assert data["date_of_birth"] == "15/08/1995"


def test_dl_barcode_parses_delimited_fallback():
    # State layouts without JSON: pull the licence-number-shaped token.
    raw = "MH0120300567890|15/08/1995|SINGH ARJUN KUMAR"
    data = parse_dl_barcode(raw)
    assert data["document_number"] == "MH0120300567890"
    assert data["date_of_birth"] == "15/08/1995"


def test_dl_barcode_garbage_is_graceful():
    data = parse_dl_barcode("just some text, no structure")
    assert "document_number" not in data
    assert data["_raw"] == "just some text, no structure"


# --- payload -> field mapping -------------------------------------------------
def test_fields_from_barcode_aadhaar_qr():
    result = BarcodeResult(
        channel="aadhaar_qr",
        format="QRCODE",
        raw="x",
        data={
            "uid": "234567890124",
            "name": "SINGH ARJUN KUMAR",
            "gender": "M",
            "dob": "15/08/1995",
        },
    )
    fields = fields_from_barcode_result(result)
    assert fields == {
        "document_number": "234567890124",
        "surname": "SINGH ARJUN KUMAR",
        "sex": "M",
        "date_of_birth": "15/08/1995",
    }


def test_fields_from_barcode_dl():
    result = BarcodeResult(
        channel="dl_barcode",
        format="QRCODE",
        raw="x",
        data={
            "document_number": "MH0120300567890",
            "surname": "SINGH ARJUN KUMAR",
            "date_of_birth": "15/08/1995",
        },
    )
    assert fields_from_barcode_result(result)["document_number"] == "MH0120300567890"


def test_fields_from_unclassified_is_empty():
    result = BarcodeResult(channel="unclassified", format="QRCODE", raw="x")
    assert fields_from_barcode_result(result) == {}


# --- classify + graceful degradation (injected decoder) -----------------------
def _pp(qr_bgr):
    return PreprocessedDocument(original_rgb=qr_bgr)


def test_extractor_classifies_aadhaar_channel():
    import zlib

    text = "printed-zone text, ignored by the machine-read path"
    raw = zlib.compress(_aadhaar_xml().encode("utf-8"))
    be = BarcodeExtractor(decode_fn=lambda image: [("QRCODE", text, raw)])
    results = be.extract(_pp(np.zeros((8, 8, 3), np.uint8)))
    assert len(results) == 1
    assert results[0].channel == "aadhaar_qr"
    assert results[0].data["uid"] == "234567890124"
    assert results[0].signature_present is True


def test_extractor_classifies_dl_channel():
    text = '{"licenceNo":"MH0120300567890","dob":"15/08/1995"}'
    be = BarcodeExtractor(decode_fn=lambda image: [("QRCODE", text, text.encode("latin1"))])
    results = be.extract(_pp(np.zeros((8, 8, 3), np.uint8)))
    assert len(results) == 1
    assert results[0].channel == "dl_barcode"
    assert results[0].data["document_number"] == "MH0120300567890"


def test_extractor_unclassified_for_plain_payload():
    be = BarcodeExtractor(decode_fn=lambda image: [("QRCODE", "hello world", b"hello world")])
    results = be.extract(_pp(np.zeros((8, 8, 3), np.uint8)))
    assert len(results) == 1
    assert results[0].channel == "unclassified"


def test_extractor_degrades_on_decoder_crash():
    def boom(image):
        raise RuntimeError("decoder segfaulted")

    be = BarcodeExtractor(decode_fn=lambda image: (_ for _ in ()).throw(
        RuntimeError("decoder segfaulted")))
    results = be.extract(_pp(np.zeros((8, 8, 3), np.uint8)))
    assert results == []

    be2 = BarcodeExtractor(decode_fn=boom)
    results2 = be2.extract(_pp(np.zeros((8, 8, 3), np.uint8)))
    assert results2 == []


@pytest.mark.skipif(sys.version_info < (3, 9), reason="requires 3.9+")
def test_aadhaar_qr_raster_roundtrip():
    """Solve a real QR raster through the default decoder stack."""
    qrcode = pytest.importorskip("qrcode")
    zlib = pytest.importorskip("zlib")

    xml = _aadhaar_xml()
    payload_bytes = zlib.compress(xml.encode("utf-8"))
    qr = qrcode.make(payload_bytes)
    rgb = np.array(qr.convert("RGB"))
    bgr = rgb[:, :, ::-1].copy()

    results = BarcodeExtractor().extract(_pp(bgr))
    assert len(results) == 1
    result = results[0]
    assert result.channel == "aadhaar_qr"
    assert result.format == "QRCODE"
    assert result.data["uid"] == "234567890124"
    assert result.data["name"] == "SINGH ARJUN KUMAR"
    assert result.data["dob"] == "15/08/1995"
    assert result.signature_present is True