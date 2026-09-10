from pydantic import BaseModel, Field


class FaceVerifyResponse(BaseModel):
    similarity_score: float = Field(..., ge=0, le=1)
    match: bool
    confidence: float = Field(..., ge=0, le=1)
    model: str = "arcface-demo"
    is_simulated: bool = True
