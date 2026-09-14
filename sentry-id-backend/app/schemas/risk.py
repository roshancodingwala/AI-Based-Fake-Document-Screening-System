from typing import Optional

from pydantic import BaseModel

from app.schemas.documents import (
    DocumentDNAResponse,
    DocumentStatusResponse,
    OCRResponse,
    TamperingResponse,
    ValidationResponse,
)
from app.schemas.face import FaceDetectResponse, FaceVerifyResponse
from app.schemas.fraud import FraudNetworkResponse
from app.schemas.identity import IdentitySearchResponse
from app.schemas.intelligence import CrossCheckpointResponse


class RiskFactor(BaseModel):
    factor: str
    weight: float
    contribution: float
    detail: str


class RiskCalculateRequest(BaseModel):
    validation: Optional[ValidationResponse] = None
    tampering: Optional[TamperingResponse] = None
    face: Optional[FaceVerifyResponse] = None
    identity_search: Optional[IdentitySearchResponse] = None
    document_status: Optional[DocumentStatusResponse] = None
    document_dna: Optional[DocumentDNAResponse] = None
    cross_checkpoint: Optional[CrossCheckpointResponse] = None
    fraud_network: Optional[FraudNetworkResponse] = None


class RiskCalculateResponse(BaseModel):
    risk_score: int
    risk_level: str  # LOW, MEDIUM, HIGH
    factors: list[RiskFactor]
    is_simulated: bool = True


class ScreenRequest(BaseModel):
    document_number: str
    identity_id: Optional[str] = None
    checkpoint_name: str = "Terminal 3 - Counter 4"
    officer_id: Optional[str] = None


class ScreenResponse(BaseModel):
    verification_id: str
    document_number: str
    ocr: OCRResponse
    validation: ValidationResponse
    tampering: TamperingResponse
    face: FaceVerifyResponse
    # Real MediaPipe face detection result (None if detection was skipped or failed at startup)
    face_detection: Optional[FaceDetectResponse] = None
    identity_search: IdentitySearchResponse
    document_status: DocumentStatusResponse
    document_dna: DocumentDNAResponse
    cross_checkpoint: CrossCheckpointResponse
    fraud_network: FraudNetworkResponse
    risk: RiskCalculateResponse
    reasons: list[str]
    is_simulated: bool = True
