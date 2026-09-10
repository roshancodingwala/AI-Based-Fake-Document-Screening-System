from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class BlockchainRecordItem(BaseModel):
    verification_id: str
    document_hash: str
    result: str
    status: str
    timestamp: datetime


class OfficerDecisionRequest(BaseModel):
    officer_id: str
    decision: Literal["CLEARED", "SECONDARY_INSPECTION", "DENIED"]
    notes: str | None = None


class OfficerDecisionResponse(BaseModel):
    verification_id: str
    decision: str
    recorded_at: datetime
