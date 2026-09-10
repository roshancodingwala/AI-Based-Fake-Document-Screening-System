from fastapi import APIRouter, Depends, File, UploadFile

from app.core.security import require_api_key
from app.schemas.face import FaceVerifyResponse
from app.services.face_service import FaceService, get_face_service
from app.utils.file_validation import validate_upload

router = APIRouter(prefix="/api/face", tags=["face"], dependencies=[Depends(require_api_key)])


@router.post("/verify", response_model=FaceVerifyResponse)
async def verify_face(
    document_photo: UploadFile = File(...),
    live_photo: UploadFile = File(...),
    face_service: FaceService = Depends(get_face_service),
):
    doc_bytes = await validate_upload(document_photo)
    live_bytes = await validate_upload(live_photo)
    return await face_service.verify(doc_bytes, live_bytes)
