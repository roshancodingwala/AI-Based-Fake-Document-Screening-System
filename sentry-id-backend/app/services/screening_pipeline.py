"""
Orchestrates the full screening pipeline for POST /api/screen:

    OCR -> Validation -> Tampering -> Face -> Identity Search
    -> Document Status -> Document DNA -> Cross-Checkpoint -> Fraud Network
    -> Risk Score

Each stage is a separately-swappable service (see the individual service
modules); this file only wires them together and builds the officer-facing
explanation. Persists a VerificationRecord and a hash-only blockchain audit
row for every run.
"""
import json
import logging

from sqlalchemy.orm import Session

from app.core.logging_config import audit_logger
from app.db.models import Document, Identity, VerificationRecord
from app.schemas.identity import IdentitySearchResponse
from app.schemas.intelligence import CrossCheckpointResponse
from app.schemas.fraud import FraudNetworkResponse
from app.schemas.risk import RiskCalculateRequest, ScreenResponse
from app.services.cross_checkpoint_service import get_cross_checkpoint_service
from app.services.document_status_service import get_document_status_service
from app.services.dna_service import get_dna_service
from app.services.face_service import get_face_service
from app.services.fraud_network_service import get_fraud_network_service
from app.services.identity_service import get_identity_search_service
from app.services.ocr_service import get_ocr_service
from app.services.risk_engine import get_risk_engine
from app.services.tampering_service import get_tampering_service
from app.services.validation_service import get_validation_service
from app.services.blockchain_service import get_blockchain_service

logger = logging.getLogger("sentry_id.pipeline")


def _build_reasons(response_parts: dict) -> list[str]:
    reasons: list[str] = []

    tampering = response_parts["tampering"]
    if tampering.reasons and tampering.status != "CLEAN":
        reasons.extend(tampering.reasons)

    face = response_parts["face"]
    if not face.match:
        reasons.append(f"Face match score of {face.similarity_score:.0%} is below the confident-match threshold.")

    identity_search: IdentitySearchResponse = response_parts["identity_search"]
    for match in identity_search.matches:
        reasons.append(f"Similar identity found: {match.identity_id} ({match.similarity:.0%} similarity) — requires officer review.")

    status = response_parts["document_status"]
    if status.status == "BLACKLISTED":
        reasons.append(f"Document is blacklisted: {status.detail}")
    elif status.status == "EXPIRED":
        reasons.append("Document has expired.")
    elif status.status == "REVOKED":
        reasons.append("Document has been revoked.")

    dna = response_parts["document_dna"]
    if dna.related_documents:
        reasons.append(dna.summary)

    fraud_network: FraudNetworkResponse = response_parts["fraud_network"]
    if fraud_network.connected_cases > 1:
        pattern_note = f" (pattern: {fraud_network.common_pattern})" if fraud_network.common_pattern else ""
        reasons.append(f"Part of a network of {fraud_network.connected_cases} connected documents{pattern_note}.")

    cross_checkpoint: CrossCheckpointResponse = response_parts["cross_checkpoint"]
    if cross_checkpoint.alert:
        reasons.append(cross_checkpoint.alert_message)

    validation = response_parts["validation"]
    if not validation.is_valid:
        reasons.extend(f"Validation error: {e}" for e in validation.errors)

    return reasons or ["No significant risk indicators detected."]


class ScreeningPipeline:
    async def run(
        self,
        db: Session,
        document_image: bytes,
        document_type: str,
        checkpoint_name: str,
        officer_id: str | None,
        live_photo: bytes | None = None,
        identity_id: str | None = None,
    ) -> ScreenResponse:
        ocr_service = get_ocr_service()
        validation_service = get_validation_service()
        tampering_service = get_tampering_service()
        face_service = get_face_service()
        identity_service = get_identity_search_service()
        status_service = get_document_status_service()
        dna_service = get_dna_service()
        cross_checkpoint_service = get_cross_checkpoint_service()
        fraud_network_service = get_fraud_network_service()
        risk_engine = get_risk_engine()
        blockchain_service = get_blockchain_service()

        # 1. OCR
        ocr = await ocr_service.extract(document_image, document_type)
        document_number = ocr.fields.document_number or "UNKNOWN"

        # 2. Validation
        validation = validation_service.validate(ocr.fields, document_type)

        # 3. Tampering
        tampering = await tampering_service.analyze(document_image)

        # 4. Face verification (uses live photo if provided, else compares
        # the document photo against itself as a neutral placeholder so the
        # pipeline can still run end-to-end in the prototype).
        face = await face_service.verify(document_image, live_photo or document_image)

        # Resolve identity: prefer explicit identity_id, else look up by
        # document number in the demo registry.
        resolved_identity_id = identity_id
        if resolved_identity_id is None:
            doc_record = db.query(Document).filter(Document.document_number == document_number).first()
            if doc_record is not None:
                resolved_identity_id = doc_record.identity_id

        # 5. Identity search
        if resolved_identity_id:
            identity_search = identity_service.search(db, resolved_identity_id)
        else:
            identity_search = IdentitySearchResponse(possible_multiple_identity=False, matches=[])

        # 6. Document status
        document_status = status_service.check(db, document_number)

        # 7. Document DNA
        document_dna = dna_service.compare(db, document_number)

        # 8. Cross-checkpoint intelligence
        if resolved_identity_id:
            cross_checkpoint = cross_checkpoint_service.get_history(db, resolved_identity_id)
        else:
            cross_checkpoint = CrossCheckpointResponse(
                identity_id="UNKNOWN", total_checkpoints=0, total_appearances=0, alert=False, history=[]
            )

        # 9. Fraud network
        if resolved_identity_id:
            fraud_network = fraud_network_service.build(db, resolved_identity_id)
        else:
            fraud_network = FraudNetworkResponse(
                identity_id="UNKNOWN", connected_cases=0, common_pattern=None, checkpoints_involved=[], nodes=[], edges=[]
            )

        # 10. Risk score
        risk = risk_engine.calculate(RiskCalculateRequest(
            validation=validation,
            tampering=tampering,
            face=face,
            identity_search=identity_search,
            document_status=document_status,
            document_dna=document_dna,
            cross_checkpoint=cross_checkpoint,
            fraud_network=fraud_network,
        ))

        parts = {
            "validation": validation, "tampering": tampering, "face": face,
            "identity_search": identity_search, "document_status": document_status,
            "document_dna": document_dna, "cross_checkpoint": cross_checkpoint,
            "fraud_network": fraud_network,
        }
        reasons = _build_reasons(parts)

        record = VerificationRecord(
            document_number=document_number,
            identity_id=resolved_identity_id,
            checkpoint_name=checkpoint_name,
            risk_score=risk.risk_score,
            risk_level=risk.risk_level,
            result_json=json.dumps({"risk": risk.model_dump(), "reasons": reasons}),
            officer_id=officer_id,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        blockchain_service.record(
            db,
            verification_id=record.verification_id,
            outcome_summary=f"{record.verification_id}:{document_number}:{risk.risk_level}:{risk.risk_score}",
            result="VERIFIED" if risk.risk_level == "LOW" else "FLAGGED",
        )

        audit_logger.info(
            "event=screening_complete verification_id=%s document=%s risk_score=%s risk_level=%s officer=%s",
            record.verification_id, document_number, risk.risk_score, risk.risk_level, officer_id,
        )

        return ScreenResponse(
            verification_id=record.verification_id,
            document_number=document_number,
            ocr=ocr,
            validation=validation,
            tampering=tampering,
            face=face,
            identity_search=identity_search,
            document_status=document_status,
            document_dna=document_dna,
            cross_checkpoint=cross_checkpoint,
            fraud_network=fraud_network,
            risk=risk,
            reasons=reasons,
        )


def get_screening_pipeline() -> ScreeningPipeline:
    return ScreeningPipeline()
