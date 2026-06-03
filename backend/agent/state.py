from typing import TypedDict, Optional, Any


class AgentState(TypedDict):
    question:       str
    intent:         Optional[str]   # "analytics_query" | "forecast" | "clarify"
    tool_params:    Optional[dict]
    tool_result:    Optional[Any]
    chart_spec:     Optional[dict]
    answer:         Optional[str]
    explainability: Optional[dict]
    node_trace:     list[str]
