from fastapi import APIRouter, Depends

from app.core.security import require_api_key
from app.schemas.risk import RiskCalculateRequest, RiskCalculateResponse
from app.services.risk_engine import RiskEngine, get_risk_engine

router = APIRouter(prefix="/api/risk", tags=["risk"], dependencies=[Depends(require_api_key)])


@router.post("/calculate", response_model=RiskCalculateResponse)
async def calculate_risk(
    request: RiskCalculateRequest,
    engine: RiskEngine = Depends(get_risk_engine),
):
    return engine.calculate(request)
