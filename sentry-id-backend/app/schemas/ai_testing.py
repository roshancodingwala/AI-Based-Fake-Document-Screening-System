from datetime import datetime

from pydantic import BaseModel


class SelfTestRequest(BaseModel):
    manipulation_type: str
    # Name of a synthetic test document from the demo test set. In a real
    # system this would be an uploaded test image instead.
    test_document_id: str = "synthetic-test-set-4"


class SelfTestResponse(BaseModel):
    test_id: str
    manipulation_type: str
    predicted_detection: bool
    confidence: float
    correct: bool
    is_simulated: bool = True


class SelfTestHistoryItem(BaseModel):
    test_id: str
    manipulation_type: str
    predicted_detection: bool
    confidence: float
    correct: bool
    created_at: datetime
