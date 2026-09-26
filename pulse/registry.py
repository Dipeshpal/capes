"""Tool registry: decorate an async function with @tool(...) and it is served over MCP."""

from collections.abc import Awaitable, Callable
from typing import Any

ToolFn = Callable[[dict], Awaitable[Any]]
TOOLS: dict[str, dict] = {}

ANNOTATIONS = {
    "read": {"readOnlyHint": True, "openWorldHint": True},
    "write": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": True},
    "destructive": {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": True},
}


class ToolError(Exception):
    """Expected failure; shown to the model as a tool error, not a crash."""


def tool(name: str, description: str, properties: dict, required: list | None = None, hint: str = "read"):
    def register(fn: ToolFn) -> ToolFn:
        TOOLS[name] = {
            "fn": fn,
            "spec": {
                "name": name,
                "description": description,
                "inputSchema": {"type": "object", "properties": properties, "required": required or []},
                "annotations": ANNOTATIONS[hint],
            },
        }
        return fn

    return register


def kind(spec: dict) -> str:
    """'read', 'write' or 'destructive' for a tool spec."""
    a = spec["annotations"]
    if a.get("readOnlyHint"):
        return "read"
    return "destructive" if a.get("destructiveHint") else "write"
