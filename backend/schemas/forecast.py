from typing import Literal
from pydantic import BaseModel, Field


class ForecastRequest(BaseModel):
    target:      str
    target_type: Literal["sku", "category"]
    periods:     int = Field(default=3, ge=1, le=12)
    period_unit: Literal["week", "month"] = "month"


class ForecastPeriod(BaseModel):
    period:   str
    quantity: float


class ForecastProjection(BaseModel):
    period:   str
    quantity: float
    lower:    float
    upper:    float


class ForecastResponse(BaseModel):
    historical:     list[ForecastPeriod]
    forecast:       list[ForecastProjection]
    method:         str
    recommendation: str
    explanation:    str
