import logging

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.core.security import require_api_key
from app.db.database import get_db
from app.schemas.documents import (
    DocumentDNAResponse,
    DocumentStatusResponse,
    OCRResponse,
    TamperingResponse,
    ValidationRequest,
    ValidationResponse,
)
from app.services.dna_service import DocumentDNAService, get_dna_service
from app.services.document_status_service import DocumentStatusService, get_document_status_service
from app.services.ocr_service import OCRService, get_ocr_service
from app.services.tampering_service import TamperingService, get_tampering_service
from app.services.validation_service import ValidationService, get_validation_service
from app.utils.file_validation import validate_upload

router = APIRouter(prefix="/api/documents", tags=["documents"], dependencies=[Depends(require_api_key)])
logger = logging.getLogger("sentry_id.documents")


@router.post("/ocr", response_model=OCRResponse)
async def extract_ocr(
    file: UploadFile = File(...),
    document_type: str = Form("Passport"),
    ocr_service: OCRService = Depends(get_ocr_service),
):
    contents = await validate_upload(file)
    return await ocr_service.extract(contents, document_type)


@router.post("/validate", response_model=ValidationResponse)
async def validate_document(
    request: ValidationRequest,
    validation_service: ValidationService = Depends(get_validation_service),
):
    return validation_service.validate(request.fields, document_type="Passport")


@router.post("/tampering", response_model=TamperingResponse)
async def detect_tampering(
    file: UploadFile = File(...),
    tampering_service: TamperingService = Depends(get_tampering_service),
):
    contents = await validate_upload(file)
    return await tampering_service.analyze(contents)


@router.get("/status/{document_number}", response_model=DocumentStatusResponse)
async def get_document_status(
    document_number: str,
    db: Session = Depends(get_db),
    status_service: DocumentStatusService = Depends(get_document_status_service),
):
    return status_service.check(db, document_number)


@router.post("/dna", response_model=DocumentDNAResponse)
async def document_dna(
    document_number: str = Form(...),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    dna_service: DocumentDNAService = Depends(get_dna_service),
):
    if file is not None:
        await validate_upload(file)
    return dna_service.compare(db, document_number)
