from typing import Literal
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.connection import get_db
from backend.schemas.dashboard import DashboardFilters, KPIResponse, ChartResponse
from backend.services.analytics_service import run_kpi, run_chart, run_multi_series

router = APIRouter(tags=["dashboard"])


def _filters(
    from_date=Query(None),
    to_date=Query(None),
    carrier: str | None = Query(None),
    region:  str | None = Query(None),
    category: str | None = Query(None),
) -> DashboardFilters:
    return DashboardFilters(
        from_date=from_date,
        to_date=to_date,
        carrier=carrier,
        region=region,
        category=category,
    )


@router.get("/kpi", response_model=KPIResponse)
async def get_kpi(
    filters: DashboardFilters = Depends(_filters),
    db: AsyncSession = Depends(get_db),
):
    return await run_kpi(db, filters)


@router.get("/charts/order-volume", response_model=ChartResponse)
async def get_order_volume(
    granularity: Literal["week", "month"] = Query("month"),
    filters: DashboardFilters = Depends(_filters),
    db: AsyncSession = Depends(get_db),
):
    data = await run_chart(db, "order_count", granularity, filters)
    return ChartResponse(
        type="line",
        title=f"Order Volume by {granularity.capitalize()}",
        x_key="label",
        y_keys=["value"],
        data=data,
    )


@router.get("/charts/delivery-performance", response_model=ChartResponse)
async def get_delivery_performance(
    filters: DashboardFilters = Depends(_filters),
    db: AsyncSession = Depends(get_db),
):
    data = await run_multi_series(db, "delivery_performance", filters)
    return ChartResponse(
        type="bar",
        title="Delivery Performance Over Time",
        x_key="period",
        y_keys=["on_time", "delayed"],
        data=data,
    )


@router.get("/charts/carrier-breakdown", response_model=ChartResponse)
async def get_carrier_breakdown(
    filters: DashboardFilters = Depends(_filters),
    db: AsyncSession = Depends(get_db),
):
    data = await run_chart(db, "delay_rate", "carrier", filters)
    return ChartResponse(
        type="bar",
        title="Delay Rate by Carrier (%)",
        x_key="label",
        y_keys=["value"],
        data=data,
    )


@router.get("/charts/region-breakdown", response_model=ChartResponse)
async def get_region_breakdown(
    filters: DashboardFilters = Depends(_filters),
    db: AsyncSession = Depends(get_db),
):
    data = await run_multi_series(db, "region_breakdown", filters)
    return ChartResponse(
        type="bar",
        title="Order Volume & Delay Rate by Region",
        x_key="label",
        y_keys=["order_count", "delay_rate"],
        data=data,
    )
