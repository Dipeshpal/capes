"""Tool registry: decorate an async function with @tool(...) and it is served over MCP."""

from typing import Any, Awaitable, Callable, Optional

ToolFn = Callable[[dict], Awaitable[Any]]
TOOLS: dict[str, dict] = {}

ANNOTATIONS = {
    "read": {"readOnlyHint": True, "openWorldHint": True},
    "write": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": True},
    "destructive": {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": True},
}


class ToolError(Exception):
    """Expected failure; shown to the model as a tool error, not a crash."""


def tool(name: str, description: str, properties: dict, required: Optional[list] = None, hint: str = "read"):
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
