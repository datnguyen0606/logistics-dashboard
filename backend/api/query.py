import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.connection import get_db
from backend.schemas.query import QueryRequest
from backend.agent.graph import build_agent_graph
from backend.agent.state import AgentState

router = APIRouter(tags=["query"])


async def _stream_agent(question: str, db: AsyncSession):
    state: AgentState = {
        "question":       question,
        "intent":         None,
        "tool_params":    None,
        "tool_result":    None,
        "chart_spec":     None,
        "answer":         None,
        "explainability": None,
        "node_trace":     [],
    }

    agent = build_agent_graph(db)
    final_state = None

    async for event in agent.astream_events(state, version="v2"):
        kind = event.get("event")
        if (
            kind == "on_chat_model_stream"
            and event.get("metadata", {}).get("langgraph_node") == "summarize"
        ):
            chunk = event.get("data", {}).get("chunk")
            if chunk and hasattr(chunk, "content"):
                for block in (chunk.content if isinstance(chunk.content, list) else [chunk.content]):
                    text = block.text if hasattr(block, "text") else str(block)
                    if text:
                        yield f"data: {json.dumps({'type': 'token', 'content': text})}\n\n"

        if kind == "on_chain_end" and event.get("name") == "LangGraph":
            final_state = event.get("data", {}).get("output")

    if final_state:
        complete = {
            "type":            "complete",
            "answer":          final_state.get("answer", ""),
            "chart":           final_state.get("chart_spec"),
            "explainability":  final_state.get("explainability"),
            "underlying_data": (
                final_state.get("tool_result")
                if isinstance(final_state.get("tool_result"), list)
                else final_state.get("chart_spec", {}).get("data", [])
            ),
        }
        yield f"data: {json.dumps(complete, default=str)}\n\n"

    yield "data: [DONE]\n\n"


@router.post("/query/ask")
async def ask_query(
    body: QueryRequest,
    db: AsyncSession = Depends(get_db),
):
    if not body.question.strip():
        raise HTTPException(status_code=422, detail="question must not be empty")

    return StreamingResponse(
        _stream_agent(body.question, db),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
