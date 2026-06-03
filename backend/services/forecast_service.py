import math
from typing import Literal
import numpy as np
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from fastapi import HTTPException

from backend.schemas.forecast import ForecastResponse, ForecastPeriod, ForecastProjection

_HISTORICAL_SQL = """
    SELECT
        {trunc_expr} AS period,
        SUM(quantity)::float AS quantity
    FROM orders
    WHERE {filter_col} = :target
    GROUP BY {trunc_expr}
    ORDER BY 1
"""


def _trunc_expr(period_unit: str) -> str:
    if period_unit == "month":
        return "DATE_TRUNC('month', order_date)"
    return "DATE_TRUNC('week', order_date)"


def _period_label(ts, period_unit: str) -> str:
    if period_unit == "month":
        return pd.Timestamp(ts).strftime("%Y-%m")
    return pd.Timestamp(ts).strftime("%Y-W%V")


def _next_period_label(last_ts, step: int, period_unit: str) -> str:
    ts = pd.Timestamp(last_ts)
    if period_unit == "month":
        month = ts.month + step
        year  = ts.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        return f"{year}-{month:02d}"
    return (ts + pd.DateOffset(weeks=step)).strftime("%Y-W%V")


async def forecast_demand(
    db: AsyncSession,
    target: str,
    target_type: Literal["sku", "category"],
    periods: int,
    period_unit: Literal["week", "month"],
) -> ForecastResponse:
    filter_col = "sku" if target_type == "sku" else "product_category"
    trunc = _trunc_expr(period_unit)
    sql = _HISTORICAL_SQL.format(trunc_expr=trunc, filter_col=filter_col)

    rows = (await db.execute(text(sql), {"target": target})).all()
    if not rows:
        raise HTTPException(status_code=404, detail=f"No data found for {target_type} '{target}'")

    historical = [
        ForecastPeriod(period=_period_label(r.period, period_unit), quantity=r.quantity)
        for r in rows
    ]
    series = pd.Series([r.quantity for r in rows], dtype=float)
    n = len(series)

    if n >= 6:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        model  = ExponentialSmoothing(series, trend="add", initialization_method="estimated").fit()
        fc     = model.forecast(periods)
        method = "exponential_smoothing"

        # Approximate 95% CI from residual standard deviation
        residuals = series.values - model.fittedvalues.values
        sigma = math.sqrt(float(np.mean(residuals ** 2)))
        margin = 1.96 * sigma

        explanation = (
            f"Applied Holt-Winters additive trend. "
            f"Alpha={model.params.get('smoothing_level', 'n/a'):.3f}. "
            f"Confidence intervals: ±1.96 × residual std dev ({sigma:.1f} units). "
            f"Dataset has {n} {'months' if period_unit == 'month' else 'weeks'} of history — "
            f"no seasonal component fitted (insufficient history)."
        )
    else:
        x      = np.arange(n)
        coeffs = np.polyfit(x, series.values, 1)
        fc_x   = np.arange(n, n + periods)
        fc     = pd.Series(np.polyval(coeffs, fc_x))
        method = "linear_regression_fallback"

        slope = coeffs[0]
        sigma = float(np.std(series.values - np.polyval(coeffs, x)))
        margin = 1.96 * sigma

        explanation = (
            f"Insufficient history for exponential smoothing ({n} data points found). "
            f"Applied linear regression fallback (slope: {slope:.1f} units/period). "
            f"Forecast accuracy is limited. CI: ±1.96 × residual std dev ({sigma:.1f} units)."
        )

    last_ts = rows[-1].period
    forecast_out = [
        ForecastProjection(
            period=_next_period_label(last_ts, i + 1, period_unit),
            quantity=round(float(fc.iloc[i]), 1),
            lower=round(float(fc.iloc[i]) - margin, 1),
            upper=round(float(fc.iloc[i]) + margin, 1),
        )
        for i in range(periods)
    ]

    final_qty = forecast_out[-1].quantity
    safety_qty = math.ceil(final_qty * 1.15)
    final_period = forecast_out[-1].period
    recommendation = (
        f"Plan for ~{round(final_qty)} units in {final_period}. "
        f"Apply 15% safety stock → order {safety_qty} units."
    )

    return ForecastResponse(
        historical=historical,
        forecast=forecast_out,
        method=method,
        recommendation=recommendation,
        explanation=explanation,
    )
