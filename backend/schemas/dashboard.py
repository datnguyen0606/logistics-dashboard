from datetime import date
from typing import Optional
from pydantic import BaseModel


class DashboardFilters(BaseModel):
    from_date: Optional[date] = None
    to_date:   Optional[date] = None
    carrier:   Optional[str]  = None
    region:    Optional[str]  = None
    category:  Optional[str]  = None


class KPIResponse(BaseModel):
    total_orders:      int
    delivered_orders:  int
    delayed_orders:    int
    on_time_rate:      float
    avg_delivery_days: float
    total_order_value: float


class ChartResponse(BaseModel):
    type:   str
    title:  str
    x_key:  str
    y_keys: list[str]
    data:   list[dict]
