from __future__ import annotations

from typing import Any, Literal, Optional, TypedDict

from pydantic import BaseModel, Field


class PendingAction(BaseModel):
    id: Optional[str] = None
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    summary: str
    risk: Literal["low", "medium", "high"] = "high"


class AgentState(TypedDict):
    messages: list[dict[str, str]]
    thread_id: str
    account_status: dict[str, Any]
    pending_action: Optional[dict[str, Any]]
    final_response: str
