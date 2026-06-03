from typing import Optional, Literal
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question:   str
    session_id: Optional[str] = None


class AnalyticsToolParams(BaseModel):
    metric:     Literal["order_count", "delay_rate", "on_time_rate", "avg_delivery_days", "order_value"]
    group_by:   Literal["carrier", "region", "product_category", "week", "month", "warehouse"]
    filters:    dict = Field(default_factory=dict)
    chart_hint: Literal["bar", "line", "pie", "table"] = "bar"


class ForecastToolParams(BaseModel):
    target:      str
    target_type: Literal["sku", "category"]
    periods:     int = Field(default=3, ge=1, le=12)
    period_unit: Literal["week", "month"] = "month"
