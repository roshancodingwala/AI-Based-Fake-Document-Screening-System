from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class FraudFamilyResponse(BaseModel):
    fraud_family_id: str
    related_document_count: int
    common_pattern: str
    suspicious_source: Optional[str] = None
    related_documents: list[str]
    is_simulated: bool = True


class GraphNode(BaseModel):
    id: str
    label: str
    type: str  # person | document | pattern | checkpoint | case


class GraphEdge(BaseModel):
    source: str
    target: str


class FraudNetworkResponse(BaseModel):
    identity_id: str
    connected_cases: int
    common_pattern: Optional[str] = None
    checkpoints_involved: list[str]
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    is_simulated: bool = True


class ConfirmedFraudCaseRequest(BaseModel):
    document_number: str
    fraud_type: str
    detected_features: list[str] = []
    officer_id: str
    officer_notes: Optional[str] = None


class ConfirmedFraudCaseResponse(BaseModel):
    id: int
    document_number: str
    fraud_type: str
    confirmed_at: datetime
    message: str = "Stored for future model retraining. Not applied automatically."
