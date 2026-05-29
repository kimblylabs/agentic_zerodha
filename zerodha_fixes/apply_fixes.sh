#!/usr/bin/env bash
# Run this from the ROOT of your repo (where zerodha_agent/ lives).
# Usage:  bash apply_fixes.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "→ Copying fixed files..."
cp "$SCRIPT_DIR/zerodha_agent/mcp/tools.py"    zerodha_agent/mcp/tools.py
cp "$SCRIPT_DIR/zerodha_agent/app.py"           zerodha_agent/app.py
cp "$SCRIPT_DIR/zerodha_agent/static/app.js"    zerodha_agent/static/app.js

echo "→ Staging changes..."
git add zerodha_agent/mcp/tools.py zerodha_agent/app.py zerodha_agent/static/app.js

echo "→ Committing..."
git commit -m "fix: harden account status endpoint and frontend error handling

- mcp/tools.py: use return_exceptions=True in asyncio.gather so a single
  failing MCP call no longer crashes the entire /api/account/status response
- app.py: fix return type annotation to Any (was dict[str, Any], caused FastAPI
  validation errors on error-dict responses); add /favicon.ico 204 route;
  remove stray debug print statement
- static/app.js: wrap loadStatus/loadApprovals/sendMessage/decideApproval in
  try/catch so a single network failure no longer crashes the whole UI; show
  a readable inline error when the status endpoint returns an error object"

echo "✓ Done. Push with:  git push"
