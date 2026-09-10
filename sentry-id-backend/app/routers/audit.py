from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.logging_config import audit_logger
from app.core.security import require_api_key
from app.db.database import get_db
from app.db.models import BlockchainRecord, VerificationRecord
from app.schemas.audit import (
    BlockchainRecordItem,
    OfficerDecisionRequest,
    OfficerDecisionResponse,
)

router = APIRouter(prefix="/api", tags=["audit"], dependencies=[Depends(require_api_key)])


@router.get("/blockchain/records", response_model=list[BlockchainRecordItem])
async def list_blockchain_records(db: Session = Depends(get_db), limit: int = 20):
    records = db.query(BlockchainRecord).order_by(BlockchainRecord.timestamp.desc()).limit(limit).all()
    return records


@router.post("/verification/{verification_id}/decision", response_model=OfficerDecisionResponse)
async def record_officer_decision(
    verification_id: str,
    request: OfficerDecisionRequest,
    db: Session = Depends(get_db),
):
    record = db.query(VerificationRecord).filter(VerificationRecord.verification_id == verification_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Verification record not found.")

    record.officer_decision = request.decision
    record.officer_id = request.officer_id
    db.commit()

    audit_logger.info(
        "event=officer_decision verification_id=%s officer=%s decision=%s",
        verification_id, request.officer_id, request.decision,
    )

    return OfficerDecisionResponse(
        verification_id=verification_id,
        decision=request.decision,
        recorded_at=datetime.now(timezone.utc),
    )
