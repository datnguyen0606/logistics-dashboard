from functools import partial
from langgraph.graph import StateGraph, END
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.state import AgentState
from backend.agent.nodes import (
    interpret_node,
    route_node,
    execute_query_node,
    execute_forecast_node,
    summarize_node,
)


def build_agent_graph(db: AsyncSession):
    """Build and compile the LangGraph agent. Called once per request with the DB session."""
    graph = StateGraph(AgentState)

    graph.add_node("interpret",         interpret_node)
    graph.add_node("route",             route_node)
    graph.add_node("execute_query",     partial(execute_query_node,     db=db))
    graph.add_node("execute_forecast",  partial(execute_forecast_node,  db=db))
    graph.add_node("summarize",         summarize_node)

    graph.set_entry_point("interpret")
    graph.add_edge("interpret", "route")

    graph.add_conditional_edges(
        "route",
        lambda s: s.get("intent", "clarify"),
        {
            "analytics_query": "execute_query",
            "forecast":        "execute_forecast",
            "clarify":         "summarize",
        },
    )

    graph.add_edge("execute_query",    "summarize")
    graph.add_edge("execute_forecast", "summarize")
    graph.add_edge("summarize",        END)

    return graph.compile()
