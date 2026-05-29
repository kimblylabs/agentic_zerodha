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


# ── request / response models ──────────────────────────────────────────────────


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    thread_id: Optional[str] = None


class ActionDecision(BaseModel):
    approved: bool
    note: Optional[str] = None


# ── static routes ──────────────────────────────────────────────────────────────


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(settings.static_dir / "index.html")


# ── account status ─────────────────────────────────────────────────────────────


@app.get("/api/account/status", response_class=JSONResponse)
async def account_status() -> JSONResponse:
    try:
        return {
            "profile": trading_tools.get_profile(),
            "holdings": trading_tools.get_holdings(),
            "positions": trading_tools.get_positions(),
            "orders": trading_tools.get_orders(),
            "margins": trading_tools.get_margins(),
        }
    except Exception as e:
        tb = traceback.format_exc()
        logging.error(f"Error in /api/account/status: {e}\n{tb}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "type": type(e).__name__, "traceback": tb},
        )


# ── streaming chat ─────────────────────────────────────────────────────────────


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Server-Sent Events endpoint.
    Each event is a JSON object:
      { "type": "token",          "data": "hello" }
      { "type": "pending_action", "data": { ...PendingAction... } }
      { "type": "done" }
      { "type": "error",          "data": "message" }
    """
    thread_id = request.thread_id or str(uuid4())
    account_status = await trading_tools.get_account_status()

    async def event_generator():
        try:
            async for token in stream_response(request.message, account_status):
                if token.startswith("__PENDING_ACTION__:"):
                    raw = token[len("__PENDING_ACTION__:") :]
                    action = json.loads(raw)

                    # Register it so /api/actions picks it up
                    action_id = str(uuid4())
                    action["id"] = action_id
                    pa = PendingAction(**action)
                    pending_actions[action_id] = pa

                    payload = json.dumps(
                        {
                            "type": "pending_action",
                            "data": pa.model_dump(),
                        }
                    )
                    yield f"data: {payload}\n\n"
                else:
                    payload = json.dumps({"type": "token", "data": token})
                    yield f"data: {payload}\n\n"

            yield f"data: {json.dumps({'type': 'done', 'thread_id': thread_id})}\n\n"

        except Exception as e:
            logging.error(f"Stream error: {e}\n{traceback.format_exc()}")
            yield f"data: {json.dumps({'type': 'error', 'data': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering if behind proxy
        },
    )


# ── HITL actions ───────────────────────────────────────────────────────────────


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
        return {"status": "rejected", "message": f"{action.summary} was rejected."}

    # ── execute the approved action ────────────────────────────────────────────
    try:
        result = _execute_action(action)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    pending_actions.pop(action_id, None)
    return {
        "status": "executed",
        "message": f"{action.summary} was approved and submitted to Zerodha.",
        "result": result,
    }


def _execute_action(action: PendingAction) -> Any:
    """Dispatch a confirmed PendingAction to the correct trading tool."""
    args = action.arguments.copy()
    args.pop("raw_instruction", None)  # internal field, not a Kite param

    if action.name == "place_order":
        # Required Kite params: tradingsymbol, exchange, transaction_type,
        #                       quantity, order_type, product
        required = [
            "tradingsymbol",
            "exchange",
            "transaction_type",
            "quantity",
            "order_type",
            "product",
        ]
        missing = [k for k in required if k not in args]
        if missing:
            raise ValueError(f"Missing required order fields: {', '.join(missing)}")

        if args.get("order_type") == "MARKET" and "market_protection" not in args:
            args["market_protection"] = -1
        return trading_tools.place_order(**args)

    elif action.name == "cancel_order":
        order_id = args.get("order_id")
        if not order_id:
            raise ValueError("order_id is required to cancel an order")
        return trading_tools.cancel_order(order_id)

    elif action.name == "modify_order":
        order_id = args.pop("order_id", None)
        if not order_id:
            raise ValueError("order_id is required to modify an order")
        return trading_tools.modify_order(order_id, **args)

    else:
        raise ValueError(f"Unknown action: {action.name}")
