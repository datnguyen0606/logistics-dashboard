import json
import math
from typing import Literal

import anthropic
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from fastapi import HTTPException

from backend.config import settings
from backend.schemas.forecast import ForecastResponse, ForecastPeriod, ForecastProjection

_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
_MODEL  = "claude-sonnet-4-20250514"

# Allowlists — Claude's extracted params are validated before any SQL runs
_ALLOWED_METRICS = {
    "order_count", "delay_rate", "order_value", "avg_delivery_days", "quantity",
}
_ALLOWED_FILTER_COLS = {"carrier", "region", "product_category", "sku"}
_ALLOWED_PERIOD_UNITS = {"week", "month"}

_TIME_SERIES_SQL: dict[str, str] = {
    "order_count": """
        SELECT {trunc} AS period, COUNT(*)::float AS value
        FROM orders WHERE {where} GROUP BY {trunc} ORDER BY 1
    """,
    "delay_rate": """
        SELECT {trunc} AS period,
               ROUND(100.0 * SUM(is_delayed::int) / NULLIF(COUNT(*), 0), 1)::float AS value
        FROM orders WHERE {where} GROUP BY {trunc} ORDER BY 1
    """,
    "order_value": """
        SELECT {trunc} AS period, ROUND(SUM(order_value_usd)::numeric, 2)::float AS value
        FROM orders WHERE {where} GROUP BY {trunc} ORDER BY 1
    """,
    "avg_delivery_days": """
        SELECT {trunc} AS period,
               ROUND(AVG(delivery_days)::numeric, 1)::float AS value
        FROM orders WHERE {where} AND delivery_days IS NOT NULL GROUP BY {trunc} ORDER BY 1
    """,
    "quantity": """
        SELECT {trunc} AS period, SUM(quantity)::float AS value
        FROM orders WHERE {where} GROUP BY {trunc} ORDER BY 1
    """,
}

_EXTRACT_SYSTEM = f"""
You are a logistics data analyst. Given a forecast question, extract structured query parameters.

Available dataset columns: order_date, carrier, region, product_category, sku,
quantity, order_value_usd, delivery_days, is_delayed, status.

Allowed metrics: {sorted(_ALLOWED_METRICS)}
Allowed filter_col values: {sorted(_ALLOWED_FILTER_COLS)} (null = no filter, aggregate all)
Allowed period_unit values: week, month

Respond with JSON only — no prose, no markdown:
{{
  "metric":      "<metric>",
  "filter_col":  "<column name or null>",
  "filter_val":  "<value or null>",
  "periods":     <integer 1-12>,
  "period_unit": "week | month",
  "title":       "<short descriptive chart title>"
}}
"""

_FORECAST_SYSTEM = """
You are a quantitative forecasting assistant. Given a historical time series and a question,
forecast future periods.

Respond with JSON only — no prose, no markdown fences:
{
  "forecast": [
    {"period": "<label>", "value": <float>, "lower": <float>, "upper": <float>},
    ...
  ],
  "method":      "<one-line description of your forecasting approach>",
  "explanation": "<2-3 sentences on observed trend and forecast rationale>"
}

Rules:
- period labels must continue the same format as the input (YYYY-MM or YYYY-WNN)
- lower/upper represent an approximate 90% confidence interval around value
- for rate/percentage metrics keep values between 0 and 100
- all values must be non-negative
- return exactly the requested number of periods
"""


def _trunc_expr(period_unit: str) -> str:
    return "DATE_TRUNC('month', order_date)" if period_unit == "month" else "DATE_TRUNC('week', order_date)"


def _period_label(ts, period_unit: str) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m" if period_unit == "month" else "%Y-W%V")


async def _extract_params(question: str) -> dict:
    response = await _client.messages.create(
        model=_MODEL,
        max_tokens=256,
        system=_EXTRACT_SYSTEM,
        messages=[{"role": "user", "content": question}],
    )
    parsed = json.loads(response.content[0].text.strip())

    metric      = parsed.get("metric", "order_count")
    filter_col  = parsed.get("filter_col")
    period_unit = parsed.get("period_unit", "month")

    # Validate all values against allowlists before building any SQL
    if metric not in _ALLOWED_METRICS:
        metric = "order_count"
    if filter_col and filter_col not in _ALLOWED_FILTER_COLS:
        filter_col = None
    if period_unit not in _ALLOWED_PERIOD_UNITS:
        period_unit = "month"

    return {
        "metric":      metric,
        "filter_col":  filter_col,
        "filter_val":  parsed.get("filter_val"),
        "periods":     max(1, min(12, int(parsed.get("periods", 3)))),
        "period_unit": period_unit,
        "title":       parsed.get("title", "Forecast"),
    }


async def _fetch_series(db: AsyncSession, params: dict) -> list[ForecastPeriod]:
    trunc = _trunc_expr(params["period_unit"])
    where_clauses = ["order_date IS NOT NULL"]
    bind_params: dict = {}

    if params["filter_col"] and params["filter_val"]:
        where_clauses.append(f"{params['filter_col']} = :filter_val")
        bind_params["filter_val"] = params["filter_val"]

    where = " AND ".join(where_clauses)
    sql = _TIME_SERIES_SQL[params["metric"]].format(trunc=trunc, where=where)

    rows = (await db.execute(text(sql), bind_params)).all()
    if not rows:
        raise HTTPException(
            status_code=404,
            detail="No data found for the requested forecast. Check the filter values and try again.",
        )

    return [
        ForecastPeriod(period=_period_label(r.period, params["period_unit"]), quantity=float(r.value or 0))
        for r in rows
    ]


async def _llm_forecast(
    question: str,
    historical: list[ForecastPeriod],
    params: dict,
) -> tuple[list[ForecastProjection], str, str]:
    history_payload = [{"period": p.period, "value": p.quantity} for p in historical]
    filter_note = (
        f" for {params['filter_col']}={params['filter_val']}" if params.get("filter_val") else ""
    )
    user_message = (
        f'Forecast question: "{question}"\n\n'
        f"Historical {params['period_unit']}ly {params['metric']}{filter_note}:\n"
        f"{json.dumps(history_payload, indent=2)}\n\n"
        f"Produce {params['periods']} {params['period_unit']}(s) of forecast "
        f"continuing from {historical[-1].period}."
    )

    response = await _client.messages.create(
        model=_MODEL,
        max_tokens=1024,
        system=_FORECAST_SYSTEM,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw[raw.index("\n") + 1 : raw.rfind("```")]

    parsed = json.loads(raw)

    projections = [
        ForecastProjection(
            period=p["period"],
            quantity=max(0.0, round(float(p["value"]), 1)),
            lower=max(0.0,    round(float(p["lower"]),  1)),
            upper=max(0.0,    round(float(p["upper"]),  1)),
        )
        for p in parsed["forecast"][: params["periods"]]
    ]
    return projections, parsed.get("method", "llm_forecast"), parsed.get("explanation", "")


async def forecast_open(db: AsyncSession, question: str) -> ForecastResponse:
    params      = await _extract_params(question)
    historical  = await _fetch_series(db, params)
    projections, method, explanation = await _llm_forecast(question, historical, params)

    final_qty  = projections[-1].quantity
    safety_qty = math.ceil(final_qty * 1.15)
    recommendation = (
        f"Plan for ~{round(final_qty)} {params['metric']} in {projections[-1].period}. "
        f"Apply 15% safety buffer → target {safety_qty}."
    )

    return ForecastResponse(
        title=params["title"],
        historical=historical,
        forecast=projections,
        method=method,
        recommendation=recommendation,
        explanation=explanation,
    )
