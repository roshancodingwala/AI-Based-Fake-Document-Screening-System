"""
Stores officer-confirmed fraud cases as future training/intelligence
examples. Explicitly does NOT retrain or update any live model — a human
review and validation step should always sit between "officer confirmed
this one case" and "the production model changed its behaviour".
"""
import json

from sqlalchemy.orm import Session

from app.core.logging_config import audit_logger
from app.db.models import ConfirmedFraudCase
from app.schemas.fraud import ConfirmedFraudCaseRequest, ConfirmedFraudCaseResponse


class FraudLearningService:
    def record(self, db: Session, request: ConfirmedFraudCaseRequest) -> ConfirmedFraudCaseResponse:
        record = ConfirmedFraudCase(
            document_number=request.document_number,
            fraud_type=request.fraud_type,
            detected_features=json.dumps(request.detected_features),
            officer_id=request.officer_id,
            officer_notes=request.officer_notes,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        audit_logger.info(
            "event=confirmed_fraud_case document=%s fraud_type=%s officer=%s",
            request.document_number, request.fraud_type, request.officer_id,
        )

        return ConfirmedFraudCaseResponse(
            id=record.id,
            document_number=record.document_number,
            fraud_type=record.fraud_type,
            confirmed_at=record.confirmed_at,
        )


def get_fraud_learning_service() -> FraudLearningService:
    return FraudLearningService()
