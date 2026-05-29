from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from zerodha_agent.graph.state import AgentState, PendingAction
from zerodha_agent.tools import trading_tools
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
        risky_action = _extract_risky_action(user_message)

        if risky_action:
            state["pending_action"] = risky_action.model_dump()
            state["final_response"] = (
                "I prepared this account action and paused for your confirmation. "
                "Review the details in the approval panel before it is sent to Zerodha."
            )
            return state

        if os.getenv("OPENAI_API_KEY"):
            state["final_response"] = await _llm_response(
                user_message, state["account_status"]
            )
        else:
            state["final_response"] = _fallback_response(
                user_message, state["account_status"]
            )

        return state

    return node


async def _llm_response(user_message: str, account_status: dict[str, Any]) -> str:
    llm = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"), temperature=0.2)
    response = await llm.ainvoke(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"Account snapshot:\n{json.dumps(account_status, indent=2)}\n\n"
                    f"User message:\n{user_message}"
                )
            ),
        ]
    )
    return str(response.content)


def _fallback_response(user_message: str, account_status: dict[str, Any]) -> str:
    lowered = user_message.lower()
    if "holding" in lowered:
        holdings = account_status.get("holdings", [])
        if not holdings:
            return "I do not see any holdings in the current Zerodha snapshot."
        symbols = ", ".join(
            item.get("tradingsymbol", "Unknown") for item in holdings[:5]
        )
        return f"Your current holdings include {symbols}."
    if "margin" in lowered or "fund" in lowered:
        margins = account_status.get("margins", {})
        available = margins.get("available", {}).get("cash", "unavailable")
        return f"Available cash margin is {available}."
    return (
        "I can summarize account status, holdings, positions, margins, and orders. "
        "Set OPENAI_API_KEY for richer LangChain reasoning."
    )


def _extract_risky_action(message: str) -> Optional[PendingAction]:
    lowered = message.lower()
    if not any(keyword in lowered for keyword in TRADING_KEYWORDS):
        return None

    action_name = "place_order"
    if "cancel" in lowered:
        action_name = "cancel_order"
    elif "modify" in lowered:
        action_name = "modify_order"

    arguments: dict[str, Any] = {"raw_instruction": message}
    symbol_match = re.search(r"\b([A-Z]{2,12})\b", message)
    quantity_match = re.search(r"\b(\d+)\s*(?:share|shares|qty|quantity)?\b", lowered)
    side = "BUY" if "buy" in lowered else "SELL" if "sell" in lowered else None

    if symbol_match:
        arguments["tradingsymbol"] = symbol_match.group(1)
    if quantity_match:
        arguments["quantity"] = int(quantity_match.group(1))
    if side:
        arguments["transaction_type"] = side

    summary_parts = [action_name.replace("_", " ").title()]
    if side:
        summary_parts.append(side)
    if arguments.get("quantity"):
        summary_parts.append(str(arguments["quantity"]))
    if arguments.get("tradingsymbol"):
        summary_parts.append(arguments["tradingsymbol"])

    return PendingAction(
        name=action_name,
        arguments=arguments,
        summary=" ".join(summary_parts),
        risk="high",
    )
