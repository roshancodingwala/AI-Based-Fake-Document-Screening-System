import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.db.seed import seed_if_empty
from app.main import app

seed_if_empty()

client = TestClient(app)
HEADERS = {"X-API-Key": "demo-officer-key-12345"}


def make_test_image(color=(120, 140, 160), size=(400, 300)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def test_health():
    r = client.get("/health")
    assert r.status_code == 200


def test_requires_api_key():
    r = client.get("/api/documents/status/P123456")
    assert r.status_code == 401


def test_document_status_valid():
    r = client.get("/api/documents/status/P123456", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["status"] == "VALID"


def test_document_status_blacklisted():
    r = client.get("/api/documents/status/P-664521", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["status"] == "BLACKLISTED"


def test_document_status_unknown():
    r = client.get("/api/documents/status/DOES-NOT-EXIST", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["status"] == "UNKNOWN"


def test_ocr_extraction():
    r = client.post(
        "/api/documents/ocr",
        headers=HEADERS,
        files={"file": ("test.jpg", make_test_image(), "image/jpeg")},
        data={"document_type": "Passport"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["is_simulated"] is True
    assert 0 <= body["ocr_confidence"] <= 100


def test_ocr_rejects_bad_content_type():
    r = client.post(
        "/api/documents/ocr",
        headers=HEADERS,
        files={"file": ("test.txt", b"not an image", "text/plain")},
    )
    assert r.status_code == 415


def test_tampering_detection_returns_explainable_result():
    r = client.post(
        "/api/documents/tampering",
        headers=HEADERS,
        files={"file": ("test.jpg", make_test_image(), "image/jpeg")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("CLEAN", "SUSPICIOUS", "TAMPERED")
    assert isinstance(body["reasons"], list)
    assert len(body["reasons"]) > 0  # never a bare verdict with no explanation


def test_face_verify():
    r = client.post(
        "/api/face/verify",
        headers=HEADERS,
        files={
            "document_photo": ("doc.jpg", make_test_image(), "image/jpeg"),
            "live_photo": ("live.jpg", make_test_image(color=(10, 10, 10)), "image/jpeg"),
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert 0 <= body["similarity_score"] <= 1


def test_identity_search_finds_seeded_shadow_match():
    r = client.post("/api/identity/search", headers=HEADERS, json={"identity_id": "IDN-RS001"})
    assert r.status_code == 200
    body = r.json()
    assert body["possible_multiple_identity"] is True
    assert any(m["identity_id"] == "ID78231" for m in body["matches"])
    assert all(m["requires_officer_review"] or m["similarity"] < 0.9 for m in body["matches"])


def test_identity_search_requires_identity_id():
    r = client.post("/api/identity/search", headers=HEADERS, json={})
    assert r.status_code == 400


def test_document_dna():
    r = client.post("/api/documents/dna", headers=HEADERS, data={"document_number": "P123456"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["related_documents"]) > 0


def test_fraud_family():
    r = client.post("/api/fraud/family", headers=HEADERS, params={"document_number": "P123456"})
    assert r.status_code == 200
    assert r.json()["fraud_family_id"] == "PB-2291"


def test_fraud_network():
    r = client.get("/api/fraud/network/IDN-RS001", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert len(body["nodes"]) > 0
    assert len(body["edges"]) > 0


def test_cross_checkpoint_clusters_linked_identities():
    r = client.get("/api/intelligence/cross-checkpoint/IDN-RS001", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    # Should include Rohan Kumar's checkpoint history too, via the shared fraud family.
    assert body["total_checkpoints"] >= 2
    assert body["alert"] is True


def test_self_test_and_history():
    r = client.post("/api/ai/self-test", headers=HEADERS, json={"manipulation_type": "Photo Replacement"})
    assert r.status_code == 200

    r = client.get("/api/ai/self-test/history", headers=HEADERS)
    assert r.status_code == 200
    assert len(r.json()) > 0


def test_full_screening_pipeline():
    r = client.post(
        "/api/screen",
        headers=HEADERS,
        files={"document_image": ("doc.jpg", make_test_image(), "image/jpeg")},
        data={
            "document_type": "Passport",
            "checkpoint_name": "Terminal 3",
            "officer_id": "OFC-20481",
            "identity_id": "IDN-RS001",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["risk"]["risk_level"] in ("LOW", "MEDIUM", "HIGH")
    assert len(body["reasons"]) > 0

    # A matching blockchain audit row should now exist, hash-only.
    r2 = client.get("/api/blockchain/records", headers=HEADERS)
    assert any(rec["verification_id"] == body["verification_id"] for rec in r2.json())


def test_confirmed_fraud_case():
    r = client.post(
        "/api/fraud/confirmed",
        headers=HEADERS,
        json={
            "document_number": "P123456",
            "fraud_type": "Photo Substitution",
            "detected_features": ["compression anomaly"],
            "officer_id": "OFC-20481",
        },
    )
    assert r.status_code == 200
    assert r.json()["document_number"] == "P123456"


def test_upload_size_limit(monkeypatch):
    from app.core.config import get_settings

    get_settings.cache_clear()
    big_bytes = b"\xff\xd8\xff" + (b"0" * (11 * 1024 * 1024))  # ~11MB, over the 10MB default
    r = client.post(
        "/api/documents/tampering",
        headers=HEADERS,
        files={"file": ("big.jpg", big_bytes, "image/jpeg")},
    )
    assert r.status_code == 413
