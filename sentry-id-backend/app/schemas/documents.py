from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class OCRFields(BaseModel):
    name: Optional[str] = None
    document_number: Optional[str] = None
    nationality: Optional[str] = None
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    issue_date: Optional[str] = None
    expiry_date: Optional[str] = None
    visa_number: Optional[str] = None
    visa_type: Optional[str] = None
    stay_duration: Optional[str] = None


class OCRResponse(BaseModel):
    fields: OCRFields
    ocr_confidence: float = Field(..., ge=0, le=100)
    engine: str = "paddleocr-demo"
    is_simulated: bool = True


class ValidationRequest(BaseModel):
    fields: OCRFields


class ValidationResponse(BaseModel):
    is_valid: bool
    errors: list[str] = []
    warnings: list[str] = []


class TamperingResponse(BaseModel):
    status: str  # CLEAN, SUSPICIOUS, TAMPERED
    confidence: float = Field(..., ge=0, le=1)
    suspicious_regions: list[str] = []
    reasons: list[str] = []
    is_simulated: bool = True


class DocumentStatusResponse(BaseModel):
    document_number: str
    status: str  # VALID, EXPIRED, REVOKED, BLACKLISTED, UNKNOWN
    source: str
    detail: Optional[str] = None
    checked_at: datetime


class DNAFactor(BaseModel):
    name: str
    score: float


class DNARelatedDocument(BaseModel):
    document_id: str
    flagged_on: Optional[str] = None
    match: float


class DocumentDNAResponse(BaseModel):
    document_number: str
    similarity_score: float
    matching_features: list[DNAFactor]
    related_documents: list[DNARelatedDocument]
    summary: str
    is_simulated: bool = True
