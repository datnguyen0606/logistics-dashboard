from pydantic import BaseModel, Field


class ForecastRequest(BaseModel):
    question: str


class ForecastPeriod(BaseModel):
    period:   str
    quantity: float


class ForecastProjection(BaseModel):
    period:   str
    quantity: float
    lower:    float
    upper:    float


class ForecastResponse(BaseModel):
    title:          str
    historical:     list[ForecastPeriod]
    forecast:       list[ForecastProjection]
    method:         str
    recommendation: str
    explanation:    str
