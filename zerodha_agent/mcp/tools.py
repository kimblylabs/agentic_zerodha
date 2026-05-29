from __future__ import annotations

import asyncio
from typing import Any

from zerodha_agent.mcp.client import ZerodhaMCPClient


class ZerodhaTools:
    def __init__(self, client: ZerodhaMCPClient):
        self.client = client
        self.settings = client.settings

    async def get_account_status(self) -> dict[str, Any]:
        profile, margins, holdings, positions, orders = await asyncio.gather(
            self.client.call_tool(self.settings.profile_tool),
            self.client.call_tool(self.settings.margins_tool),
            self.client.call_tool(self.settings.holdings_tool),
            self.client.call_tool(self.settings.positions_tool),
            self.client.call_tool(self.settings.orders_tool),
        )
        return {
            "profile": profile,
            "margins": margins,
            "holdings": holdings,
            "positions": positions,
            "orders": orders,
            "mcp_enabled": self.settings.zerodha_mcp_enabled,
        }

    async def execute_trading_action(self, action_name: str, arguments: dict[str, Any]) -> Any:
        tool_name = {
            "place_order": self.settings.place_order_tool,
            "cancel_order": self.settings.cancel_order_tool,
            "modify_order": self.settings.modify_order_tool,
        }.get(action_name)
        if not tool_name:
            raise ValueError(f"Unsupported action: {action_name}")
        return await self.client.call_tool(tool_name, arguments)
