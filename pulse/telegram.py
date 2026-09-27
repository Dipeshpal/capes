"""Telegram via its Bot API: plain HTTPS, no gateway/websocket, needs TELEGRAM_BOT_TOKEN.

Telegram's own API puts the bot token in the URL path (`/bot<TOKEN>/method`), not a header;
there is no alternative. redact() in security.py strips the token from any text before it
reaches a client or a log, and _TOKEN_IN_URL below does the same for the URL itself.
"""

import os
import re

import aiohttp

from .registry import ToolError, tool

API = "https://api.telegram.org"
_TOKEN_IN_URL = re.compile(r"(/bot)[0-9]+:[A-Za-z0-9_-]+")

CHAT_ID = {
    "type": "string",
    "description": "Chat ID (a user, group or channel). Numeric IDs are strings here; a channel can also use its @username.",
    "pattern": r"-?\d{1,20}|@[A-Za-z0-9_]{5,32}",
}


def redact_url(text: str) -> str:
    return _TOKEN_IN_URL.sub(r"\1[redacted]", text)


async def call(method: str, params: dict) -> dict:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ToolError("TELEGRAM_BOT_TOKEN is not set on the server")
    url = f"{API}/bot{token}/{method}"
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.post(url, json=params, timeout=aiohttp.ClientTimeout(total=25)) as resp,
        ):
            body = await resp.json(content_type=None)
    except aiohttp.ClientError as e:
        raise ToolError(redact_url(f"Telegram request failed: {e}")) from e
    if not body.get("ok"):
        raise ToolError(f"Telegram API {resp.status} ({body.get('error_code')}): {body.get('description')}")
    return body["result"]


@tool(
    "telegram_send_message",
    "Send a text message to a Telegram chat (user, group or channel the bot is a member of).",
    {
        "chat_id": CHAT_ID,
        "text": {"type": "string", "maxLength": 4096},
        "parse_mode": {"type": "string", "enum": ["Markdown", "MarkdownV2", "HTML"], "description": "Formatting in text (optional)"},
        "disable_notification": {"type": "boolean", "description": "Send silently"},
    },
    ["chat_id", "text"],
    hint="write",
)
async def send_message(args: dict):
    body = {"chat_id": args["chat_id"], "text": args["text"]}
    if args.get("parse_mode"):
        body["parse_mode"] = args["parse_mode"]
    if args.get("disable_notification") is not None:
        body["disable_notification"] = args["disable_notification"]
    r = await call("sendMessage", body)
    return {"message_id": r.get("message_id"), "chat_id": str(r.get("chat", {}).get("id")), "date": r.get("date")}


@tool(
    "telegram_get_chat",
    "Get basic info about a chat: title, type, description, member count where available.",
    {"chat_id": CHAT_ID},
    ["chat_id"],
)
async def get_chat(args: dict):
    r = await call("getChat", {"chat_id": args["chat_id"]})
    count = None
    try:
        cc = await call("getChatMemberCount", {"chat_id": args["chat_id"]})
        count = cc if isinstance(cc, int) else None
    except ToolError:
        pass
    return {
        "id": str(r.get("id")),
        "type": r.get("type"),
        "title": r.get("title") or r.get("username"),
        "description": r.get("description"),
        "member_count": count,
    }


@tool(
    "telegram_get_updates",
    "Poll recent incoming updates (messages, edits, etc.) the bot has received. Only for bots without a webhook set; each update is returned once, then marked read.",
    {
        "limit": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Max updates to return (default 20)"},
        "timeout_seconds": {"type": "integer", "minimum": 0, "maximum": 30, "description": "Long-poll wait if nothing is pending yet (default 0)"},
    },
    [],
)
async def get_updates(args: dict):
    body = {
        "limit": int(args.get("limit", 20)),
        "timeout": int(args.get("timeout_seconds", 0)),
        "allowed_updates": ["message", "edited_message", "channel_post"],
    }
    updates = await call("getUpdates", body)
    out = []
    for u in updates:
        m = u.get("message") or u.get("edited_message") or u.get("channel_post") or {}
        out.append(
            {
                "update_id": u.get("update_id"),
                "chat_id": str(m.get("chat", {}).get("id")) if m.get("chat") else None,
                "from": (m.get("from") or {}).get("username") or (m.get("from") or {}).get("first_name"),
                "text": m.get("text"),
                "date": m.get("date"),
            }
        )
    return {"count": len(out), "updates": out}
