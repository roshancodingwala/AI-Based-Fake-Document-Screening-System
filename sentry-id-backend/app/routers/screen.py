from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.core.security import require_api_key
from app.db.database import get_db
from app.schemas.risk import ScreenResponse
from app.services.screening_pipeline import ScreeningPipeline, get_screening_pipeline
from app.utils.file_validation import validate_upload

router = APIRouter(prefix="/api", tags=["screen"], dependencies=[Depends(require_api_key)])


@router.post("/screen", response_model=ScreenResponse)
async def screen_document(
    document_image: UploadFile = File(...),
    document_type: str = Form("Passport"),
    checkpoint_name: str = Form("Terminal 3 - Counter 4"),
    officer_id: str | None = Form(None),
    identity_id: str | None = Form(None),
    live_photo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    pipeline: ScreeningPipeline = Depends(get_screening_pipeline),
):
    """
    Runs the complete screening pipeline end-to-end:
    OCR -> Validation -> Tampering -> Face -> Identity Search ->
    Document Status -> Document DNA -> Cross-Checkpoint -> Fraud Network -> Risk Score.

    `identity_id` can be passed explicitly for demo/testing (e.g. `IDN-RS001`
    to reproduce the seeded high-risk scenario); otherwise the pipeline
    resolves it from the OCR'd document number against the demo registry.
    """
    doc_bytes = await validate_upload(document_image)
    live_bytes = await validate_upload(live_photo) if live_photo is not None else None

    return await pipeline.run(
        db=db,
        document_image=doc_bytes,
        document_type=document_type,
        checkpoint_name=checkpoint_name,
        officer_id=officer_id,
        live_photo=live_bytes,
        identity_id=identity_id,
    )
