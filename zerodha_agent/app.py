from __future__ import annotations

import json
import logging
import traceback
from typing import Any, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from zerodha_agent.config.settings import get_settings
from zerodha_agent.graph.graph import build_graph, stream_response
from zerodha_agent.graph.state import PendingAction
from zerodha_agent.tools import trading_tools

settings = get_settings()
agent_graph = build_graph(trading_tools)
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


@app.get("/api/account/status", response_class=JSONResponse)
async def account_status() -> JSONResponse:
    try:
        return await trading_tools.get_account_status()
    except Exception as e:
        tb = traceback.format_exc()
        logging.error(f"Error in /api/account/status: {e}\n{tb}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "type": type(e).__name__, "traceback": tb},
        )


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


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    thread_id = request.thread_id or str(uuid4())
    account_status = await trading_tools.get_account_status()

    async def event_generator():
        try:
            async for token in stream_response(request.message, account_status):
                if token.startswith("__PENDING_ACTION__:"):
                    raw = token[len("__PENDING_ACTION__:") :]
                    pending_action = json.loads(raw)
                    action_id = str(uuid4())
                    pending_action["id"] = action_id
                    pending_actions[action_id] = PendingAction(**pending_action)
                    pending_payload = pending_actions[action_id].model_dump()
                    pending_payload["thread_id"] = thread_id
                    yield f"data: {json.dumps({'type': 'pending_action', 'data': pending_payload})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'token', 'data': token})}\n\n"

            yield f"data: {json.dumps({'type': 'done', 'thread_id': thread_id})}\n\n"
        except Exception as e:
            logging.error(f"Error in /api/chat/stream: {e}\n{traceback.format_exc()}")
            yield f"data: {json.dumps({'type': 'error', 'data': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


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
            "message": f"{action.name} was rejected.",
        }

    # Execute the trading action via the correct tool
    action_map = {
        "place_order": lambda: _execute_place_order(action.arguments),
        "cancel_order": lambda: trading_tools.cancel_order(
            action.arguments.get("order_id")
        ),
        "modify_order": lambda: trading_tools.modify_order(
            action.arguments.get("order_id"),
            **{k: v for k, v in action.arguments.items() if k != "order_id"},
        ),
    }

    handler = action_map.get(action.name)
    if not handler:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action.name}")

    try:
        result = handler()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    pending_actions.pop(action_id, None)
    message = f"{action.name} was approved and submitted."
    if action.name == "place_order":
        order_id = _extract_order_id(result)
        message = (
            f"{action.name} was approved and submitted to Zerodha. Order ID: {order_id}"
        )
    return {
        "status": "executed",
        "message": message,
        "result": result,
    }


def _execute_place_order(arguments: dict[str, Any]) -> Any:
    order_args = {k: v for k, v in arguments.items() if k != "raw_instruction"}
    required = [
        "tradingsymbol",
        "exchange",
        "transaction_type",
        "quantity",
        "order_type",
        "product",
    ]
    missing = [key for key in required if key not in order_args]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required order fields: {', '.join(missing)}",
        )

    if (
        order_args.get("order_type") == "MARKET"
        and "market_protection" not in order_args
    ):
        order_args["market_protection"] = -1

    result = trading_tools.place_order(**order_args)

    if isinstance(result, dict) and result.get("error"):
        raise HTTPException(
            status_code=502, detail=f"Kite order rejected: {result['error']}"
        )

    order_id = _extract_order_id(result)
    if not order_id:
        raise HTTPException(
            status_code=502,
            detail=f"Kite returned an unexpected order response: {result!r}",
        )

    return {"order_id": order_id, "submitted": True, "result": result}


def _extract_order_id(result: Any) -> str | None:
    if isinstance(result, str):
        return result.strip() or None
    if isinstance(result, dict):
        value = (
            result.get("order_id")
            or result.get("data", {}).get("order_id")
            or result.get("result", {}).get("order_id")
        )
        return str(value) if value else None
    if isinstance(result, (list, tuple)) and result:
        return _extract_order_id(result[0])
    return None


def _chunk_text(text: str, chunk_size: int) -> list[str]:
    if not text:
        return []
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
