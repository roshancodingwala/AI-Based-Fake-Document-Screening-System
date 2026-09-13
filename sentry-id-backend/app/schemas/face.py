from typing import Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Existing schema — DO NOT MODIFY (used by /api/face/verify)
# ---------------------------------------------------------------------------

class FaceVerifyResponse(BaseModel):
    similarity_score: float = Field(..., ge=0, le=1)
    match: bool
    confidence: float = Field(..., ge=0, le=1)
    model: str = "arcface-demo"
    is_simulated: bool = True


# ---------------------------------------------------------------------------
# 3.1 Face Detection & Alignment schemas
# ---------------------------------------------------------------------------

class LandmarksModel(BaseModel):
    """Absolute pixel coordinates for 5 canonical facial landmarks."""
    left_eye:    tuple[float, float]
    right_eye:   tuple[float, float]
    nose:        tuple[float, float]
    mouth_left:  tuple[float, float]
    mouth_right: tuple[float, float]


class AlignmentInfoModel(BaseModel):
    performed:      bool
    rotation_angle: float  = Field(description="Degrees; negative = face tilted right")
    output_width:   int
    output_height:  int


class FaceDetectResponse(BaseModel):
    """
    Response for POST /api/face/detect.

    SCOPE: 3.1 detection + alignment only.
    Does NOT include matching score, liveness, or identity info.
    """
    success:              bool
    status:               str   = Field(description="DetectionStatus enum value")
    face_detected:        bool
    face_count:           int   = Field(ge=0)
    detection_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    landmarks_detected:   bool
    landmarks:            Optional[LandmarksModel]  = None
    bounding_box:         Optional[list[int]]        = Field(
        default=None,
        description="[x1, y1, x2, y2] in absolute pixels of the original image"
    )
    alignment:            AlignmentInfoModel
    aligned_face_b64:     Optional[str]              = Field(
        default=None,
        description="Base64-encoded JPEG of the geometrically aligned face (224×224)"
    )
    model:                str = "mediapipe-face-landmarker"
    message:              Optional[str] = None
    extracted_face_path:  Optional[str] = Field(
        default=None,
        description="Path on disk where the extracted person image is stored"
    )
    extracted_face_filename: Optional[str] = Field(
        default=None,
        description="Filename of the extracted person image in the extraction folder"
    )
    extracted_face_url:   Optional[str] = Field(
        default=None,
        description="Relative URL to view or download the extracted person image"
    )
    document_preview_b64: Optional[str] = Field(
        default=None,
        description="Base64 JPEG of the document page (for PDF and multi-format documents)"
    )

