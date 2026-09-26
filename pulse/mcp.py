"""Minimal MCP server core: JSON-RPC 2.0 over HTTP (stateless, JSON responses)."""

import json
from typing import Optional

from .registry import TOOLS, ToolError

SUPPORTED_PROTOCOLS = ["2025-06-18", "2025-03-26", "2024-11-05"]


def rpc_error(req_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


async def handle_rpc(msg: dict) -> Optional[dict]:
    if "id" not in msg:
        return None  # notification
    req_id, method, params = msg["id"], msg.get("method"), msg.get("params") or {}

    if method == "initialize":
        asked = params.get("protocolVersion")
        version = asked if asked in SUPPORTED_PROTOCOLS else SUPPORTED_PROTOCOLS[0]
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": version,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "pulse-mcp", "version": "3.0"},
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": [t["spec"] for t in TOOLS.values()]}}
    if method == "tools/call":
        entry = TOOLS.get(params.get("name"))
        if not entry:
            return rpc_error(req_id, -32602, f"Unknown tool: {params.get('name')}")
        args = params.get("arguments") or {}
        try:
            missing = [k for k in entry["spec"]["inputSchema"]["required"] if args.get(k) in (None, "")]
            if missing:
                raise ToolError(f"Missing required argument(s): {', '.join(missing)}")
            result = await entry["fn"](args)
            text, is_error = json.dumps(result, ensure_ascii=False, indent=2), False
        except ToolError as e:
            text, is_error = str(e), True
        except Exception as e:  # noqa: BLE001
            text, is_error = f"{type(e).__name__}: {e}", True
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"content": [{"type": "text", "text": text}], "isError": is_error},
        }
    return rpc_error(req_id, -32601, f"Method not found: {method}")
