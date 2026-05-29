from __future__ import annotations

import asyncio
import json
from contextlib import AsyncExitStack
from typing import Any, Optional

from zerodha_agent.config.settings import Settings


class ZerodhaMCPClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._session = None
        self._stack = None
        self._lock = asyncio.Lock()

    async def _get_session(self):
        if self._session is not None:
            return self._session

        async with self._lock:
            if self._session is not None:
                return self._session

            command_parts = self.settings.mcp_command_parts
            if not command_parts:
                raise RuntimeError("ZERODHA_MCP_COMMAND is required when MCP is enabled.")

            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            import sys

            command = sys.executable if command_parts[0] in {"python", "python3"} else command_parts[0]
            params = StdioServerParameters(command=command, args=command_parts[1:])

            self._stack = AsyncExitStack()
            read, write = await self._stack.enter_async_context(stdio_client(params))
            self._session = await self._stack.enter_async_context(ClientSession(read, write))
            await self._session.initialize()
            return self._session

    async def call_tool(self, tool_name: str, arguments: Optional[dict[str, Any]] = None) -> Any:
        if not self.settings.zerodha_mcp_enabled:
            return self._demo_response(tool_name, arguments or {})

        session = await self._get_session()
        result = await session.call_tool(tool_name, arguments or {})
        return self._normalize_content(result.content)

    async def close(self):
        if self._stack:
            await self._stack.aclose()
            self._session = None
            self._stack = None

    def _normalize_content(self, content: Any) -> Any:
        if not content:
            return {}
        values = []
        for item in content:
            text = getattr(item, "text", None)
            if text is None:
                values.append(item.model_dump() if hasattr(item, "model_dump") else item)
                continue
            try:
                values.append(json.loads(text))
            except json.JSONDecodeError:
                values.append(text)
        return values[0] if len(values) == 1 else values

    def _demo_response(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        demo = {
            self.settings.profile_tool: {"user_name": "Demo Zerodha User", "email": "demo@example.com", "broker": "ZERODHA"},
            self.settings.margins_tool: {"available": {"cash": 125000.0, "collateral": 25000.0}, "utilised": {"debits": 34000.0, "span": 0.0}},
            self.settings.holdings_tool: [{"tradingsymbol": "INFY", "quantity": 10, "average_price": 1420.5, "last_price": 1512.8}, {"tradingsymbol": "TCS", "quantity": 4, "average_price": 3520.0, "last_price": 3661.2}],
            self.settings.positions_tool: [{"tradingsymbol": "NIFTY26MAYFUT", "quantity": 50, "pnl": 2850.0}],
            self.settings.orders_tool: [{"order_id": "demo-001", "tradingsymbol": "INFY", "status": "COMPLETE", "quantity": 10}],
            self.settings.place_order_tool: {"status": "mock_submitted", "arguments": arguments},
            self.settings.cancel_order_tool: {"status": "mock_cancelled", "arguments": arguments},
            self.settings.modify_order_tool: {"status": "mock_modified", "arguments": arguments},
        }
        return demo.get(tool_name, {"status": "mock_ok", "tool": tool_name, "arguments": arguments})
