from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from zerodha_agent.config.settings import get_settings
from zerodha_agent.graph.graph import build_graph
from zerodha_agent.graph.state import PendingAction
from zerodha_agent.mcp.client import ZerodhaMCPClient
from zerodha_agent.mcp.tools import ZerodhaTools

settings = get_settings()
mcp_client = ZerodhaMCPClient(settings)
tools = ZerodhaTools(mcp_client)
agent_graph = build_graph(tools)
pending_actions: dict[str, PendingAction] = {}

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    thread_id: Optional[str] = None


class ActionDecision(BaseModel):
    approved: bool
    note: Optional[str] = None


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(settings.static_dir / "index.html")


@app.get("/api/account/status")
async def account_status() -> Any:
    try:
        status = await tools.get_account_status()
        status["updated_at"] = datetime.now(timezone.utc).isoformat()
        return status
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logging.error(f"Error in /api/account/status: {e}\n{tb}")
        return {"error": str(e), "type": type(e).__name__, "traceback": tb}


@app.post("/api/chat")
async def chat(request: ChatRequest) -> dict[str, Any]:
    thread_id = request.thread_id or str(uuid4())
    result = await agent_graph.ainvoke(
        {
            "messages": [{"role": "user", "content": request.message}],
            "thread_id": thread_id,
            "account_status": {},
            "pending_action": None,
            "final_response": "",
        }
    )

    pending_action = result.get("pending_action")
    response: dict[str, Any] = {
        "thread_id": thread_id,
        "message": result.get("final_response", ""),
        "pending_action": None,
    }

    if pending_action:
        action_id = str(uuid4())
        pending_action["id"] = action_id
        pending_actions[action_id] = PendingAction(**pending_action)
        response["pending_action"] = pending_actions[action_id].model_dump()

    return response


@app.get("/api/actions")
async def list_actions() -> list[dict[str, Any]]:
    return [action.model_dump() for action in pending_actions.values()]


@app.post("/api/actions/{action_id}")
async def decide_action(action_id: str, decision: ActionDecision) -> dict[str, Any]:
    action = pending_actions.get(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    if not decision.approved:
        pending_actions.pop(action_id, None)
        return {
            "status": "rejected",
            "message": f"{action.name} was rejected by the user.",
        }

    result = await tools.execute_trading_action(action.name, action.arguments)
    pending_actions.pop(action_id, None)
    return {
        "status": "executed",
        "message": f"{action.name} was approved and submitted.",
        "result": result,
    }
