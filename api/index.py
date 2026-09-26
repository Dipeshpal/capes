"""Personal data MCP server (Discord, Twitter/X) for Vercel.

Speaks MCP over HTTP (JSON-RPC at POST /mcp), protected by a Bearer API key.
Add a tool by decorating an async function with @tool(...).
"""

import asyncio
import json
import os
import secrets
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

import aiohttp
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse

load_dotenv()

app = FastAPI(title="Research MCP", version="2.0")

SUPPORTED_PROTOCOLS = ["2025-06-18", "2025-03-26", "2024-11-05"]
DISCORD_API = "https://discord.com/api/v10"
APIFY_TWEET_ACTOR = os.getenv("APIFY_TWEET_ACTOR", "apidojo~tweet-scraper")


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------

def verify_api_key(authorization: Optional[str]) -> None:
    expected = os.getenv("RESEARCH_API_KEY")
    if not expected:
        raise HTTPException(500, "RESEARCH_API_KEY is not set on the server")
    if not authorization:
        raise HTTPException(401, "Missing Authorization header")
    supplied = authorization[7:] if authorization.startswith("Bearer ") else authorization
    if not secrets.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(403, "Invalid API key")


# --------------------------------------------------------------------------
# Tool registry
# --------------------------------------------------------------------------

ToolFn = Callable[[dict], Awaitable[Any]]
TOOLS: dict[str, dict] = {}


def tool(name: str, description: str, properties: dict, required: Optional[list] = None):
    def register(fn: ToolFn) -> ToolFn:
        TOOLS[name] = {
            "fn": fn,
            "spec": {
                "name": name,
                "description": description,
                "inputSchema": {
                    "type": "object",
                    "properties": properties,
                    "required": required or [],
                },
            },
        }
        return fn

    return register


class ToolError(Exception):
    pass


async def discord_get(session: aiohttp.ClientSession, path: str, params: Optional[dict] = None):
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise ToolError("DISCORD_BOT_TOKEN is not set on the server")
    async with session.get(
        f"{DISCORD_API}{path}",
        params=params,
        headers={"Authorization": f"Bot {token}"},
        timeout=aiohttp.ClientTimeout(total=20),
    ) as resp:
        body = await resp.json(content_type=None)
        if resp.status != 200:
            raise ToolError(f"Discord API {resp.status}: {body.get('message', body)}")
        return body


@tool(
    "discord_list_channels",
    "List text channels the Discord bot can see. Omit guild_id to list every server the bot is in.",
    {"guild_id": {"type": "string", "description": "Discord server (guild) ID, optional"}},
)
async def discord_list_channels(args: dict):
    async with aiohttp.ClientSession() as session:
        if args.get("guild_id"):
            guilds = [{"id": str(args["guild_id"]), "name": None}]
        else:
            guilds = await discord_get(session, "/users/@me/guilds")
        out = []
        for g in guilds:
            channels = await discord_get(session, f"/guilds/{g['id']}/channels")
            out.append(
                {
                    "guild_id": g["id"],
                    "guild_name": g.get("name"),
                    "channels": [
                        {"id": c["id"], "name": c["name"]} for c in channels if c["type"] == 0
                    ],
                }
            )
        return out


@tool(
    "discord_read_channel",
    "Read recent messages from a Discord channel (newest first).",
    {
        "channel_id": {"type": "string", "description": "Discord channel ID"},
        "limit": {"type": "integer", "description": "Messages to fetch, 1-500 (default 50)"},
    },
    ["channel_id"],
)
async def discord_read_channel(args: dict):
    channel_id = str(args["channel_id"])
    limit = max(1, min(int(args.get("limit", 50)), 500))
    messages: list[dict] = []
    before = None
    async with aiohttp.ClientSession() as session:
        while len(messages) < limit:
            params = {"limit": min(100, limit - len(messages))}
            if before:
                params["before"] = before
            batch = await discord_get(session, f"/channels/{channel_id}/messages", params)
            if not batch:
                break
            messages.extend(batch)
            before = batch[-1]["id"]
    return {
        "channel_id": channel_id,
        "count": len(messages),
        "messages": [
            {
                "id": m["id"],
                "timestamp": m["timestamp"],
                "author": m["author"]["username"],
                "content": m["content"],
                "attachments": [a["url"] for a in m.get("attachments", [])],
            }
            for m in messages
        ],
    }


@tool(
    "twitter_search",
    "Search tweets on Twitter/X via Apify.",
    {
        "query": {"type": "string", "description": "Search query"},
        "limit": {"type": "integer", "description": "Max tweets, 1-500 (default 50)"},
    },
    ["query"],
)
async def twitter_search(args: dict):
    token = os.getenv("APIFY_TOKEN")
    if not token:
        raise ToolError("APIFY_TOKEN is not set on the server")
    limit = max(1, min(int(args.get("limit", 50)), 500))
    payload = {"searchTerms": [args["query"]], "maxItems": limit, "sort": "Latest"}
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"https://api.apify.com/v2/acts/{APIFY_TWEET_ACTOR}/run-sync-get-dataset-items",
            params={"timeout": 45},
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=aiohttp.ClientTimeout(total=55),
        ) as resp:
            body = await resp.json(content_type=None)
            if resp.status not in (200, 201):
                raise ToolError(f"Apify API {resp.status}: {body}")
    tweets = [
        {
            "url": t.get("url"),
            "author": (t.get("author") or {}).get("userName"),
            "text": t.get("fullText") or t.get("text"),
            "created_at": t.get("createdAt"),
            "likes": t.get("likeCount"),
            "retweets": t.get("retweetCount"),
            "replies": t.get("replyCount"),
            "views": t.get("viewCount"),
        }
        for t in body
        if t.get("type") == "tweet"
    ][:limit]
    return {"query": args["query"], "count": len(tweets), "tweets": tweets}


# --------------------------------------------------------------------------
# MCP (JSON-RPC over HTTP)
# --------------------------------------------------------------------------

def rpc_error(req_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


async def handle_rpc(msg: dict) -> Optional[dict]:
    if "id" not in msg:
        return None
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
                "serverInfo": {"name": "research-mcp", "version": "2.0"},
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
        try:
            result = await entry["fn"](params.get("arguments") or {})
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


@app.post("/mcp")
async def mcp(request: Request, authorization: Optional[str] = Header(None)):
    verify_api_key(authorization)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse(rpc_error(None, -32700, "Parse error"), status_code=400)

    if isinstance(body, list):
        results = [r for r in await asyncio.gather(*(handle_rpc(m) for m in body)) if r]
        return JSONResponse(results) if results else Response(status_code=202)
    result = await handle_rpc(body)
    return JSONResponse(result) if result else Response(status_code=202)


@app.get("/")
async def health():
    return {
        "status": "online",
        "name": "research-mcp",
        "mcp_endpoint": "/mcp",
        "tools": list(TOOLS),
        "time": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
