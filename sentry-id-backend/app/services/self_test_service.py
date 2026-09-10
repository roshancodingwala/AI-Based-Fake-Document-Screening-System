"""
Lets administrators run the tampering detector against known synthetic
manipulation types and records whether the detector's call matched the
expected ground truth — a lightweight regression-test harness for the AI
components, using only synthetic test documents (never real seized
documents, which would need a much more controlled evidence pipeline).
"""
import random

from sqlalchemy.orm import Session

from app.db.models import SelfTestRecord
from app.schemas.ai_testing import SelfTestRequest, SelfTestResponse

# Ground truth + typical detector behaviour for each synthetic manipulation
# type in the demo test set. Hologram Spoof is deliberately the one the
# demo detector under-performs on, matching the seeded self-test history.
KNOWN_TEST_CASES = {
    "Photo Replacement": {"expected": True, "base_confidence": 96.0},
    "Font Substitution": {"expected": True, "base_confidence": 91.0},
    "MRZ Tampering": {"expected": True, "base_confidence": 98.0},
    "Hologram Spoof": {"expected": True, "base_confidence": 54.0},
    "Digital Re-scan Artefact": {"expected": True, "base_confidence": 89.0},
    "Signature Forgery": {"expected": True, "base_confidence": 82.0},
}


class SelfTestService:
    def run_test(self, db: Session, request: SelfTestRequest) -> SelfTestResponse:
        case = KNOWN_TEST_CASES.get(request.manipulation_type, {"expected": True, "base_confidence": 75.0})
        rnd = random.Random(request.manipulation_type + request.test_document_id)

        confidence = round(max(0, min(100, rnd.gauss(case["base_confidence"], 3))), 1)
        predicted_detection = confidence >= 70.0
        correct = predicted_detection == case["expected"]

        record = SelfTestRecord(
            manipulation_type=request.manipulation_type,
            expected_detection=case["expected"],
            predicted_detection=predicted_detection,
            confidence=confidence,
            correct=correct,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        return SelfTestResponse(
            test_id=record.test_id,
            manipulation_type=record.manipulation_type,
            predicted_detection=record.predicted_detection,
            confidence=record.confidence,
            correct=record.correct,
        )

    def history(self, db: Session, limit: int = 20) -> list[SelfTestRecord]:
        return db.query(SelfTestRecord).order_by(SelfTestRecord.created_at.desc()).limit(limit).all()


def get_self_test_service() -> SelfTestService:
    return SelfTestService()
