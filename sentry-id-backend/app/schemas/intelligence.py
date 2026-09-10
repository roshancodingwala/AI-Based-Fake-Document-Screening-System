from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class CheckpointHit(BaseModel):
    checkpoint_name: str
    city: Optional[str] = None
    risk_level: str
    timestamp: datetime
    notes: Optional[str] = None


class CrossCheckpointResponse(BaseModel):
    identity_id: str
    total_checkpoints: int
    total_appearances: int
    alert: bool
    alert_message: Optional[str] = None
    history: list[CheckpointHit]
    is_simulated: bool = True
