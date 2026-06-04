import json
import anthropic
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.state import AgentState
from backend.agent.tools import TOOL_SCHEMAS
from backend.schemas.query import AnalyticsToolParams, ForecastToolParams
from backend.config import settings

_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
_MODEL  = "claude-sonnet-4-20250514"

_SCHEMA_DESCRIPTION = """
Dataset: logistics orders table with columns:
order_id, client_id, order_date (DATE, 2025-01-01 to 2025-12-30), delivery_date,
carrier (DHL/FedEx/UPS/USPS/GLS/DPD/Royal Mail/LaserShip/OnTrac),
origin_city, destination_city,
status (delivered/delayed/in_transit/exception/canceled),
sku, product_category (PAPER/BOOK/CRAYON/PENCIL/MARKER/STICKER/BRUSH/PAINT),
quantity, unit_price_usd, order_value_usd, is_promo, promo_discount_pct,
region (UK/EU/US-C/US-E/US-W), warehouse,
delivery_days (integer, computed), is_delayed (boolean, computed).
"""

_INTERPRET_SYSTEM = f"""
You are a logistics data analyst assistant. Classify the user's question and pass it through.

{_SCHEMA_DESCRIPTION}

Intents:
- analytics_query: questions about current or historical logistics metrics, patterns, or breakdowns
- forecast: questions asking to predict, forecast, or project future values
- clarify: questions unrelated to logistics data or too ambiguous to answer

Respond with JSON only — no prose:
{{
  "intent": "analytics_query | forecast | clarify",
  "tool_params": {{"question": "<the user's question verbatim>"}}
}}

If intent is "clarify", set tool_params to null.
"""

_SUMMARIZE_SYSTEM = """
You are a logistics data analyst. Given query results, produce a concise, precise
natural-language answer. Then describe a chart spec as JSON.

Respond with a JSON object:
{
  "answer": "...",
  "chart_spec": { "type": "bar|line|pie|forecast", "title": "...", "x_key": "...", "y_keys": ["..."], "data": [...] },
  "recommendation": "..."  // only for forecast intent; leave null otherwise
}

Base every factual claim on the provided data. Never invent numbers.
"""


async def interpret_node(state: AgentState) -> dict:
    trace = list(state.get("node_trace", []))
    trace.append("interpret")

    response = await _client.messages.create(
        model=_MODEL,
        max_tokens=512,
        system=_INTERPRET_SYSTEM,
        messages=[{"role": "user", "content": state["question"]}],
    )
    raw = response.content[0].text.strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"intent": "clarify", "tool_params": None, "chart_hint": "table"}

    return {
        "intent":      parsed.get("intent", "clarify"),
        "tool_params": parsed.get("tool_params"),
        "node_trace":  trace,
    }


async def route_node(state: AgentState) -> dict:
    trace = list(state.get("node_trace", []))
    trace.append("route")
    return {"node_trace": trace}


async def execute_query_node(state: AgentState, db: AsyncSession) -> dict:
    from backend.services.analytics_service import run_query_open

    trace = list(state.get("node_trace", []))
    trace.append("execute_query")

    params = AnalyticsToolParams(**(state["tool_params"] or {}))
    result = await run_query_open(db, params.question)

    chart_spec = {
        "type":   result["chart_type"],
        "title":  result["title"],
        "x_key":  "label",
        "y_keys": ["value"],
        "data":   result["data"],
    }

    explainability = {
        "intent":    state.get("intent"),
        "tool_used": "query_tool",
        "filters":   {"question": params.question},
        "metric":    result["metric"],
        "group_by":  result["group_by"],
        "node_trace": trace + ["summarize"],
    }
    return {
        "tool_result":    result["data"],
        "chart_spec":     chart_spec,
        "explainability": explainability,
        "node_trace":     trace,
    }


async def execute_forecast_node(state: AgentState, db: AsyncSession) -> dict:
    from backend.services.forecast_service import forecast_open

    trace = list(state.get("node_trace", []))
    trace.append("execute_forecast")

    params = ForecastToolParams(**(state["tool_params"] or {}))
    result = await forecast_open(db, params.question)

    chart_data = [{"period": p.period, "historical": p.quantity} for p in result.historical]
    for proj in result.forecast:
        chart_data.append({
            "period":   proj.period,
            "forecast": proj.quantity,
            "ci_band":  round(proj.upper - proj.lower, 1),
        })
    chart_spec = {
        "type":   "forecast",
        "title":  result.title,
        "x_key":  "period",
        "y_keys": ["historical", "forecast"],
        "data":   chart_data,
    }

    explainability = {
        "intent":    state.get("intent"),
        "tool_used": "forecast_tool",
        "filters":   {"question": params.question},
        "metric":    "forecast",
        "group_by":  "period",
        "node_trace": trace + ["summarize"],
    }
    return {
        "tool_result":    result.model_dump(),
        "chart_spec":     chart_spec,
        "explainability": explainability,
        "node_trace":     trace,
    }


async def summarize_node(state: AgentState) -> dict:
    trace = list(state.get("node_trace", []))
    trace.append("summarize")

    intent = state.get("intent", "clarify")

    if intent == "clarify" or not state.get("tool_result"):
        return {
            "answer": (
                "I can only answer questions about this logistics dataset. "
                "Could you clarify what you'd like to know? For example: "
                "\"Which carrier has the highest delay rate?\" or "
                "\"Predict demand for BOOK next 3 months.\""
            ),
            "chart_spec": None,
            "node_trace": trace,
        }

    user_content = (
        f"Question: {state['question']}\n\n"
        f"Data: {json.dumps(state['tool_result'], default=str)}"
    )

    response = await _client.messages.create(
        model=_MODEL,
        max_tokens=1024,
        system=_SUMMARIZE_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    )
    raw = response.content[0].text.strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"answer": raw, "chart_spec": None}

    explainability = dict(state.get("explainability") or {})
    explainability["node_trace"] = trace

    # Prefer a chart_spec already built by an execute node (e.g. forecast);
    # fall back to Claude's generated spec for analytics queries.
    chart_spec = state.get("chart_spec") or parsed.get("chart_spec")

    return {
        "answer":        parsed.get("answer", ""),
        "chart_spec":    chart_spec,
        "explainability": explainability,
        "node_trace":    trace,
    }
