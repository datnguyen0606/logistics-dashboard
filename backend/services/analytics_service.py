from datetime import date, timedelta
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from backend.schemas.dashboard import DashboardFilters, KPIResponse, ChartResponse

# Default window: last 90 days relative to the latest order_date in the dataset
_DEFAULT_WINDOW_DAYS = 90

QUERY_TEMPLATES: dict[tuple[str, str], str] = {
    ("delay_rate", "carrier"): """
        SELECT carrier AS label,
               ROUND(100.0 * SUM(is_delayed::int) / NULLIF(COUNT(*), 0), 1) AS value
        FROM orders WHERE {where} GROUP BY carrier ORDER BY value DESC
    """,
    ("delay_rate", "region"): """
        SELECT region AS label,
               ROUND(100.0 * SUM(is_delayed::int) / NULLIF(COUNT(*), 0), 1) AS value
        FROM orders WHERE {where} GROUP BY region ORDER BY value DESC
    """,
    ("delay_rate", "product_category"): """
        SELECT product_category AS label,
               ROUND(100.0 * SUM(is_delayed::int) / NULLIF(COUNT(*), 0), 1) AS value
        FROM orders WHERE {where} GROUP BY product_category ORDER BY value DESC
    """,
    ("on_time_rate", "carrier"): """
        SELECT carrier AS label,
               ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'delivered') / NULLIF(COUNT(*), 0), 1) AS value
        FROM orders WHERE {where} GROUP BY carrier ORDER BY value DESC
    """,
    ("order_count", "month"): """
        SELECT TO_CHAR(DATE_TRUNC('month', order_date), 'YYYY-MM') AS label,
               COUNT(*) AS value
        FROM orders WHERE {where} GROUP BY DATE_TRUNC('month', order_date) ORDER BY 1
    """,
    ("order_count", "week"): """
        SELECT TO_CHAR(DATE_TRUNC('week', order_date), 'YYYY-"W"IW') AS label,
               COUNT(*) AS value
        FROM orders WHERE {where} GROUP BY DATE_TRUNC('week', order_date) ORDER BY 1
    """,
    ("order_count", "carrier"): """
        SELECT carrier AS label, COUNT(*) AS value
        FROM orders WHERE {where} GROUP BY carrier ORDER BY value DESC
    """,
    ("order_count", "region"): """
        SELECT region AS label, COUNT(*) AS value
        FROM orders WHERE {where} GROUP BY region ORDER BY value DESC
    """,
    ("order_count", "product_category"): """
        SELECT product_category AS label, COUNT(*) AS value
        FROM orders WHERE {where} GROUP BY product_category ORDER BY value DESC
    """,
    ("order_value", "product_category"): """
        SELECT product_category AS label,
               ROUND(SUM(order_value_usd)::numeric, 2) AS value
        FROM orders WHERE {where} GROUP BY product_category ORDER BY value DESC
    """,
    ("order_value", "carrier"): """
        SELECT carrier AS label,
               ROUND(SUM(order_value_usd)::numeric, 2) AS value
        FROM orders WHERE {where} GROUP BY carrier ORDER BY value DESC
    """,
    ("avg_delivery_days", "carrier"): """
        SELECT carrier AS label,
               ROUND(AVG(delivery_days)::numeric, 1) AS value
        FROM orders WHERE {where} AND delivery_days IS NOT NULL GROUP BY carrier ORDER BY value DESC
    """,
    ("avg_delivery_days", "region"): """
        SELECT region AS label,
               ROUND(AVG(delivery_days)::numeric, 1) AS value
        FROM orders WHERE {where} AND delivery_days IS NOT NULL GROUP BY region ORDER BY value DESC
    """,
}

# Separate multi-series templates keyed by endpoint name
MULTI_SERIES_TEMPLATES: dict[str, str] = {
    "delivery_performance": """
        SELECT TO_CHAR(DATE_TRUNC('month', order_date), 'YYYY-MM') AS period,
               COUNT(*) FILTER (WHERE status = 'delivered') AS on_time,
               COUNT(*) FILTER (WHERE status = 'delayed')   AS delayed
        FROM orders WHERE {where}
        GROUP BY DATE_TRUNC('month', order_date)
        ORDER BY 1
    """,
    "region_breakdown": """
        SELECT region AS label,
               COUNT(*) AS order_count,
               ROUND(100.0 * SUM(is_delayed::int) / NULLIF(COUNT(*), 0), 1) AS delay_rate
        FROM orders WHERE {where}
        GROUP BY region ORDER BY order_count DESC
    """,
}


def _build_where(filters: DashboardFilters, params: dict) -> str:
    clauses = ["order_date BETWEEN :from_date AND :to_date"]
    if filters.carrier:
        clauses.append("carrier = :carrier")
        params["carrier"] = filters.carrier
    if filters.region:
        clauses.append("region = :region")
        params["region"] = filters.region
    if filters.category:
        clauses.append("product_category = :category")
        params["category"] = filters.category
    return " AND ".join(clauses)


async def _default_date_range(db: AsyncSession) -> tuple[date, date]:
    result = await db.execute(text("SELECT MIN(order_date), MAX(order_date) FROM orders"))
    min_d, max_d = result.one()
    return max_d - timedelta(days=_DEFAULT_WINDOW_DAYS), max_d


async def _resolve_filters(db: AsyncSession, filters: DashboardFilters) -> tuple[DashboardFilters, dict]:
    if not filters.from_date or not filters.to_date:
        from_d, to_d = await _default_date_range(db)
        filters = filters.model_copy(update={
            "from_date": filters.from_date or from_d,
            "to_date":   filters.to_date   or to_d,
        })
    params: dict = {"from_date": filters.from_date, "to_date": filters.to_date}
    return filters, params


async def run_kpi(db: AsyncSession, filters: DashboardFilters) -> KPIResponse:
    filters, params = await _resolve_filters(db, filters)
    where = _build_where(filters, params)

    # `where` contains only hardcoded clause strings (e.g. "carrier = :carrier") — never user values.
    # All user-supplied values are in `params` and passed as bind parameters to db.execute().
    sql = f"""
        SELECT
            COUNT(*)                                                                  AS total_orders,
            COUNT(*) FILTER (WHERE status = 'delivered')                             AS delivered_orders,
            COUNT(*) FILTER (WHERE status = 'delayed')                               AS delayed_orders,
            ROUND(
                100.0 * COUNT(*) FILTER (WHERE status = 'delivered') /
                NULLIF(COUNT(*) FILTER (WHERE status IN ('delivered','delayed')), 0), 1
            )                                                                        AS on_time_rate,
            ROUND(AVG(delivery_days) FILTER (WHERE delivery_days IS NOT NULL)::numeric, 1) AS avg_delivery_days,
            ROUND(SUM(order_value_usd)::numeric, 2)                                 AS total_order_value
        FROM orders WHERE {where}
    """
    row = (await db.execute(text(sql), params)).one()
    return KPIResponse(
        total_orders=row.total_orders or 0,
        delivered_orders=row.delivered_orders or 0,
        delayed_orders=row.delayed_orders or 0,
        on_time_rate=float(row.on_time_rate or 0),
        avg_delivery_days=float(row.avg_delivery_days or 0),
        total_order_value=float(row.total_order_value or 0),
    )


async def run_chart(
    db: AsyncSession,
    metric: str,
    group_by: str,
    filters: DashboardFilters,
) -> list[dict[str, Any]]:
    key = (metric, group_by)
    if key not in QUERY_TEMPLATES:
        raise ValueError(f"Unsupported metric/group_by combination: {key}")

    filters, params = await _resolve_filters(db, filters)
    where = _build_where(filters, params)
    sql = QUERY_TEMPLATES[key].format(where=where)

    rows = (await db.execute(text(sql), params)).mappings().all()
    return [dict(r) for r in rows]


async def run_multi_series(
    db: AsyncSession,
    endpoint: str,
    filters: DashboardFilters,
) -> list[dict[str, Any]]:
    if endpoint not in MULTI_SERIES_TEMPLATES:
        raise ValueError(f"Unknown multi-series endpoint: {endpoint}")

    filters, params = await _resolve_filters(db, filters)
    where = _build_where(filters, params)
    sql = MULTI_SERIES_TEMPLATES[endpoint].format(where=where)

    rows = (await db.execute(text(sql), params)).mappings().all()
    return [dict(r) for r in rows]
