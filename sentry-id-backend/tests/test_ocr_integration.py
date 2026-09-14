import pytest
from fastapi.testclient import TestClient
from pathlib import Path

from app.main import app

client = TestClient(app)
HEADERS = {'X-API-Key': 'demo-officer-key-12345'}

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
OCR_TEST_IMAGES = WORKSPACE_ROOT / 'OCR' / 'test images'


def test_real_aadhaar_qr_ocr_extraction():
    img_path = OCR_TEST_IMAGES / 'sample_aadhaar_qr.png'
    if not img_path.exists():
        pytest.skip('sample_aadhaar_qr.png not found')

    with open(img_path, 'rb') as f:
        img_bytes = f.read()

    r = client.post(
        '/api/documents/ocr',
        headers=HEADERS,
        files={'file': ('aadhaar.png', img_bytes, 'image/png')},
        data={'document_type': 'Aadhaar'},
    )
    assert r.status_code == 200
    body = r.json()
    assert body['is_simulated'] is False
    assert body['fields']['document_number'] == '234567890124'
    assert 'SINGH' in body['fields']['name']
    assert body['ocr_confidence'] >= 90
    assert len(body['barcodes']) >= 1
    assert body['barcodes'][0]['channel'] == 'aadhaar_qr'


def test_real_dl_barcode_ocr_extraction():
    img_path = OCR_TEST_IMAGES / 'sample_dl.png'
    if not img_path.exists():
        pytest.skip('sample_dl.png not found')

    with open(img_path, 'rb') as f:
        img_bytes = f.read()

    r = client.post(
        '/api/documents/ocr',
        headers=HEADERS,
        files={'file': ('dl.png', img_bytes, 'image/png')},
        data={'document_type': 'Driving Licence'},
    )
    assert r.status_code == 200
    body = r.json()
    assert body['is_simulated'] is False
    assert body['fields']['document_number'] == 'MH0120300567890'
    assert len(body['barcodes']) >= 1


def test_aadhaar_verhoeff_validation():
    # Valid Aadhaar passing Verhoeff
    r_valid = client.post(
        '/api/documents/validate',
        headers=HEADERS,
        json={
            'fields': {
                'name': 'Arjun Kumar',
                'document_number': '234567890124',
            },
            'document_type': 'Aadhaar',
        },
    )
    assert r_valid.status_code == 200
    assert r_valid.json()['is_valid'] is True

    # Altered Aadhaar failing Verhoeff
    r_invalid = client.post(
        '/api/documents/validate',
        headers=HEADERS,
        json={
            'fields': {
                'name': 'Arjun Kumar',
                'document_number': '234567890129',  # altered last digit
            },
            'document_type': 'Aadhaar',
        },
    )
    assert r_invalid.status_code == 200
    res = r_invalid.json()
    assert res['is_valid'] is False
    assert any('Verhoeff checksum failed' in err for err in res['errors'])


def test_full_screening_with_real_aadhaar_qr():
    img_path = OCR_TEST_IMAGES / 'sample_aadhaar_qr.png'
    if not img_path.exists():
        pytest.skip('sample_aadhaar_qr.png not found')

    with open(img_path, 'rb') as f:
        img_bytes = f.read()

    r = client.post(
        '/api/screen',
        headers=HEADERS,
        files={'document_image': ('aadhaar.png', img_bytes, 'image/png')},
        data={
            'document_type': 'Aadhaar',
            'checkpoint_name': 'IGI Airport T3',
            'officer_id': 'OFC-7712',
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body['document_number'] == '234567890124'
    assert body['ocr']['is_simulated'] is False
    assert 'SINGH' in body['ocr']['fields']['name']
    assert body['validation']['is_valid'] is True
    assert 0 <= body['risk']['risk_score'] <= 100
