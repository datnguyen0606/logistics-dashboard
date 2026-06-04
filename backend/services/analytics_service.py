import json
from datetime import date, timedelta
from typing import Any

import anthropic
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from backend.config import settings
from backend.schemas.dashboard import DashboardFilters, KPIResponse, ChartResponse

_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
_MODEL  = "claude-sonnet-4-20250514"

# Allowlists for open-ended queries — all f-string interpolated values come from here, never from user input
_METRIC_EXPRS: dict[str, str] = {
    "order_count":       "COUNT(*)",
    "delay_rate":        "ROUND(100.0 * SUM(is_delayed::int) / NULLIF(COUNT(*), 0), 1)",
    "on_time_rate":      "ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'delivered') / NULLIF(COUNT(*), 0), 1)",
    "avg_delivery_days": "ROUND(AVG(delivery_days) FILTER (WHERE delivery_days IS NOT NULL)::numeric, 1)",
    "total_order_value": "ROUND(SUM(order_value_usd)::numeric, 2)",
    "total_quantity":    "SUM(quantity)::float",
    "avg_order_value":   "ROUND(AVG(order_value_usd)::numeric, 2)",
    "canceled_rate":     "ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'canceled') / NULLIF(COUNT(*), 0), 1)",
}

_GROUP_BY_COLS: set[str] = {"carrier", "region", "product_category", "sku", "warehouse", "status"}

_TIME_GROUP_BY: dict[str, tuple[str, str]] = {
    "month": (
        "TO_CHAR(DATE_TRUNC('month', order_date), 'YYYY-MM')",
        "DATE_TRUNC('month', order_date)",
    ),
    "week": (
        "TO_CHAR(DATE_TRUNC('week', order_date), 'YYYY-\"W\"IW')",
        "DATE_TRUNC('week', order_date)",
    ),
}

_ALLOWED_CHART_TYPES: set[str] = {"bar", "line", "pie"}

_EXTRACT_QUERY_SYSTEM = f"""
You are a logistics data analyst. Given an analytics question, extract structured query parameters.

Dataset: orders table — order_date (2025-01-01 to 2025-12-30),
carrier (DHL/FedEx/UPS/USPS/GLS/DPD/Royal Mail/LaserShip/OnTrac),
region (UK/EU/US-C/US-E/US-W),
product_category (PAPER/BOOK/CRAYON/PENCIL/MARKER/STICKER/BRUSH/PAINT),
sku, warehouse, status (delivered/delayed/in_transit/exception/canceled),
quantity, order_value_usd, delivery_days, is_delayed.

Allowed metrics: {sorted(_METRIC_EXPRS)}
Allowed group_by: {sorted(_GROUP_BY_COLS) + sorted(_TIME_GROUP_BY)}
Optional filters: from_date (YYYY-MM-DD), to_date (YYYY-MM-DD), carrier, region, category

Respond with JSON only — no prose, no markdown:
{{
  "metric":     "<metric>",
  "group_by":   "<dimension>",
  "filters":    {{"from_date": null, "to_date": null, "carrier": null, "region": null, "category": null}},
  "chart_type": "bar | line | pie",
  "title":      "<short descriptive chart title>"
}}
"""

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


async def _extract_query_params(question: str) -> dict:
    response = await _client.messages.create(
        model=_MODEL,
        max_tokens=256,
        system=_EXTRACT_QUERY_SYSTEM,
        messages=[{"role": "user", "content": question}],
    )
    parsed = json.loads(response.content[0].text.strip())

    metric     = parsed.get("metric", "order_count")
    group_by   = parsed.get("group_by", "carrier")
    chart_type = parsed.get("chart_type", "bar")

    if metric not in _METRIC_EXPRS:
        metric = "order_count"
    if group_by not in _GROUP_BY_COLS and group_by not in _TIME_GROUP_BY:
        group_by = "carrier"
    if chart_type not in _ALLOWED_CHART_TYPES:
        chart_type = "bar" if group_by not in _TIME_GROUP_BY else "line"

    raw_filters = parsed.get("filters") or {}
    clean_filters = {
        k: v for k, v in raw_filters.items()
        if k in {"from_date", "to_date", "carrier", "region", "category"} and v
    }

    return {
        "metric":     metric,
        "group_by":   group_by,
        "chart_type": chart_type,
        "filters":    clean_filters,
        "title":      parsed.get("title", "Analytics"),
    }


async def run_query_open(db: AsyncSession, question: str) -> dict[str, Any]:
    params = await _extract_query_params(question)

    metric_expr = _METRIC_EXPRS[params["metric"]]
    group_by    = params["group_by"]

    if group_by in _TIME_GROUP_BY:
        select_label, group_expr = _TIME_GROUP_BY[group_by]
        order_clause = f"ORDER BY {group_expr}"
    else:
        select_label = group_by
        group_expr   = group_by
        order_clause = "ORDER BY value DESC"

    filters = DashboardFilters(
        from_date=params["filters"].get("from_date"),
        to_date=params["filters"].get("to_date"),
        carrier=params["filters"].get("carrier"),
        region=params["filters"].get("region"),
        category=params["filters"].get("category"),
    )
    filters, bind_params = await _resolve_filters(db, filters)
    where = _build_where(filters, bind_params)

    # select_label, metric_expr, group_expr, order_clause are all from allowlists — never user values
    sql = f"""
        SELECT {select_label} AS label,
               {metric_expr}  AS value
        FROM orders
        WHERE {where}
        GROUP BY {group_expr}
        {order_clause}
    """

    rows = (await db.execute(text(sql), bind_params)).mappings().all()

    return {
        "data":       [dict(r) for r in rows],
        "title":      params["title"],
        "chart_type": params["chart_type"],
        "metric":     params["metric"],
        "group_by":   group_by,
    }
