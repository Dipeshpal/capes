"""MCP server core: JSON-RPC 2.0 over HTTP (stateless, JSON responses).

Every tool call passes through here, so this is where arguments are validated against the tool's schema and where the
owner's policy (disabled connectors/tools, read-only mode) is enforced.
"""

import json
import re
import time
from datetime import UTC, datetime

from . import store
from .connectors import connector_of
from .registry import TOOLS, ToolError, kind

SUPPORTED_PROTOCOLS = ["2025-06-18", "2025-03-26", "2024-11-05"]
MAX_STRING = 1_000_000


def rpc_error(req_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def validate_args(schema: dict, args) -> dict:
    """Check `args` against a tool's inputSchema (type, enum, pattern, length, required). Returns a cleaned copy.

    Lenient where models are sloppy (numbers as strings, integers for ID strings); strict about everything that could
    change which API endpoint or object a call touches. Unknown keys are dropped.
    """
    if not isinstance(args, dict):
        raise ToolError("Arguments must be an object")
    props, out = schema.get("properties", {}), {}
    missing = [k for k in schema.get("required", []) if args.get(k) in (None, "")]
    if missing:
        raise ToolError(f"Missing required argument(s): {', '.join(missing)}")
    for key, value in args.items():
        if key not in props or value is None:
            continue
        out[key] = _check(key, props[key], value)
    return out


def _check(name: str, spec: dict, value):
    kind_ = spec.get("type")
    if kind_ == "string":
        if isinstance(value, int) and not isinstance(value, bool):
            value = str(value)
        if not isinstance(value, str):
            raise ToolError(f"'{name}' must be a string")
        if len(value) > spec.get("maxLength", MAX_STRING):
            raise ToolError(f"'{name}' is too long")
        if "pattern" in spec and not re.fullmatch(spec["pattern"], value):
            raise ToolError(f"'{name}' has an invalid format (expected {spec['pattern']})")
    elif kind_ == "integer":
        if isinstance(value, str) and re.fullmatch(r"-?\d{1,18}", value):
            value = int(value)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ToolError(f"'{name}' must be an integer")
        if ("minimum" in spec and value < spec["minimum"]) or ("maximum" in spec and value > spec["maximum"]):
            raise ToolError(f"'{name}' is out of range")
    elif kind_ == "boolean":
        if isinstance(value, str) and value.lower() in ("true", "false"):
            value = value.lower() == "true"
        if not isinstance(value, bool):
            raise ToolError(f"'{name}' must be true or false")
    elif kind_ == "array":
        if not isinstance(value, list) or len(value) > 1000:
            raise ToolError(f"'{name}' must be a list")
        item = spec.get("items")
        if item:
            value = [_check(f"{name}[]", item, v) for v in value]
    elif kind_ == "object":
        if not isinstance(value, dict):
            raise ToolError(f"'{name}' must be an object")
    if "enum" in spec and value not in spec["enum"]:
        raise ToolError(f"'{name}' must be one of {spec['enum']}")
    return value


def tool_allowed(name: str, policy: store.Policy) -> str | None:
    """None if the tool may run, otherwise the reason it is blocked."""
    entry = TOOLS.get(name)
    if entry is None:
        return "Unknown tool"
    connector = connector_of(name)
    if connector and connector.id in policy.disabled_connectors:
        return f"The {connector.name} connector is disabled by the server owner"
    if name in policy.disabled_tools:
        return "This tool is disabled by the server owner"
    if policy.read_only and kind(entry["spec"]) != "read":
        return "The server is in read-only mode, so tools that change things are disabled"
    return None


async def run_tool(name: str, arguments, source: str = "mcp") -> tuple[bool, str]:
    """Validate, authorize, run and log one tool call. Returns (ok, text)."""
    started = time.monotonic()
    ok, text = False, ""
    try:
        entry = TOOLS.get(name)
        if entry is None:
            raise ToolError(f"Unknown tool: {name}")
        blocked = tool_allowed(name, await store.load_policy())
        if blocked:
            raise ToolError(blocked)
        args = validate_args(entry["spec"]["inputSchema"], arguments or {})
        result = await entry["fn"](args)
        ok, text = True, json.dumps(result, ensure_ascii=False, indent=2)
    except ToolError as e:
        text = str(e)
    except Exception as e:
        text = f"{type(e).__name__}: {e}"
    await store.record_activity(
        {
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
            "tool": name,
            "source": source,
            "ok": ok,
            "ms": int((time.monotonic() - started) * 1000),
            **({} if ok else {"error": text[:120]}),
        }
    )
    return ok, text


async def handle_rpc(msg: dict, source: str = "mcp") -> dict | None:
    if not isinstance(msg, dict):
        return rpc_error(None, -32600, "Invalid request")
    if "id" not in msg:
        return None  # notification
    req_id, method, params = msg["id"], msg.get("method"), msg.get("params")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return rpc_error(req_id, -32602, "params must be an object")

    if method == "initialize":
        asked = params.get("protocolVersion")
        version = asked if asked in SUPPORTED_PROTOCOLS else SUPPORTED_PROTOCOLS[0]
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"protocolVersion": version, "capabilities": {"tools": {}}, "serverInfo": {"name": "pulse-mcp", "version": "4.0"}},
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    if method == "tools/list":
        policy = await store.load_policy()
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": [t["spec"] for n, t in TOOLS.items() if tool_allowed(n, policy) is None]}}
    if method == "tools/call":
        name = params.get("name")
        if not isinstance(name, str) or name not in TOOLS:
            return rpc_error(req_id, -32602, "Unknown tool")
        ok, text = await run_tool(name, params.get("arguments"), source)
        return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": text}], "isError": not ok}}
    return rpc_error(req_id, -32601, f"Method not found: {method}")
