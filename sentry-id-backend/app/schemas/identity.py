from typing import Optional

from pydantic import BaseModel, Field


class IdentitySearchRequest(BaseModel):
    # In production this would take a face embedding derived server-side
    # from an uploaded image. The prototype accepts an identity_id or a
    # raw embedding directly so it can be exercised without real ML models.
    identity_id: Optional[str] = Field(
        None, description="Known demo identity ID to search against the index, e.g. IDN-RS001"
    )


class IdentityMatch(BaseModel):
    identity_id: str
    name: str
    similarity: float = Field(..., ge=0, le=1)
    requires_officer_review: bool


class IdentitySearchResponse(BaseModel):
    possible_multiple_identity: bool
    matches: list[IdentityMatch]
    note: str = (
        "Similarity search only. This system never automatically declares two "
        "people the same person — a human officer must review any match."
    )
    is_simulated: bool = True
