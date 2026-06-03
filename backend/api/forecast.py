from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.connection import get_db
from backend.schemas.forecast import ForecastRequest, ForecastResponse
from backend.services.forecast_service import forecast_demand

router = APIRouter(tags=["forecast"])


@router.post("/forecast", response_model=ForecastResponse)
async def get_forecast(
    body: ForecastRequest,
    db: AsyncSession = Depends(get_db),
):
    return await forecast_demand(db, body.target, body.target_type, body.periods, body.period_unit)
