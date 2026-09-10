from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import require_api_key
from app.db.database import get_db
from app.schemas.intelligence import CrossCheckpointResponse
from app.services.cross_checkpoint_service import CrossCheckpointService, get_cross_checkpoint_service

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"], dependencies=[Depends(require_api_key)])


@router.get("/cross-checkpoint/{identity_id}", response_model=CrossCheckpointResponse)
async def cross_checkpoint(
    identity_id: str,
    db: Session = Depends(get_db),
    service: CrossCheckpointService = Depends(get_cross_checkpoint_service),
):
    return service.get_history(db, identity_id)
