from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import require_api_key
from app.db.database import get_db
from app.schemas.ai_testing import SelfTestHistoryItem, SelfTestRequest, SelfTestResponse
from app.services.self_test_service import SelfTestService, get_self_test_service

router = APIRouter(prefix="/api/ai", tags=["ai-testing"], dependencies=[Depends(require_api_key)])


@router.post("/self-test", response_model=SelfTestResponse)
async def run_self_test(
    request: SelfTestRequest,
    db: Session = Depends(get_db),
    service: SelfTestService = Depends(get_self_test_service),
):
    return service.run_test(db, request)


@router.get("/self-test/history", response_model=list[SelfTestHistoryItem])
async def self_test_history(
    db: Session = Depends(get_db),
    service: SelfTestService = Depends(get_self_test_service),
):
    return service.history(db)
