"""
OCR extraction.

`OCRService` is an abstract interface so the demo implementation
(`DemoOCRService`, which returns realistic synthetic fields) can later be
swapped for `PaddleOCRService` without touching the router or schemas.

To wire in real PaddleOCR:
    1. `pip install paddleocr paddlepaddle`
    2. Implement a `PaddleOCRService(OCRService)` that runs
       `PaddleOCR(use_angle_cls=True, lang="en")` on the image bytes and
       maps detected text regions to the OCRFields schema (e.g. via MRZ
       parsing for passports, regex for ID layouts).
    3. Change the `get_ocr_service()` factory below to return it.
"""
import hashlib
import random
from abc import ABC, abstractmethod

from app.schemas.documents import OCRFields, OCRResponse


class OCRService(ABC):
    @abstractmethod
    async def extract(self, image_bytes: bytes, document_type: str) -> OCRResponse:
        ...


class DemoOCRService(OCRService):
    """Deterministic per-image synthetic OCR output for the prototype."""

    _DEMO_RECORDS = [
        OCRFields(name="Rahul Sharma", document_number="P123456", nationality="India", date_of_birth="1991-04-12",
                  gender="Male", issue_date="2021-03-01", expiry_date="2031-02-28"),
        OCRFields(name="Amina Yusuf", document_number="V-77281", nationality="Nigeria", date_of_birth="1994-02-20",
                  gender="Female", issue_date="2025-01-10", expiry_date="2027-01-09", visa_number="V-77281",
                  visa_type="Business", stay_duration="90 days"),
        OCRFields(name="Liu Wei", document_number="ID-556213", nationality="China", date_of_birth="1988-07-09",
                  gender="Male", issue_date="2020-03-01", expiry_date="2030-02-28"),
    ]

    async def extract(self, image_bytes: bytes, document_type: str) -> OCRResponse:
        # Use a hash of the bytes to deterministically pick a demo record so
        # repeated calls with the same test image are stable.
        digest = hashlib.sha256(image_bytes).hexdigest()
        idx = int(digest, 16) % len(self._DEMO_RECORDS)
        fields = self._DEMO_RECORDS[idx].model_copy()

        rnd = random.Random(digest)
        confidence = round(rnd.uniform(92.0, 99.5), 1)

        return OCRResponse(fields=fields, ocr_confidence=confidence)


def get_ocr_service() -> OCRService:
    return DemoOCRService()
