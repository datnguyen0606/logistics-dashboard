from typing import Optional
from pydantic import BaseModel


class QueryRequest(BaseModel):
    question:   str
    session_id: Optional[str] = None


class AnalyticsToolParams(BaseModel):
    question: str


class ForecastToolParams(BaseModel):
    question: str
