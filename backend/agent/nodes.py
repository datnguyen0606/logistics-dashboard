import json
import anthropic
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.state import AgentState
from backend.agent.tools import TOOL_SCHEMAS
from backend.schemas.query import AnalyticsToolParams, ForecastToolParams
from backend.schemas.dashboard import DashboardFilters
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
You are a logistics data analyst assistant. Your job is to interpret user questions
about logistics operations and produce structured parameters for data retrieval.

{_SCHEMA_DESCRIPTION}

Available tools:
{json.dumps(TOOL_SCHEMAS, indent=2)}

You MUST NEVER answer data questions from memory.
Always produce tool_params for computation.

Respond with a JSON object only — no prose. Format:
{{
  "intent": "analytics_query" | "forecast" | "clarify",
  "tool_params": {{ ... }},
  "chart_hint": "bar" | "line" | "pie" | "table"
}}

If the question is ambiguous or unrelated to logistics data, set intent to "clarify"
and leave tool_params as null.
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
    from backend.services.analytics_service import run_chart

    trace = list(state.get("node_trace", []))
    trace.append("execute_query")

    params = AnalyticsToolParams(**(state["tool_params"] or {}))
    filters = DashboardFilters(**(params.filters or {}))
    data = await run_chart(db, params.metric, params.group_by, filters)

    explainability = {
        "intent":    state.get("intent"),
        "tool_used": "query_tool",
        "filters":   params.filters,
        "metric":    params.metric,
        "group_by":  params.group_by,
        "node_trace": trace + ["summarize"],
    }
    return {"tool_result": data, "explainability": explainability, "node_trace": trace}


async def execute_forecast_node(state: AgentState, db: AsyncSession) -> dict:
    from backend.services.forecast_service import forecast_demand

    trace = list(state.get("node_trace", []))
    trace.append("execute_forecast")

    params = ForecastToolParams(**(state["tool_params"] or {}))
    result = await forecast_demand(db, params.target, params.target_type, params.periods, params.period_unit)

    explainability = {
        "intent":    state.get("intent"),
        "tool_used": "forecast_tool",
        "filters":   {"target": params.target, "target_type": params.target_type},
        "metric":    "quantity",
        "group_by":  params.period_unit,
        "node_trace": trace + ["summarize"],
    }
    return {"tool_result": result.model_dump(), "explainability": explainability, "node_trace": trace}


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

    return {
        "answer":        parsed.get("answer", ""),
        "chart_spec":    parsed.get("chart_spec"),
        "explainability": explainability,
        "node_trace":    trace,
    }
