from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import require_api_key
from app.db.database import get_db
from app.schemas.identity import IdentitySearchRequest, IdentitySearchResponse
from app.services.identity_service import IdentitySearchService, get_identity_search_service

router = APIRouter(prefix="/api/identity", tags=["identity"], dependencies=[Depends(require_api_key)])


@router.post("/search", response_model=IdentitySearchResponse)
async def search_identity(
    request: IdentitySearchRequest,
    db: Session = Depends(get_db),
    search_service: IdentitySearchService = Depends(get_identity_search_service),
):
    if not request.identity_id:
        raise HTTPException(status_code=400, detail="identity_id is required in this prototype.")
    return search_service.search(db, request.identity_id)
