from sqlalchemy.orm import Session

from app.db.models import Document, FraudFamily
from app.schemas.fraud import FraudFamilyResponse


class FraudFamilyService:
    def get_family_for_document(self, db: Session, document_number: str) -> FraudFamilyResponse | None:
        doc = db.query(Document).filter(Document.document_number == document_number).first()
        if doc is None or not doc.fraud_family_id:
            return None

        family = db.query(FraudFamily).filter(FraudFamily.fraud_family_id == doc.fraud_family_id).first()
        if family is None:
            return None

        members = db.query(Document).filter(Document.fraud_family_id == family.fraud_family_id).all()

        return FraudFamilyResponse(
            fraud_family_id=family.fraud_family_id,
            related_document_count=len(members),
            common_pattern=family.common_pattern,
            suspicious_source=family.suspicious_source,
            related_documents=[m.document_number for m in members],
        )


def get_fraud_family_service() -> FraudFamilyService:
    return FraudFamilyService()
