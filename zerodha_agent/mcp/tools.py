from __future__ import annotations

import asyncio
from typing import Any

from zerodha_agent.mcp.client import ZerodhaMCPClient


class ZerodhaTools:
    def __init__(self, client: ZerodhaMCPClient):
        self.client = client
        self.settings = client.settings

    async def _login(self) -> None:
        await self.client.call_tool(
            self.settings.login_tool,
            {
                "api_key": self.settings.zerodha_api_key,
                "access_token": self.settings.zerodha_access_token,
            },
        )

    async def get_account_status(self) -> dict[str, Any]:
        if self.settings.zerodha_mcp_enabled:
            await self._login()

        results = await asyncio.gather(
            self.client.call_tool(self.settings.profile_tool),
            self.client.call_tool(self.settings.margins_tool),
            self.client.call_tool(self.settings.holdings_tool),
            self.client.call_tool(self.settings.positions_tool),
            self.client.call_tool(self.settings.orders_tool),
            return_exceptions=True,
        )

        def safe(val: Any, fallback: Any) -> Any:
            return fallback if isinstance(val, BaseException) else val

        profile, margins, holdings, positions, orders = results
        return {
            "profile":     safe(profile,   {}),
            "margins":     safe(margins,   {}),
            "holdings":    safe(holdings,  []),
            "positions":   safe(positions, []),
            "orders":      safe(orders,    []),
            "mcp_enabled": self.settings.zerodha_mcp_enabled,
        }

    async def execute_trading_action(self, action_name: str, arguments: dict[str, Any]) -> Any:
        if self.settings.zerodha_mcp_enabled:
            await self._login()

        tool_name = {
            "place_order":  self.settings.place_order_tool,
            "cancel_order": self.settings.cancel_order_tool,
            "modify_order": self.settings.modify_order_tool,
        }.get(action_name)
        if not tool_name:
            raise ValueError(f"Unsupported action: {action_name}")
        return await self.client.call_tool(tool_name, arguments)
