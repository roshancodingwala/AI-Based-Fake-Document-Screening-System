from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import require_api_key
from app.db.database import get_db
from app.schemas.fraud import (
    ConfirmedFraudCaseRequest,
    ConfirmedFraudCaseResponse,
    FraudFamilyResponse,
    FraudNetworkResponse,
)
from app.services.fraud_family_service import FraudFamilyService, get_fraud_family_service
from app.services.fraud_learning_service import FraudLearningService, get_fraud_learning_service
from app.services.fraud_network_service import FraudNetworkService, get_fraud_network_service

router = APIRouter(prefix="/api/fraud", tags=["fraud"], dependencies=[Depends(require_api_key)])


@router.post("/family", response_model=FraudFamilyResponse)
async def get_fraud_family(
    document_number: str,
    db: Session = Depends(get_db),
    family_service: FraudFamilyService = Depends(get_fraud_family_service),
):
    result = family_service.get_family_for_document(db, document_number)
    if result is None:
        raise HTTPException(status_code=404, detail="No fraud family found for this document.")
    return result


@router.get("/network/{identity_id}", response_model=FraudNetworkResponse)
async def get_fraud_network(
    identity_id: str,
    db: Session = Depends(get_db),
    network_service: FraudNetworkService = Depends(get_fraud_network_service),
):
    return network_service.build(db, identity_id)


@router.post("/confirmed", response_model=ConfirmedFraudCaseResponse)
async def confirm_fraud_case(
    request: ConfirmedFraudCaseRequest,
    db: Session = Depends(get_db),
    learning_service: FraudLearningService = Depends(get_fraud_learning_service),
):
    return learning_service.record(db, request)
