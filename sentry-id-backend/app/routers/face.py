import asyncio
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.core.security import require_api_key
from app.schemas.face import FaceDetectResponse, FaceVerifyResponse
from app.services.face_detection_service import detect_and_align
from app.services.face_service import FaceService, get_face_service
from app.utils.file_validation import validate_upload

logger = logging.getLogger("sentry_id.face_router")

router = APIRouter(prefix="/api/face", tags=["face"], dependencies=[Depends(require_api_key)])


# ---------------------------------------------------------------------------
# Existing endpoint — untouched
# ---------------------------------------------------------------------------

@router.post("/verify", response_model=FaceVerifyResponse)
async def verify_face(
    document_photo: UploadFile = File(...),
    live_photo: UploadFile = File(...),
    face_service: FaceService = Depends(get_face_service),
):
    doc_bytes = await validate_upload(document_photo)
    live_bytes = await validate_upload(live_photo)
    return await face_service.verify(doc_bytes, live_bytes)


# ---------------------------------------------------------------------------
# 3.1 — Face Detection & Alignment (NEW)
# ---------------------------------------------------------------------------

@router.post(
    "/detect",
    response_model=FaceDetectResponse,
    summary="3.1 Face Detection & Alignment",
    description=(
        "Real computer-vision face detection using MediaPipe FaceLandmarker. "
        "Detects faces, extracts 5-point landmarks, and geometrically aligns the face. "
        "Scope: detection and alignment only — no face matching, no liveness, no identity search."
    ),
)
async def detect_face(
    file: UploadFile = File(..., description="Image file (JPEG or PNG) containing a face"),
) -> FaceDetectResponse:
    """
    POST /api/face/detect

    Accepts a single image upload.  Returns:
    - bounding box and detection confidence
    - 5-point landmark coordinates
    - aligned face as base64 JPEG (224×224)
    - rotation angle used for alignment

    Status codes returned in the response body:
    - FACE_ALIGNED           — success, exactly one face processed
    - NO_FACE_DETECTED       — no faces found
    - MULTIPLE_FACES_DETECTED — more than one face; only one is accepted
    - LOW_QUALITY            — face too small or image resolution too low
    - INVALID_IMAGE          — file could not be decoded
    - ALIGNMENT_FAILED       — landmarks found but warp failed
    """
    image_bytes = await validate_upload(file)

    # Run synchronous MediaPipe + OpenCV work off the async event loop.
    from functools import partial
    loop = asyncio.get_event_loop()
    try:
        fn = partial(detect_and_align, image_bytes, original_filename=file.filename)
        result = await loop.run_in_executor(None, fn)
    except Exception as exc:
        logger.exception("face_detect=unexpected_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Face detection pipeline encountered an unexpected error.",
        ) from exc

    # Map the service dataclass → Pydantic response model
    from app.schemas.face import AlignmentInfoModel, LandmarksModel

    lm_model = None
    if result.landmarks is not None:
        lm = result.landmarks
        lm_model = LandmarksModel(
            left_eye=lm.left_eye,
            right_eye=lm.right_eye,
            nose=lm.nose,
            mouth_left=lm.mouth_left,
            mouth_right=lm.mouth_right,
        )

    align_model = AlignmentInfoModel(
        performed=result.alignment.performed,
        rotation_angle=result.alignment.rotation_angle,
        output_width=result.alignment.output_width,
        output_height=result.alignment.output_height,
    )

    logger.info(
        "face_detect=complete status=%s face_count=%d confidence=%s extracted=%s",
        result.status.value,
        result.face_count,
        result.detection_confidence,
        result.extracted_face_path,
    )

    extracted_url = None
    if result.extracted_face_filename:
        extracted_url = f"/api/face/extracted/{result.extracted_face_filename}"

    return FaceDetectResponse(
        success=result.success,
        status=result.status.value,
        face_detected=result.face_detected,
        face_count=result.face_count,
        detection_confidence=result.detection_confidence,
        landmarks_detected=result.landmarks_detected,
        landmarks=lm_model,
        bounding_box=result.bounding_box,
        alignment=align_model,
        aligned_face_b64=result.aligned_face_b64,
        model=result.model,
        message=result.message,
        extracted_face_path=result.extracted_face_path,
        extracted_face_filename=result.extracted_face_filename,
        extracted_face_url=extracted_url,
        document_preview_b64=result.document_preview_b64,
    )


# ---------------------------------------------------------------------------
# Extracted Face File Serving & Listing
# ---------------------------------------------------------------------------

@router.get(
    "/extracted/{filename}",
    summary="Download or view an extracted person face image",
    description="Serves the person image extracted from a document into the extraction folder.",
)
async def get_extracted_face(filename: str):
    import os
    from pathlib import Path
    from fastapi.responses import FileResponse

    clean_filename = os.path.basename(filename)
    extract_dir = Path("extracted_faces")
    file_path = extract_dir / clean_filename

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Extracted face image '{clean_filename}' not found in extraction folder.",
        )

    return FileResponse(
        str(file_path),
        media_type="image/jpeg",
        filename=clean_filename,
    )


@router.get(
    "/extracted",
    summary="List all extracted person faces in the extraction folder",
    description="Returns a list of all person faces extracted from uploaded documents.",
)
async def list_extracted_faces():
    import os
    from pathlib import Path

    extract_dir = Path("extracted_faces")
    if not extract_dir.exists():
        return {"total": 0, "folder": str(extract_dir), "files": []}

    files = []
    for p in sorted(extract_dir.glob("*.jpg"), key=os.path.getmtime, reverse=True):
        stat = p.stat()
        files.append({
            "filename": p.name,
            "path": str(p).replace("\\", "/"),
            "url": f"/api/face/extracted/{p.name}",
            "size_bytes": stat.st_size,
            "modified": stat.st_mtime,
        })

    return {"total": len(files), "folder": str(extract_dir), "files": files}

