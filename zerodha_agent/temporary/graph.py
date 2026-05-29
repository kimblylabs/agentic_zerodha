from __future__ import annotations

import datetime
import json
import os
import re
from typing import Any, AsyncGenerator, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from zerodha_agent.graph.state import AgentState, PendingAction
from zerodha_agent.prompts.system_prompt import SYSTEM_PROMPT

TRADING_KEYWORDS = ("buy", "sell", "place order", "cancel order", "modify order")


def build_graph(tools):
    workflow = StateGraph(AgentState)
    workflow.add_node("load_account", _load_account(tools))
    workflow.add_node("reason", _reason(tools))
    workflow.set_entry_point("load_account")
    workflow.add_edge("load_account", "reason")
    workflow.add_edge("reason", END)
    return workflow.compile()


def _load_account(tools):
    async def node(state: AgentState) -> AgentState:
        state["account_status"] = await tools.get_account_status()
        return state

    return node


def _reason(tools):
    async def node(state: AgentState) -> AgentState:
        user_message = state["messages"][-1]["content"]
        risky_action = _extract_risky_action(user_message, state["account_status"])

        if risky_action:
            state["pending_action"] = risky_action.model_dump()
            state["final_response"] = (
                "I've prepared this action for your review. "
                "Check the Approvals panel to confirm or reject before anything is sent to Zerodha."
            )
            return state

        if os.getenv("OPENAI_API_KEY"):
            # Collect full streamed response into final_response for non-streaming graph path
            chunks = []
            async for chunk in _llm_stream(user_message, state["account_status"]):
                chunks.append(chunk)
            state["final_response"] = "".join(chunks)
        else:
            state["final_response"] = _fallback_response(
                user_message, state["account_status"]
            )

        return state

    return node


def _json_safe(obj: Any) -> str:
    """JSON serializer that handles datetime/date objects from Kite API."""
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


async def _llm_stream(
    user_message: str, account_status: dict[str, Any]
) -> AsyncGenerator[str, None]:
    """Yield LLM response tokens one by one."""
    llm = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"), temperature=0.2)
    snapshot = json.dumps(account_status, indent=2, default=_json_safe)
    async for chunk in llm.astream(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"Account snapshot:\n{snapshot}\n\n"
                    f"User message:\n{user_message}"
                )
            ),
        ]
    ):
        if chunk.content:
            yield str(chunk.content)


async def stream_response(
    user_message: str, account_status: dict[str, Any]
) -> AsyncGenerator[str, None]:
    """
    Public entry point used by the SSE endpoint in app.py.
    Checks for trading intent first; if found, yields a JSON marker so
    the frontend knows to open the approval panel instead of streaming text.
    """
    risky_action = _extract_risky_action(user_message, account_status)
    if risky_action:
        # Signal to the SSE consumer that this is a pending action, not text
        yield "__PENDING_ACTION__:" + json.dumps(risky_action.model_dump())
        return

    if os.getenv("OPENAI_API_KEY"):
        async for token in _llm_stream(user_message, account_status):
            yield token
    else:
        yield _fallback_response(user_message, account_status)


def _fallback_response(user_message: str, account_status: dict[str, Any]) -> str:
    lowered = user_message.lower()
    if "holding" in lowered:
        holdings = account_status.get("holdings", [])
        if not holdings:
            return "I do not see any holdings in the current Zerodha snapshot."
        symbols = ", ".join(
            item.get("tradingsymbol", "Unknown") for item in holdings[:5]
        )
        return f"Your current holdings include: {symbols}."
    if "margin" in lowered or "fund" in lowered:
        available = (
            account_status.get("margins", {})
            .get("available", {})
            .get("cash", "unavailable")
        )
        return f"Available cash margin is {available}."
    if "order" in lowered:
        orders = account_status.get("orders", [])
        return (
            f"You have {len(orders)} order(s) on record."
            if orders
            else "No orders found."
        )
    if "position" in lowered:
        positions = account_status.get("positions", {})
        net = positions.get("net", []) if isinstance(positions, dict) else positions
        if not net:
            return "No open positions found."
        symbols = ", ".join(p.get("tradingsymbol", "?") for p in net[:5])
        return f"Open positions: {symbols}."
    return (
        "I can summarize account status, holdings, positions, margins, and orders. "
        "Set OPENAI_API_KEY for richer LangChain reasoning."
    )


def _extract_risky_action(
    message: str, account_status: dict[str, Any]
) -> Optional[PendingAction]:
    lowered = message.lower()
    if not any(kw in lowered for kw in TRADING_KEYWORDS):
        return None

    action_name = "place_order"
    if "cancel" in lowered:
        action_name = "cancel_order"
    elif "modify" in lowered:
        action_name = "modify_order"

    arguments: dict[str, Any] = {"raw_instruction": message}
    symbol_match = re.search(r"\b([A-Z]{2,20})\b", message)
    quantity_match = re.search(r"\b(\d+)\s*(?:share|shares|qty|quantity)?\b", lowered)
    price_match = re.search(
        r"(?:at|@|price|limit)\s*(?:rs\.?|inr)?\s*(\d+(?:\.\d+)?)", lowered
    )
    side = "BUY" if "buy" in lowered else "SELL" if "sell" in lowered else None

    order_type = "MARKET"
    if price_match or "limit" in lowered:
        order_type = "LIMIT"

    if symbol_match:
        arguments["tradingsymbol"] = symbol_match.group(1)
    if quantity_match:
        arguments["quantity"] = int(quantity_match.group(1))
    elif "all" in lowered and side == "SELL":
        resolved_quantity = _infer_holding_quantity(
            account_status, arguments.get("tradingsymbol")
        )
        if resolved_quantity:
            arguments["quantity"] = resolved_quantity
    if price_match:
        arguments["price"] = float(price_match.group(1))
    if side:
        arguments["transaction_type"] = side

    arguments["order_type"] = order_type
    arguments["exchange"] = "NSE"
    arguments["product"] = "CNC"  # default; user can override
    if order_type == "MARKET":
        arguments["market_protection"] = -1

    summary_parts = [action_name.replace("_", " ").title()]
    if side:
        summary_parts.append(side)
    if arguments.get("quantity"):
        summary_parts.append(str(arguments["quantity"]))
    if arguments.get("tradingsymbol"):
        summary_parts.append(arguments["tradingsymbol"])
    if order_type == "LIMIT" and arguments.get("price"):
        summary_parts.append(f"@ ₹{arguments['price']}")

    return PendingAction(
        name=action_name,
        arguments=arguments,
        summary=" ".join(summary_parts),
        risk="high",
    )


def _infer_holding_quantity(
    account_status: dict[str, Any], tradingsymbol: Any
) -> Optional[int]:
    if not tradingsymbol:
        return None

    target_symbol = str(tradingsymbol).upper()
    holdings = account_status.get("holdings", [])
    for holding in holdings:
        symbol = str(holding.get("tradingsymbol", "")).upper()
        if symbol != target_symbol:
            continue

        quantity = holding.get("quantity")
        if quantity is None:
            return None
        try:
            return int(quantity)
        except (TypeError, ValueError):
            return None

    return None
