"""Discord tools over the REST API (no gateway, so it works on serverless).

What the bot can do is decided by Discord, not by this code: see "Discord permissions" in the README.
"""

import asyncio
import base64
import json
import os
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

import aiohttp

from .registry import ToolError, tool

API = "https://discord.com/api/v10"
SAFE_PATH = re.compile(r"(?:/[A-Za-z0-9@_.%:\-]+)+")
INVITE_PERMISSIONS = "2253295267998935"  # tests/protocol.py recomputes this from PERMISSIONS
UA = "DiscordBot (https://github.com/Dipeshpal/capes, 3.0)"
DEFAULT_REASON = "via capes"

PERMISSIONS = {
    name: bit
    for bit, name in enumerate(
        [
            "CREATE_INSTANT_INVITE",
            "KICK_MEMBERS",
            "BAN_MEMBERS",
            "ADMINISTRATOR",
            "MANAGE_CHANNELS",
            "MANAGE_GUILD",
            "ADD_REACTIONS",
            "VIEW_AUDIT_LOG",
            "PRIORITY_SPEAKER",
            "STREAM",
            "VIEW_CHANNEL",
            "SEND_MESSAGES",
            "SEND_TTS_MESSAGES",
            "MANAGE_MESSAGES",
            "EMBED_LINKS",
            "ATTACH_FILES",
            "READ_MESSAGE_HISTORY",
            "MENTION_EVERYONE",
            "USE_EXTERNAL_EMOJIS",
            "VIEW_GUILD_INSIGHTS",
            "CONNECT",
            "SPEAK",
            "MUTE_MEMBERS",
            "DEAFEN_MEMBERS",
            "MOVE_MEMBERS",
            "USE_VAD",
            "CHANGE_NICKNAME",
            "MANAGE_NICKNAMES",
            "MANAGE_ROLES",
            "MANAGE_WEBHOOKS",
            "MANAGE_GUILD_EXPRESSIONS",
            "USE_APPLICATION_COMMANDS",
            "REQUEST_TO_SPEAK",
            "MANAGE_EVENTS",
            "MANAGE_THREADS",
            "CREATE_PUBLIC_THREADS",
            "CREATE_PRIVATE_THREADS",
            "USE_EXTERNAL_STICKERS",
            "SEND_MESSAGES_IN_THREADS",
            "USE_EMBEDDED_ACTIVITIES",
            "MODERATE_MEMBERS",
            "VIEW_CREATOR_MONETIZATION_ANALYTICS",
            "USE_SOUNDBOARD",
            "CREATE_GUILD_EXPRESSIONS",
            "CREATE_EVENTS",
            "USE_EXTERNAL_SOUNDS",
            "SEND_VOICE_MESSAGES",
            "RESERVED_47",
            "RESERVED_48",
            "SEND_POLLS",
            "USE_EXTERNAL_APPS",
            "PIN_MESSAGES",
        ]
    )
}
CHANNEL_TYPES = {"text": 0, "voice": 2, "category": 4, "announcement": 5, "stage": 13, "forum": 15}
CHANNEL_TYPE_NAMES = {**{v: k for k, v in CHANNEL_TYPES.items()}, 10: "announcement_thread", 11: "public_thread", 12: "private_thread", 16: "media"}

HINTS = {
    50001: "Missing Access: the bot is not in that server/channel or cannot view it.",
    50013: "Missing Permissions: grant the bot this permission (re-invite it with more permissions, or raise its role). See README > Discord permissions.",
    50035: "Invalid form body: check the argument values.",
    10003: "Unknown channel.",
    10004: "Unknown server.",
    10008: "Unknown message.",
    10011: "Unknown role.",
    10013: "Unknown user.",
    20001: "Bots cannot use this endpoint.",
    50007: "Cannot message this user: they must share a server with the bot and allow direct messages from server members.",
    50109: "The request body was not valid JSON.",
    10015: "Unknown webhook.",
    10006: "Unknown invite.",
}

_bot_id: str | None = None


# --------------------------------------------------------------------------
# HTTP helper
# --------------------------------------------------------------------------


async def call(method: str, path: str, *, json_body: Any = None, params: dict | None = None, reason: str | None = None, data_factory=None) -> Any:
    """One Discord REST call. `data_factory` builds a fresh multipart body per attempt (a form can only be sent once)."""
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise ToolError("DISCORD_BOT_TOKEN is not set on the server")
    if not SAFE_PATH.fullmatch(path) or ".." in path:
        raise ToolError("Refusing an unsafe Discord API path")
    headers = {"Authorization": f"Bot {token}", "User-Agent": UA}
    if reason:
        headers["X-Audit-Log-Reason"] = quote(reason)
    async with aiohttp.ClientSession() as session:
        for attempt in range(2):
            data = data_factory() if data_factory else None
            async with session.request(
                method, f"{API}{path}", json=json_body, data=data, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                text = await resp.text()
                try:
                    body = json.loads(text) if text else None
                except ValueError:
                    body = None  # e.g. an HTML error page from a proxy
                if resp.status == 429 and attempt == 0 and (body or {}).get("retry_after", 99) <= 5:
                    await asyncio.sleep(body["retry_after"])
                    continue
                if resp.status >= 400:
                    code = (body or {}).get("code")
                    msg = (body or {}).get("message", text)
                    hint = HINTS.get(code)
                    raise ToolError(f"Discord {resp.status} (code {code}): {msg}" + (f"\nHint: {hint}" if hint else ""))
                return body
    raise ToolError("Discord rate limit hit; try again shortly.")


async def bot_user_id() -> str:
    global _bot_id
    if not _bot_id:
        _bot_id = (await call("GET", "/users/@me"))["id"]
    return _bot_id


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def perms_to_str(names: list) -> str:
    total = 0
    for n in names:
        key = str(n).upper()
        if key not in PERMISSIONS:
            raise ToolError(f"Unknown permission '{n}'. Valid: {', '.join(PERMISSIONS)}")
        total |= 1 << PERMISSIONS[key]
    return str(total)


def str_to_perms(value) -> list:
    v = int(value)
    return [n for n, bit in PERMISSIONS.items() if v >> bit & 1]


def parse_color(value) -> int:
    if isinstance(value, str):
        return int(value.lstrip("#"), 16)
    return int(value)


def fmt_channel(c: dict) -> dict:
    return clean(
        {
            "id": c["id"],
            "name": c.get("name"),
            "type": CHANNEL_TYPE_NAMES.get(c["type"], c["type"]),
            "parent_id": c.get("parent_id"),
            "topic": c.get("topic"),
            "nsfw": c.get("nsfw") or None,
            "position": c.get("position"),
        }
    )


def fmt_message(m: dict) -> dict:
    return clean(
        {
            "id": m["id"],
            "timestamp": m["timestamp"],
            "edited": m.get("edited_timestamp"),
            "author": m["author"]["username"],
            "author_id": m["author"]["id"],
            "bot": m["author"].get("bot") or None,
            "content": m["content"],
            "attachments": [a["url"] for a in m.get("attachments", [])] or None,
            "embeds": len(m.get("embeds", [])) or None,
            "reactions": [{"emoji": r["emoji"].get("name"), "count": r["count"]} for r in m.get("reactions", [])] or None,
            "reply_to": (m.get("message_reference") or {}).get("message_id"),
            "pinned": m.get("pinned") or None,
            "thread_id": (m.get("thread") or {}).get("id"),
        }
    )


def fmt_role(r: dict) -> dict:
    return {
        "id": r["id"],
        "name": r["name"],
        "color": f"#{r['color']:06x}" if r["color"] else None,
        "position": r["position"],
        "hoist": r["hoist"],
        "mentionable": r["mentionable"],
        "managed": r["managed"],
        "permissions": str_to_perms(r["permissions"]),
    }


def fmt_overwrite(o: dict) -> dict:
    return {
        "id": o["id"],
        "type": "role" if o["type"] == 0 else "member",
        "allow": str_to_perms(o["allow"]),
        "deny": str_to_perms(o["deny"]),
    }


def allowed_mentions(mode: str | None) -> dict:
    return {"none": {"parse": []}, "all": {"parse": ["users", "roles", "everyone"]}}.get(mode or "users", {"parse": ["users"]})


SNOWFLAKE = r"\d{5,25}"


def sid(description: str) -> dict:
    """A Discord ID (snowflake). The pattern is enforced by pulse/mcp.py so an ID can never smuggle extra URL path."""
    return {"type": "string", "description": description, "pattern": SNOWFLAKE}


GUILD = sid("Server (guild) ID")
CHANNEL = sid("Channel ID (a thread ID also works)")
MESSAGE = sid("Message ID")
USER = sid("User ID")
ROLE = sid("Role ID")
REASON = {"type": "string", "description": "Reason shown in the server audit log (optional)"}
PERM_LIST = {
    "type": "array",
    "items": {"type": "string", "enum": list(PERMISSIONS)},
    "description": "Permission names",
}
EMBED = {
    "type": "object",
    "description": "Optional embed: {title, description, url, color (int), fields: [{name, value, inline}], footer: {text}}",
}
MENTIONS = {
    "type": "string",
    "enum": ["users", "none", "all"],
    "description": "Who this message may ping. Default 'users' (blocks @everyone/@here and role pings). 'all' allows them.",
}


# --------------------------------------------------------------------------
# Servers, channels, members, roles (read)
# --------------------------------------------------------------------------


@tool("discord_list_guilds", "List the Discord servers the bot is in.", {})
async def list_guilds(args):
    guilds = await call("GET", "/users/@me/guilds", params={"with_counts": "true"})
    return [{"id": g["id"], "name": g["name"], "owner": g.get("owner"), "members": g.get("approximate_member_count")} for g in guilds]


@tool("discord_get_guild", "Get details about a Discord server.", {"guild_id": GUILD}, ["guild_id"])
async def get_guild(args):
    g = await call("GET", f"/guilds/{args['guild_id']}", params={"with_counts": "true"})
    return {
        "id": g["id"],
        "name": g["name"],
        "owner_id": g["owner_id"],
        "description": g.get("description"),
        "members": g.get("approximate_member_count"),
        "online": g.get("approximate_presence_count"),
        "roles": len(g.get("roles", [])),
        "features": g.get("features"),
    }


@tool(
    "discord_list_channels",
    "List channels (all types, including categories, voice and forums). Omit guild_id to list every server the bot is in.",
    {"guild_id": GUILD},
)
async def list_channels(args):
    guilds = [{"id": str(args["guild_id"]), "name": None}] if args.get("guild_id") else await call("GET", "/users/@me/guilds")
    out = []
    for g in guilds:
        channels = await call("GET", f"/guilds/{g['id']}/channels")
        out.append({"guild_id": g["id"], "guild_name": g.get("name"), "channels": [fmt_channel(c) for c in sorted(channels, key=lambda c: c["position"])]})
    return out


@tool(
    "discord_get_channel",
    "Get a channel or thread, including its permission overwrites (translated to permission names).",
    {"channel_id": CHANNEL},
    ["channel_id"],
)
async def get_channel(args):
    c = await call("GET", f"/channels/{args['channel_id']}")
    out = fmt_channel(c)
    out["slowmode_seconds"] = c.get("rate_limit_per_user")
    out["permission_overwrites"] = [fmt_overwrite(o) for o in c.get("permission_overwrites", [])]
    if "thread_metadata" in c:
        out["thread"] = c["thread_metadata"]
    return out


@tool(
    "discord_read_channel",
    "Read recent messages from a channel or thread (newest first).",
    {
        "channel_id": CHANNEL,
        "limit": {"type": "integer", "description": "Messages to fetch, 1-500 (default 50)"},
        "before": {"type": "string", "description": "Only messages before this message ID (optional)", "pattern": SNOWFLAKE},
    },
    ["channel_id"],
)
async def read_channel(args):
    return await read_messages(str(args["channel_id"]), int(args.get("limit", 50)), args.get("before"))


async def read_messages(channel_id: str, limit: int, before: str | None = None) -> dict:
    limit = max(1, min(limit, 500))
    messages: list = []
    while len(messages) < limit:
        params = {"limit": min(100, limit - len(messages))}
        if before:
            params["before"] = before
        batch = await call("GET", f"/channels/{channel_id}/messages", params=params)
        if not batch:
            break
        messages.extend(batch)
        before = batch[-1]["id"]
    return {"channel_id": channel_id, "count": len(messages), "messages": [fmt_message(m) for m in messages]}


@tool("discord_list_pins", "List pinned messages in a channel.", {"channel_id": CHANNEL}, ["channel_id"])
async def list_pins(args):
    data = await call("GET", f"/channels/{args['channel_id']}/messages/pins")
    return [fmt_message(i["message"]) for i in data.get("items", [])]


@tool(
    "discord_list_members",
    "List server members, or search by name with `query`. Needs the 'Server Members Intent' enabled in the Discord Developer Portal (Bot tab).",
    {
        "guild_id": GUILD,
        "query": {"type": "string", "description": "Username/nickname prefix to search (optional)"},
        "limit": {"type": "integer", "description": "1-1000 (default 50)"},
    },
    ["guild_id"],
)
async def list_members(args):
    limit = max(1, min(int(args.get("limit", 50)), 1000))
    if args.get("query"):
        members = await call("GET", f"/guilds/{args['guild_id']}/members/search", params={"query": args["query"], "limit": min(limit, 100)})
    else:
        members = await call("GET", f"/guilds/{args['guild_id']}/members", params={"limit": limit})
    return [
        clean(
            {
                "user_id": m["user"]["id"],
                "username": m["user"]["username"],
                "nick": m.get("nick"),
                "bot": m["user"].get("bot") or None,
                "roles": m["roles"],
                "joined_at": m.get("joined_at"),
                "timeout_until": m.get("communication_disabled_until"),
            }
        )
        for m in members
    ]


@tool(
    "discord_list_emojis",
    "List a server's custom emojis, including the name:id value used by discord_add_reaction. The bot must have access to the server.",
    {"guild_id": GUILD},
    ["guild_id"],
    hint="read",
)
async def list_emojis(args):
    emojis = await call("GET", f"/guilds/{args['guild_id']}/emojis")
    return [{"id": e["id"], "name": e["name"], "animated": e.get("animated", False), "reaction": f"{e['name']}:{e['id']}"} for e in emojis]


@tool("discord_list_roles", "List a server's roles with their permissions.", {"guild_id": GUILD}, ["guild_id"])
async def list_roles(args):
    roles = await call("GET", f"/guilds/{args['guild_id']}/roles")
    return [fmt_role(r) for r in sorted(roles, key=lambda r: -r["position"])]


@tool(
    "discord_list_threads",
    "List active threads in a server, or archived public threads of one channel when channel_id is given.",
    {"guild_id": GUILD, "channel_id": sid("Channel to list archived public threads for (optional)")},
)
async def list_threads(args):
    if args.get("channel_id"):
        data = await call("GET", f"/channels/{args['channel_id']}/threads/archived/public", params={"limit": 50})
    elif args.get("guild_id"):
        data = await call("GET", f"/guilds/{args['guild_id']}/threads/active")
    else:
        raise ToolError("Provide guild_id (active threads) or channel_id (archived threads)")
    return [fmt_channel(t) | {"archived": (t.get("thread_metadata") or {}).get("archived"), "message_count": t.get("message_count")} for t in data["threads"]]


# --------------------------------------------------------------------------
# Messages
# --------------------------------------------------------------------------


@tool(
    "discord_send_message",
    "Send a message to a channel or thread. Provide content and/or an embed.",
    {
        "channel_id": CHANNEL,
        "content": {"type": "string", "description": "Message text (max 2000 chars)", "maxLength": 2000},
        "embed": EMBED,
        "reply_to_message_id": sid("Reply to this message (optional)"),
        "mentions": MENTIONS,
    },
    ["channel_id"],
    hint="write",
)
async def send_message(args):
    if not args.get("content") and not args.get("embed"):
        raise ToolError("Provide content and/or embed")
    body = clean(
        {
            "content": args.get("content"),
            "embeds": [args["embed"]] if args.get("embed") else None,
            "allowed_mentions": allowed_mentions(args.get("mentions")),
            "message_reference": {"message_id": str(args["reply_to_message_id"])} if args.get("reply_to_message_id") else None,
        }
    )
    m = await call("POST", f"/channels/{args['channel_id']}/messages", json_body=body)
    return {"id": m["id"], "channel_id": m["channel_id"], "timestamp": m["timestamp"]}


@tool(
    "discord_edit_message",
    "Edit a message. Discord only lets the bot edit its own messages.",
    {"channel_id": CHANNEL, "message_id": MESSAGE, "content": {"type": "string", "maxLength": 2000}, "embed": EMBED, "mentions": MENTIONS},
    ["channel_id", "message_id"],
    hint="write",
)
async def edit_message(args):
    body = clean(
        {"content": args.get("content"), "embeds": [args["embed"]] if args.get("embed") else None, "allowed_mentions": allowed_mentions(args.get("mentions"))}
    )
    m = await call("PATCH", f"/channels/{args['channel_id']}/messages/{args['message_id']}", json_body=body)
    return {"id": m["id"], "edited": m.get("edited_timestamp")}


@tool(
    "discord_delete_message",
    "Delete a message. Needs Manage Messages to delete other people's messages.",
    {"channel_id": CHANNEL, "message_id": MESSAGE, "reason": REASON},
    ["channel_id", "message_id"],
    hint="destructive",
)
async def delete_message(args):
    await call("DELETE", f"/channels/{args['channel_id']}/messages/{args['message_id']}", reason=args.get("reason") or DEFAULT_REASON)
    return {"deleted": str(args["message_id"])}


@tool(
    "discord_bulk_delete_messages",
    "Delete 2-100 messages at once (must be newer than 14 days). Needs Manage Messages.",
    {
        "channel_id": CHANNEL,
        "message_ids": {"type": "array", "items": {"type": "string", "pattern": SNOWFLAKE}, "description": "2-100 message IDs"},
        "reason": REASON,
    },
    ["channel_id", "message_ids"],
    hint="destructive",
)
async def bulk_delete(args):
    ids = [str(i) for i in args["message_ids"]]
    if not 2 <= len(ids) <= 100:
        raise ToolError("message_ids must contain 2-100 IDs")
    await call("POST", f"/channels/{args['channel_id']}/messages/bulk-delete", json_body={"messages": ids}, reason=args.get("reason") or DEFAULT_REASON)
    return {"deleted": len(ids)}


@tool(
    "discord_pin_message",
    "Pin (default) or unpin a message. Needs the Pin Messages permission (Discord split it from Manage Messages).",
    {"channel_id": CHANNEL, "message_id": MESSAGE, "unpin": {"type": "boolean", "description": "Set true to unpin"}},
    ["channel_id", "message_id"],
    hint="write",
)
async def pin_message(args):
    unpin = bool(args.get("unpin"))
    await call("DELETE" if unpin else "PUT", f"/channels/{args['channel_id']}/messages/pins/{args['message_id']}", reason=DEFAULT_REASON)
    return {"message_id": str(args["message_id"]), "pinned": not unpin}


@tool(
    "discord_add_reaction",
    "React to a message. emoji is a unicode emoji (👍) or a custom emoji as name:id.",
    {"channel_id": CHANNEL, "message_id": MESSAGE, "emoji": {"type": "string", "maxLength": 100}},
    ["channel_id", "message_id", "emoji"],
    hint="write",
)
async def add_reaction(args):
    await call("PUT", f"/channels/{args['channel_id']}/messages/{args['message_id']}/reactions/{quote(args['emoji'], safe='')}/@me")
    return {"reacted": args["emoji"]}


@tool(
    "discord_remove_reaction",
    "Remove the bot's reaction, another user's reaction (user_id), or all reactions on the message (clear_all). Removing others' reactions needs Manage Messages.",
    {
        "channel_id": CHANNEL,
        "message_id": MESSAGE,
        "emoji": {"type": "string", "maxLength": 100, "description": "Unicode or name:id. Not needed with clear_all."},
        "user_id": sid("Remove this user's reaction instead of the bot's"),
        "clear_all": {"type": "boolean", "description": "Remove every reaction from the message"},
    },
    ["channel_id", "message_id"],
    hint="destructive",
)
async def remove_reaction(args):
    base = f"/channels/{args['channel_id']}/messages/{args['message_id']}/reactions"
    if args.get("clear_all"):
        await call("DELETE", base)
        return {"cleared": "all"}
    if not args.get("emoji"):
        raise ToolError("emoji is required unless clear_all is true")
    await call("DELETE", f"{base}/{quote(args['emoji'], safe='')}/{args.get('user_id') or '@me'}")
    return {"removed": args["emoji"]}


# --------------------------------------------------------------------------
# Channels and permissions
# --------------------------------------------------------------------------


@tool(
    "discord_create_channel",
    "Create a channel in a server. Needs Manage Channels.",
    {
        "guild_id": GUILD,
        "name": {"type": "string"},
        "type": {"type": "string", "enum": list(CHANNEL_TYPES), "description": "Default text"},
        "topic": {"type": "string"},
        "parent_id": sid("Category ID to put the channel under"),
        "nsfw": {"type": "boolean"},
        "slowmode_seconds": {"type": "integer"},
        "private": {"type": "boolean", "description": "Hide from @everyone (the bot keeps access). Use discord_set_channel_permission to let roles in."},
    },
    ["guild_id", "name"],
    hint="write",
)
async def create_channel(args):
    kind = args.get("type", "text")
    if kind not in CHANNEL_TYPES:
        raise ToolError(f"type must be one of {list(CHANNEL_TYPES)}")
    overwrites = None
    if args.get("private"):
        me = await bot_user_id()
        overwrites = [
            {"id": str(args["guild_id"]), "type": 0, "allow": "0", "deny": perms_to_str(["VIEW_CHANNEL"])},
            {"id": me, "type": 1, "allow": perms_to_str(["VIEW_CHANNEL", "SEND_MESSAGES", "READ_MESSAGE_HISTORY", "MANAGE_CHANNELS"]), "deny": "0"},
        ]
    body = clean(
        {
            "name": args["name"],
            "type": CHANNEL_TYPES[kind],
            "topic": args.get("topic"),
            "parent_id": args.get("parent_id"),
            "nsfw": args.get("nsfw"),
            "rate_limit_per_user": args.get("slowmode_seconds"),
            "permission_overwrites": overwrites,
        }
    )
    return fmt_channel(await call("POST", f"/guilds/{args['guild_id']}/channels", json_body=body, reason=DEFAULT_REASON))


@tool(
    "discord_edit_channel",
    "Edit a channel or a thread (rename, topic, move, slowmode; for threads also archive/lock). Needs Manage Channels (Manage Threads for threads).",
    {
        "channel_id": CHANNEL,
        "name": {"type": "string"},
        "topic": {"type": "string"},
        "parent_id": sid("Move under this category"),
        "nsfw": {"type": "boolean"},
        "slowmode_seconds": {"type": "integer"},
        "position": {"type": "integer"},
        "archived": {"type": "boolean", "description": "Threads only"},
        "locked": {"type": "boolean", "description": "Threads only"},
        "auto_archive_minutes": {"type": "integer", "enum": [60, 1440, 4320, 10080], "description": "Threads only"},
    },
    ["channel_id"],
    hint="write",
)
async def edit_channel(args):
    body = clean(
        {
            "name": args.get("name"),
            "topic": args.get("topic"),
            "parent_id": args.get("parent_id"),
            "nsfw": args.get("nsfw"),
            "rate_limit_per_user": args.get("slowmode_seconds"),
            "position": args.get("position"),
            "archived": args.get("archived"),
            "locked": args.get("locked"),
            "auto_archive_duration": args.get("auto_archive_minutes"),
        }
    )
    if not body:
        raise ToolError("Nothing to change")
    return fmt_channel(await call("PATCH", f"/channels/{args['channel_id']}", json_body=body, reason=DEFAULT_REASON))


@tool(
    "discord_delete_channel",
    "Permanently delete a channel or thread. This cannot be undone.",
    {"channel_id": CHANNEL, "reason": REASON},
    ["channel_id"],
    hint="destructive",
)
async def delete_channel(args):
    c = await call("DELETE", f"/channels/{args['channel_id']}", reason=args.get("reason") or DEFAULT_REASON)
    return {"deleted": c["id"], "name": c.get("name")}


@tool(
    "discord_set_channel_permission",
    "Set (replace) the permission overwrite for a role or member on a channel. Permissions in neither allow nor deny inherit. Needs Manage Roles.",
    {
        "channel_id": CHANNEL,
        "target_id": sid("Role ID or user ID (the @everyone role ID equals the server ID)"),
        "target_type": {"type": "string", "enum": ["role", "member"]},
        "allow": PERM_LIST,
        "deny": PERM_LIST,
    },
    ["channel_id", "target_id", "target_type"],
    hint="write",
)
async def set_channel_permission(args):
    body = {"type": 0 if args["target_type"] == "role" else 1, "allow": perms_to_str(args.get("allow") or []), "deny": perms_to_str(args.get("deny") or [])}
    await call("PUT", f"/channels/{args['channel_id']}/permissions/{args['target_id']}", json_body=body, reason=DEFAULT_REASON)
    return {"target_id": str(args["target_id"]), "allow": args.get("allow") or [], "deny": args.get("deny") or []}


@tool(
    "discord_delete_channel_permission",
    "Remove a role's or member's permission overwrite from a channel.",
    {"channel_id": CHANNEL, "target_id": sid("Role ID or user ID")},
    ["channel_id", "target_id"],
    hint="destructive",
)
async def delete_channel_permission(args):
    await call("DELETE", f"/channels/{args['channel_id']}/permissions/{args['target_id']}", reason=DEFAULT_REASON)
    return {"removed": str(args["target_id"])}


@tool(
    "discord_create_invite",
    "Create an invite link for a channel.",
    {
        "channel_id": CHANNEL,
        "max_age_seconds": {"type": "integer", "description": "0 = never expires (default 86400)"},
        "max_uses": {"type": "integer", "description": "0 = unlimited"},
        "temporary": {"type": "boolean", "description": "Kick members who are not given a role when they disconnect"},
    },
    ["channel_id"],
    hint="write",
)
async def create_invite(args):
    body = {"max_age": args.get("max_age_seconds", 86400), "max_uses": args.get("max_uses", 0), "temporary": bool(args.get("temporary")), "unique": True}
    inv = await call("POST", f"/channels/{args['channel_id']}/invites", json_body=body, reason=DEFAULT_REASON)
    return {"url": f"https://discord.gg/{inv['code']}", "expires_at": inv.get("expires_at")}


# --------------------------------------------------------------------------
# Threads
# --------------------------------------------------------------------------


@tool(
    "discord_create_thread",
    "Create a thread: from an existing message (message_id), as a standalone thread, or as a forum post (content). Edit/archive/delete threads with discord_edit_channel / discord_delete_channel.",
    {
        "channel_id": sid("Parent text/announcement/forum channel"),
        "name": {"type": "string"},
        "message_id": sid("Start the thread from this message (optional)"),
        "content": {"type": "string", "description": "First post text; required for forum channels"},
        "tag_ids": {"type": "array", "items": {"type": "string", "pattern": SNOWFLAKE}, "description": "Forum tag IDs to apply (see discord_list_forum_tags)"},
        "private": {"type": "boolean", "description": "Private thread (standalone only)"},
        "auto_archive_minutes": {"type": "integer", "enum": [60, 1440, 4320, 10080]},
    },
    ["channel_id", "name"],
    hint="write",
)
async def create_thread(args):
    archive = args.get("auto_archive_minutes", 1440)
    cid = args["channel_id"]
    if args.get("message_id"):
        t = await call("POST", f"/channels/{cid}/messages/{args['message_id']}/threads", json_body={"name": args["name"], "auto_archive_duration": archive})
    elif args.get("content"):
        t = await call(
            "POST",
            f"/channels/{cid}/threads",
            json_body={
                "name": args["name"],
                "auto_archive_duration": archive,
                "message": {"content": args["content"], "allowed_mentions": {"parse": ["users"]}},
                **({"applied_tags": [str(t) for t in args["tag_ids"]]} if args.get("tag_ids") else {}),
            },
        )
    else:
        t = await call(
            "POST", f"/channels/{cid}/threads", json_body={"name": args["name"], "auto_archive_duration": archive, "type": 12 if args.get("private") else 11}
        )
    return fmt_channel(t)


@tool(
    "discord_thread_member",
    "Manage thread membership: join/leave (the bot), add/remove a user, or list members.",
    {
        "thread_id": sid("Thread ID"),
        "action": {"type": "string", "enum": ["join", "leave", "add", "remove", "list"]},
        "user_id": sid("Required for add/remove"),
    },
    ["thread_id", "action"],
    hint="write",
)
async def thread_member(args):
    t, action = args["thread_id"], args["action"]
    if action == "list":
        return [m["user_id"] for m in await call("GET", f"/channels/{t}/thread-members")]
    if action in ("add", "remove") and not args.get("user_id"):
        raise ToolError("user_id is required for add/remove")
    who = args.get("user_id") if action in ("add", "remove") else "@me"
    await call("PUT" if action in ("join", "add") else "DELETE", f"/channels/{t}/thread-members/{who}")
    return {"thread_id": str(t), "action": action, "user": who}


# --------------------------------------------------------------------------
# Roles and moderation
# --------------------------------------------------------------------------


@tool(
    "discord_create_role",
    "Create a role. Needs Manage Roles; the bot can only grant permissions it has itself.",
    {
        "guild_id": GUILD,
        "name": {"type": "string"},
        "permissions": PERM_LIST,
        "color": {"type": "string", "description": "Hex like #ff8800"},
        "hoist": {"type": "boolean", "description": "Show members separately in the list"},
        "mentionable": {"type": "boolean"},
    },
    ["guild_id", "name"],
    hint="write",
)
async def create_role(args):
    body = clean(
        {
            "name": args["name"],
            "permissions": perms_to_str(args["permissions"]) if args.get("permissions") is not None else None,
            "color": parse_color(args["color"]) if args.get("color") else None,
            "hoist": args.get("hoist"),
            "mentionable": args.get("mentionable"),
        }
    )
    return fmt_role(await call("POST", f"/guilds/{args['guild_id']}/roles", json_body=body, reason=DEFAULT_REASON))


@tool(
    "discord_edit_role",
    "Edit a role. Passing permissions replaces the role's whole permission set.",
    {
        "guild_id": GUILD,
        "role_id": ROLE,
        "name": {"type": "string"},
        "permissions": PERM_LIST,
        "color": {"type": "string", "description": "Hex like #ff8800"},
        "hoist": {"type": "boolean"},
        "mentionable": {"type": "boolean"},
    },
    ["guild_id", "role_id"],
    hint="write",
)
async def edit_role(args):
    body = clean(
        {
            "name": args.get("name"),
            "permissions": perms_to_str(args["permissions"]) if args.get("permissions") is not None else None,
            "color": parse_color(args["color"]) if args.get("color") else None,
            "hoist": args.get("hoist"),
            "mentionable": args.get("mentionable"),
        }
    )
    if not body:
        raise ToolError("Nothing to change")
    return fmt_role(await call("PATCH", f"/guilds/{args['guild_id']}/roles/{args['role_id']}", json_body=body, reason=DEFAULT_REASON))


@tool("discord_delete_role", "Delete a role permanently.", {"guild_id": GUILD, "role_id": ROLE, "reason": REASON}, ["guild_id", "role_id"], hint="destructive")
async def delete_role(args):
    await call("DELETE", f"/guilds/{args['guild_id']}/roles/{args['role_id']}", reason=args.get("reason") or DEFAULT_REASON)
    return {"deleted": str(args["role_id"])}


@tool(
    "discord_member_role",
    "Give a role to a member, or take it away. The role must be below the bot's highest role.",
    {"guild_id": GUILD, "user_id": USER, "role_id": ROLE, "action": {"type": "string", "enum": ["add", "remove"]}},
    ["guild_id", "user_id", "role_id", "action"],
    hint="write",
)
async def member_role(args):
    if args["action"] not in ("add", "remove"):
        raise ToolError("action must be add or remove")
    await call(
        "PUT" if args["action"] == "add" else "DELETE", f"/guilds/{args['guild_id']}/members/{args['user_id']}/roles/{args['role_id']}", reason=DEFAULT_REASON
    )
    return {"user_id": str(args["user_id"]), "role_id": str(args["role_id"]), "action": args["action"]}


@tool(
    "discord_moderate_member",
    "Moderate a member: kick, ban, unban, timeout (mute for N minutes) or untimeout. Needs Kick/Ban/Moderate Members. Destructive: confirm with the user first.",
    {
        "guild_id": GUILD,
        "user_id": USER,
        "action": {"type": "string", "enum": ["kick", "ban", "unban", "timeout", "untimeout"]},
        "timeout_minutes": {"type": "integer", "description": "For timeout: 1-40320 (28 days)"},
        "delete_message_seconds": {"type": "integer", "description": "For ban: also delete their messages from the last N seconds (max 604800)"},
        "reason": REASON,
    },
    ["guild_id", "user_id", "action"],
    hint="destructive",
)
async def moderate_member(args):
    g, u, action, reason = args["guild_id"], args["user_id"], args["action"], args.get("reason") or DEFAULT_REASON
    if action == "kick":
        await call("DELETE", f"/guilds/{g}/members/{u}", reason=reason)
    elif action == "ban":
        await call("PUT", f"/guilds/{g}/bans/{u}", json_body={"delete_message_seconds": int(args.get("delete_message_seconds", 0))}, reason=reason)
    elif action == "unban":
        await call("DELETE", f"/guilds/{g}/bans/{u}", reason=reason)
    elif action in ("timeout", "untimeout"):
        until = None
        if action == "timeout":
            minutes = int(args.get("timeout_minutes", 10))
            if not 1 <= minutes <= 40320:
                raise ToolError("timeout_minutes must be 1-40320")
            until = (datetime.now(UTC) + timedelta(minutes=minutes)).isoformat()
        await call("PATCH", f"/guilds/{g}/members/{u}", json_body={"communication_disabled_until": until}, reason=reason)
    else:
        raise ToolError("action must be kick, ban, unban, timeout or untimeout")
    return {"user_id": str(u), "action": action}


# --------------------------------------------------------------------------
# Messages: single message, who reacted, direct messages, files, polls
# --------------------------------------------------------------------------

MAX_UPLOAD_BYTES = 3_000_000  # Vercel caps request bodies at 4.5 MB, and base64 adds a third
FILENAME = r"[A-Za-z0-9._ \-]{1,100}"
INVITE_CODE = r"[A-Za-z0-9\-]{2,32}"


@tool("discord_get_message", "Read one message by ID.", {"channel_id": CHANNEL, "message_id": MESSAGE}, ["channel_id", "message_id"])
async def get_message(args):
    return fmt_message(await call("GET", f"/channels/{args['channel_id']}/messages/{args['message_id']}"))


@tool(
    "discord_list_reactions",
    "List the users who reacted to a message with one emoji (unicode or name:id).",
    {"channel_id": CHANNEL, "message_id": MESSAGE, "emoji": {"type": "string", "maxLength": 100}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}},
    ["channel_id", "message_id", "emoji"],
)
async def list_reactions(args):
    users = await call(
        "GET",
        f"/channels/{args['channel_id']}/messages/{args['message_id']}/reactions/{quote(args['emoji'], safe='')}",
        params={"limit": int(args.get("limit", 25))},
    )
    return [{"id": u["id"], "username": u["username"]} for u in users]


async def dm_channel(user_id: str) -> str:
    """Open (or fetch) the direct-message channel with a user."""
    return (await call("POST", "/users/@me/channels", json_body={"recipient_id": str(user_id)}))["id"]


@tool(
    "discord_send_dm",
    "Send a direct message to a user. They must share a server with the bot and allow DMs from server members. Never pings anyone.",
    {"user_id": USER, "content": {"type": "string", "maxLength": 2000}, "embed": EMBED},
    ["user_id"],
    hint="write",
)
async def send_dm(args):
    if not args.get("content") and not args.get("embed"):
        raise ToolError("Provide content and/or embed")
    channel = await dm_channel(args["user_id"])
    body = clean({"content": args.get("content"), "embeds": [args["embed"]] if args.get("embed") else None, "allowed_mentions": {"parse": []}})
    m = await call("POST", f"/channels/{channel}/messages", json_body=body)
    return {"id": m["id"], "channel_id": m["channel_id"], "timestamp": m["timestamp"]}


@tool(
    "discord_read_dm",
    "Read recent direct messages between the bot and a user (newest first).",
    {"user_id": USER, "limit": {"type": "integer", "minimum": 1, "maximum": 100}},
    ["user_id"],
)
async def read_dm(args):
    return await read_messages(await dm_channel(args["user_id"]), int(args.get("limit", 25)))


@tool(
    "discord_send_file",
    "Upload a file (base64, up to 3 MB) to a channel or thread, with an optional message.",
    {
        "channel_id": CHANNEL,
        "filename": {"type": "string", "pattern": FILENAME, "description": "For example report.pdf"},
        "content_base64": {"type": "string", "maxLength": 4_100_000, "description": "File bytes, base64 encoded (up to 3 MB of file)"},
        "mime_type": {"type": "string", "maxLength": 100, "description": "Default application/octet-stream"},
        "content": {"type": "string", "maxLength": 2000, "description": "Message text to send with the file"},
    },
    ["channel_id", "filename", "content_base64"],
    hint="write",
)
async def send_file(args):
    try:
        raw = base64.b64decode(args["content_base64"], validate=True)
    except ValueError as e:
        raise ToolError("content_base64 is not valid base64") from e
    if not raw:
        raise ToolError("The file is empty")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ToolError(f"The file is {len(raw)} bytes; this server accepts up to {MAX_UPLOAD_BYTES}")
    payload = json.dumps(clean({"content": args.get("content"), "allowed_mentions": {"parse": ["users"]}}))

    def form():
        f = aiohttp.FormData()
        f.add_field("payload_json", payload, content_type="application/json")
        f.add_field("files[0]", raw, filename=args["filename"], content_type=args.get("mime_type") or "application/octet-stream")
        return f

    m = await call("POST", f"/channels/{args['channel_id']}/messages", data_factory=form)
    return {"id": m["id"], "channel_id": m["channel_id"], "attachments": [a["url"] for a in m.get("attachments", [])]}


@tool(
    "discord_create_poll",
    "Post a native Discord poll (2 to 10 answers) in a channel.",
    {
        "channel_id": CHANNEL,
        "question": {"type": "string", "maxLength": 300},
        "answers": {"type": "array", "items": {"type": "string", "maxLength": 55}, "description": "2 to 10 answer texts"},
        "duration_hours": {"type": "integer", "minimum": 1, "maximum": 768, "description": "Default 24"},
        "allow_multiselect": {"type": "boolean"},
    },
    ["channel_id", "question", "answers"],
    hint="write",
)
async def create_poll(args):
    answers = args["answers"]
    if not 2 <= len(answers) <= 10 or not all(a.strip() for a in answers):
        raise ToolError("A poll needs 2 to 10 non-empty answers")
    poll = {
        "question": {"text": args["question"]},
        "answers": [{"poll_media": {"text": a}} for a in answers],
        "duration": int(args.get("duration_hours", 24)),
        "allow_multiselect": bool(args.get("allow_multiselect")),
    }
    m = await call("POST", f"/channels/{args['channel_id']}/messages", json_body={"poll": poll})
    return {"id": m["id"], "channel_id": m["channel_id"]}


# --------------------------------------------------------------------------
# Forum tags
# --------------------------------------------------------------------------

FORUM_TYPES = (15, 16)


def fmt_tag(t: dict) -> dict:
    return clean({"id": t["id"], "name": t["name"], "moderated": t.get("moderated") or None, "emoji": t.get("emoji_name")})


async def forum_tags(channel_id: str) -> tuple[dict, list]:
    c = await call("GET", f"/channels/{channel_id}")
    if c["type"] not in FORUM_TYPES:
        raise ToolError("That channel is not a forum or media channel")
    return c, c.get("available_tags", [])


@tool("discord_list_forum_tags", "List the tags of a forum channel.", {"channel_id": CHANNEL}, ["channel_id"])
async def list_forum_tags(args):
    _, tags = await forum_tags(str(args["channel_id"]))
    return [fmt_tag(t) for t in tags]


@tool(
    "discord_manage_forum_tag",
    "Add, rename or remove a tag on a forum channel. Needs Manage Channels. Removing a tag removes it from posts that use it.",
    {
        "channel_id": CHANNEL,
        "action": {"type": "string", "enum": ["add", "rename", "remove"]},
        "name": {"type": "string", "maxLength": 20, "description": "Tag name (add, rename)"},
        "tag_id": sid("Tag ID (rename, remove)"),
        "emoji": {"type": "string", "maxLength": 20, "description": "Unicode emoji for the tag (add, rename), optional"},
        "moderated": {"type": "boolean", "description": "Only members with Manage Threads can apply it (add)"},
    },
    ["channel_id", "action"],
    hint="destructive",
)
async def manage_forum_tag(args):
    cid, action = str(args["channel_id"]), args["action"]
    _, tags = await forum_tags(cid)
    keep = [clean({k: t.get(k) for k in ("id", "name", "moderated", "emoji_id", "emoji_name")}) for t in tags]
    if action == "add":
        if not args.get("name"):
            raise ToolError("name is required to add a tag")
        keep.append(clean({"name": args["name"], "moderated": bool(args.get("moderated")), "emoji_name": args.get("emoji")}))
    else:
        target = next((t for t in keep if t["id"] == str(args.get("tag_id"))), None)
        if not target:
            raise ToolError("No tag with that tag_id on this channel (see discord_list_forum_tags)")
        if action == "remove":
            keep.remove(target)
        elif action == "rename":
            if not args.get("name"):
                raise ToolError("name is required to rename a tag")
            target["name"] = args["name"]
            if args.get("emoji"):
                target["emoji_name"] = args["emoji"]
                target.pop("emoji_id", None)
        else:
            raise ToolError("action must be add, rename or remove")
    updated = await call("PATCH", f"/channels/{cid}", json_body={"available_tags": keep}, reason=DEFAULT_REASON)
    return [fmt_tag(t) for t in updated.get("available_tags", [])]


# --------------------------------------------------------------------------
# Webhooks (the webhook token stays on the server and is never returned)
# --------------------------------------------------------------------------


def fmt_webhook(w: dict) -> dict:
    return clean(
        {
            "id": w["id"],
            "name": w.get("name"),
            "channel_id": w.get("channel_id"),
            "guild_id": w.get("guild_id"),
            "created_by": (w.get("user") or {}).get("username"),
        }
    )


@tool(
    "discord_list_webhooks",
    "List webhooks of a channel or of a whole server. Tokens are never shown. Needs Manage Webhooks.",
    {"channel_id": CHANNEL, "guild_id": GUILD},
)
async def list_webhooks(args):
    if args.get("channel_id"):
        hooks = await call("GET", f"/channels/{args['channel_id']}/webhooks")
    elif args.get("guild_id"):
        hooks = await call("GET", f"/guilds/{args['guild_id']}/webhooks")
    else:
        raise ToolError("Provide channel_id or guild_id")
    return [fmt_webhook(w) for w in hooks]


@tool(
    "discord_create_webhook",
    "Create a webhook in a channel. Returns its ID only; use discord_send_webhook_message to post through it. Needs Manage Webhooks.",
    {"channel_id": CHANNEL, "name": {"type": "string", "maxLength": 80}},
    ["channel_id", "name"],
    hint="write",
)
async def create_webhook(args):
    return fmt_webhook(await call("POST", f"/channels/{args['channel_id']}/webhooks", json_body={"name": args["name"]}, reason=DEFAULT_REASON))


@tool(
    "discord_send_webhook_message",
    "Post a message through a webhook, optionally under a custom display name. The server looks up the webhook token itself.",
    {
        "webhook_id": sid("Webhook ID (from discord_list_webhooks)"),
        "content": {"type": "string", "maxLength": 2000},
        "username": {"type": "string", "maxLength": 80, "description": "Display name to post as (optional)"},
        "embed": EMBED,
    },
    ["webhook_id"],
    hint="write",
)
async def send_webhook_message(args):
    if not args.get("content") and not args.get("embed"):
        raise ToolError("Provide content and/or embed")
    hook = await call("GET", f"/webhooks/{args['webhook_id']}")
    token = hook.get("token")
    if not token:
        raise ToolError("This webhook has no token the bot can read (it belongs to another application)")
    body = clean(
        {
            "content": args.get("content"),
            "username": args.get("username"),
            "embeds": [args["embed"]] if args.get("embed") else None,
            "allowed_mentions": {"parse": ["users"]},
        }
    )
    m = await call("POST", f"/webhooks/{args['webhook_id']}/{token}", json_body=body, params={"wait": "true"})
    return {"id": m["id"], "channel_id": m["channel_id"]}


@tool(
    "discord_delete_webhook",
    "Delete a webhook permanently. Needs Manage Webhooks.",
    {"webhook_id": sid("Webhook ID"), "reason": REASON},
    ["webhook_id"],
    hint="destructive",
)
async def delete_webhook(args):
    await call("DELETE", f"/webhooks/{args['webhook_id']}", reason=args.get("reason") or DEFAULT_REASON)
    return {"deleted": str(args["webhook_id"])}


# --------------------------------------------------------------------------
# Invites and audit log
# --------------------------------------------------------------------------


@tool("discord_list_invites", "List a server's active invites. Needs Manage Server.", {"guild_id": GUILD}, ["guild_id"])
async def list_invites(args):
    invites = await call("GET", f"/guilds/{args['guild_id']}/invites")
    return [
        clean(
            {
                "code": i["code"],
                "channel": (i.get("channel") or {}).get("name"),
                "inviter": (i.get("inviter") or {}).get("username"),
                "uses": i.get("uses"),
                "max_uses": i.get("max_uses") or None,
                "expires_at": i.get("expires_at"),
            }
        )
        for i in invites
    ]


@tool(
    "discord_delete_invite",
    "Revoke an invite link. Needs Manage Server (or Manage Channels for that channel).",
    {"code": {"type": "string", "pattern": INVITE_CODE}, "reason": REASON},
    ["code"],
    hint="destructive",
)
async def delete_invite(args):
    await call("DELETE", f"/invites/{args['code']}", reason=args.get("reason") or DEFAULT_REASON)
    return {"revoked": args["code"]}


@tool(
    "discord_get_audit_log",
    "Read a server's audit log (who changed what, newest first). Needs View Audit Log.",
    {
        "guild_id": GUILD,
        "limit": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Default 25"},
        "user_id": sid("Only actions by this user (optional)"),
        "action_type": {"type": "integer", "minimum": 1, "maximum": 200, "description": "Discord audit log action type number (optional)"},
    },
    ["guild_id"],
)
async def get_audit_log(args):
    params = clean({"limit": int(args.get("limit", 25)), "user_id": args.get("user_id"), "action_type": args.get("action_type")})
    data = await call("GET", f"/guilds/{args['guild_id']}/audit-logs", params=params)
    names = {u["id"]: u["username"] for u in data.get("users", [])}
    return [
        clean(
            {
                "id": e["id"],
                "action_type": e["action_type"],
                "by": names.get(e.get("user_id"), e.get("user_id")),
                "target_id": e.get("target_id"),
                "reason": e.get("reason"),
                "changed": [c.get("key") for c in e.get("changes", [])] or None,
            }
        )
        for e in data.get("audit_log_entries", [])
    ]
