"""
Document DNA: compares a document's structural fingerprint (font, layout,
compression profile, print pattern, dimensions, security feature
placement, photo offset) against previously flagged documents in the same
fraud family.

Real implementation notes: font signature would come from stroke-width /
glyph-shape clustering, layout from a document-layout-analysis model
(e.g. LayoutLMv3), and print-pattern from microtexture analysis on a
high-DPI scan. The prototype instead reads pre-computed demo fingerprints
stored on the `Document` row (see db/seed.py).
"""
import json

from sqlalchemy.orm import Session

from app.db.models import Document
from app.schemas.documents import DNAFactor, DNARelatedDocument, DocumentDNAResponse

FACTOR_LABELS = {
    "font": "Font signature",
    "layout": "Layout grid",
    "compression": "Image compression profile",
    "print_pattern": "Print pattern (microtext)",
    "dimensions": "Document dimensions",
    "security_features": "Security feature placement",
    "photo_offset": "Photo placement offset",
}


class DocumentDNAService:
    def compare(self, db: Session, document_number: str) -> DocumentDNAResponse:
        doc = db.query(Document).filter(Document.document_number == document_number).first()

        if doc is None or not doc.dna_fingerprint:
            return DocumentDNAResponse(
                document_number=document_number,
                similarity_score=0.0,
                matching_features=[],
                related_documents=[],
                summary="No structural fingerprint available for this document.",
            )

        fingerprint = json.loads(doc.dna_fingerprint)
        factors = [DNAFactor(name=FACTOR_LABELS.get(k, k), score=round(v * 100, 1)) for k, v in fingerprint.items()]
        overall = round(sum(fingerprint.values()) / len(fingerprint) * 100, 1)

        related_docs: list[DNARelatedDocument] = []
        if doc.fraud_family_id:
            siblings = (
                db.query(Document)
                .filter(Document.fraud_family_id == doc.fraud_family_id, Document.document_number != document_number)
                .all()
            )
            for sib in siblings:
                if not sib.dna_fingerprint:
                    continue
                sib_fp = json.loads(sib.dna_fingerprint)
                # Simple mean-absolute-difference similarity between fingerprints
                shared_keys = set(fingerprint) & set(sib_fp)
                if not shared_keys:
                    continue
                diff = sum(abs(fingerprint[k] - sib_fp[k]) for k in shared_keys) / len(shared_keys)
                match = round((1 - diff) * 100, 1)
                related_docs.append(
                    DNARelatedDocument(document_id=sib.document_number, flagged_on=sib.created_at.date().isoformat() if sib.created_at else None, match=match)
                )
            related_docs.sort(key=lambda d: d.match, reverse=True)

        summary = (
            f"Similar pattern detected in {len(related_docs)} previously flagged documents."
            if related_docs
            else "No related flagged documents found for this structural pattern."
        )

        return DocumentDNAResponse(
            document_number=document_number,
            similarity_score=overall,
            matching_features=factors,
            related_documents=related_docs,
            summary=summary,
        )


def get_dna_service() -> DocumentDNAService:
    return DocumentDNAService()
