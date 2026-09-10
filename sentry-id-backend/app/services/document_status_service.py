from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import Document
from app.schemas.documents import DocumentStatusResponse


class DocumentStatusService:
    def check(self, db: Session, document_number: str) -> DocumentStatusResponse:
        doc = db.query(Document).filter(Document.document_number == document_number).first()

        if doc is None:
            return DocumentStatusResponse(
                document_number=document_number,
                status="UNKNOWN",
                source="demo-registry",
                detail="No record found in the demo registry for this document number.",
                checked_at=datetime.now(timezone.utc),
            )

        detail = doc.blacklist_reason if doc.status == "BLACKLISTED" else None
        return DocumentStatusResponse(
            document_number=document_number,
            status=doc.status,
            source="demo-registry",
            detail=detail,
            checked_at=datetime.now(timezone.utc),
        )


def get_document_status_service() -> DocumentStatusService:
    return DocumentStatusService()
