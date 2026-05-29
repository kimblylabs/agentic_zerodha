# Zerodha Agent

A LangGraph + LangChain + LangSmith-ready Zerodha account assistant with a browser dashboard, chat interface, MCP tool bridge, and human-in-the-loop approvals for account-affecting actions.

## Features

- FastAPI backend serving account status and chat APIs.
- LangGraph workflow that loads the account snapshot before responding.
- Configurable Zerodha MCP stdio client.
- LangSmith tracing environment support.
- Frontend dashboard for profile, margins, holdings, positions, orders, chat, and HITL approvals.
- Demo data mode so the UI runs before connecting a real Zerodha MCP server.

## Project Structure

```text
zerodha_agent/
├── app.py
├── graph/
│   ├── graph.py
│   └── state.py
├── mcp/
│   ├── client.py
│   └── tools.py
├── prompts/
│   └── system_prompt.py
├── config/
│   └── settings.py
├── static/
│   ├── app.js
│   ├── index.html
│   └── styles.css
├── .env
├── .env.example
├── requirements.txt
└── README.md
```

## Setup

Use Python 3.10 or newer for live Zerodha MCP mode. Demo mode can run without the `mcp` package, but it will not connect to a real MCP server.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r zerodha_agent/requirements.txt
uvicorn zerodha_agent.app:app --reload --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`.

## Configure Zerodha MCP

Edit `.env`:

```bash
ZERODHA_MCP_ENABLED=true
ZERODHA_MCP_TRANSPORT=stdio
ZERODHA_MCP_COMMAND="your-zerodha-mcp-server-command --with args"
```

If your MCP server exposes different tool names, update:

```bash
PROFILE_TOOL=get_profile
MARGINS_TOOL=get_margins
HOLDINGS_TOOL=get_holdings
POSITIONS_TOOL=get_positions
ORDERS_TOOL=get_orders
PLACE_ORDER_TOOL=place_order
CANCEL_ORDER_TOOL=cancel_order
MODIFY_ORDER_TOOL=modify_order
```

## LangSmith

Set these values in `.env` to trace LangChain and LangGraph runs:

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your_key
LANGSMITH_PROJECT=zerodha-agent
```

## HITL Flow

The agent never directly executes trading instructions from chat. If a user asks to buy, sell, place, cancel, or modify an order, the graph creates a pending action. The frontend shows the action in the HITL approvals panel. Only after the user presses `Approve` does the backend call the configured Zerodha MCP trading tool.
