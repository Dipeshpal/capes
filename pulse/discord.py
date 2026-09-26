"""Discord tools over the REST API (no gateway, so it works on serverless).

What the bot can do is decided by Discord, not by this code: see "Discord permissions" in the README.
"""

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import quote

import aiohttp

from .registry import ToolError, tool

API = "https://discord.com/api/v10"
UA = "DiscordBot (https://github.com/Dipeshpal/pulse-mcp, 3.0)"
DEFAULT_REASON = "via pulse-mcp"

PERMISSIONS = {
    name: bit
    for bit, name in enumerate(
        """CREATE_INSTANT_INVITE KICK_MEMBERS BAN_MEMBERS ADMINISTRATOR MANAGE_CHANNELS MANAGE_GUILD ADD_REACTIONS
        VIEW_AUDIT_LOG PRIORITY_SPEAKER STREAM VIEW_CHANNEL SEND_MESSAGES SEND_TTS_MESSAGES MANAGE_MESSAGES EMBED_LINKS
        ATTACH_FILES READ_MESSAGE_HISTORY MENTION_EVERYONE USE_EXTERNAL_EMOJIS VIEW_GUILD_INSIGHTS CONNECT SPEAK
        MUTE_MEMBERS DEAFEN_MEMBERS MOVE_MEMBERS USE_VAD CHANGE_NICKNAME MANAGE_NICKNAMES MANAGE_ROLES MANAGE_WEBHOOKS
        MANAGE_GUILD_EXPRESSIONS USE_APPLICATION_COMMANDS REQUEST_TO_SPEAK MANAGE_EVENTS MANAGE_THREADS
        CREATE_PUBLIC_THREADS CREATE_PRIVATE_THREADS USE_EXTERNAL_STICKERS SEND_MESSAGES_IN_THREADS
        USE_EMBEDDED_ACTIVITIES MODERATE_MEMBERS""".split()
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
}

_bot_id: Optional[str] = None


# --------------------------------------------------------------------------
# HTTP helper
# --------------------------------------------------------------------------

async def call(method: str, path: str, *, json_body: Any = None, params: Optional[dict] = None, reason: Optional[str] = None) -> Any:
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise ToolError("DISCORD_BOT_TOKEN is not set on the server")
    headers = {"Authorization": f"Bot {token}", "User-Agent": UA}
    if reason:
        headers["X-Audit-Log-Reason"] = quote(reason)
    async with aiohttp.ClientSession() as session:
        for attempt in range(2):
            async with session.request(
                method, f"{API}{path}", json=json_body, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                text = await resp.text()
                body = json.loads(text) if text else None
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


def allowed_mentions(mode: Optional[str]) -> dict:
    return {"none": {"parse": []}, "all": {"parse": ["users", "roles", "everyone"]}}.get(mode or "users", {"parse": ["users"]})


def sid(description: str) -> dict:
    return {"type": "string", "description": description}


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
        "before": {"type": "string", "description": "Only messages before this message ID (optional)"},
    },
    ["channel_id"],
)
async def read_channel(args):
    limit = max(1, min(int(args.get("limit", 50)), 500))
    before = args.get("before")
    messages: list = []
    while len(messages) < limit:
        params = {"limit": min(100, limit - len(messages))}
        if before:
            params["before"] = before
        batch = await call("GET", f"/channels/{args['channel_id']}/messages", params=params)
        if not batch:
            break
        messages.extend(batch)
        before = batch[-1]["id"]
    return {"channel_id": str(args["channel_id"]), "count": len(messages), "messages": [fmt_message(m) for m in messages]}


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
        clean({"user_id": m["user"]["id"], "username": m["user"]["username"], "nick": m.get("nick"), "bot": m["user"].get("bot") or None, "roles": m["roles"], "joined_at": m.get("joined_at"), "timeout_until": m.get("communication_disabled_until")})
        for m in members
    ]


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
        "content": {"type": "string", "description": "Message text (max 2000 chars)"},
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
    {"channel_id": CHANNEL, "message_id": MESSAGE, "content": {"type": "string"}, "embed": EMBED, "mentions": MENTIONS},
    ["channel_id", "message_id"],
    hint="write",
)
async def edit_message(args):
    body = clean({"content": args.get("content"), "embeds": [args["embed"]] if args.get("embed") else None, "allowed_mentions": allowed_mentions(args.get("mentions"))})
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
    {"channel_id": CHANNEL, "message_ids": {"type": "array", "items": {"type": "string"}, "description": "2-100 message IDs"}, "reason": REASON},
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
    "Pin (default) or unpin a message. Needs Manage Messages.",
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
    {"channel_id": CHANNEL, "message_id": MESSAGE, "emoji": {"type": "string"}},
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
        "emoji": {"type": "string", "description": "Unicode or name:id. Not needed with clear_all."},
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
        t = await call("POST", f"/channels/{cid}/threads", json_body={"name": args["name"], "auto_archive_duration": archive, "message": {"content": args["content"], "allowed_mentions": {"parse": ["users"]}}})
    else:
        t = await call("POST", f"/channels/{cid}/threads", json_body={"name": args["name"], "auto_archive_duration": archive, "type": 12 if args.get("private") else 11})
    return fmt_channel(t)


@tool(
    "discord_thread_member",
    "Manage thread membership: join/leave (the bot), add/remove a user, or list members.",
    {"thread_id": sid("Thread ID"), "action": {"type": "string", "enum": ["join", "leave", "add", "remove", "list"]}, "user_id": sid("Required for add/remove")},
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
    {"guild_id": GUILD, "role_id": ROLE, "name": {"type": "string"}, "permissions": PERM_LIST, "color": {"type": "string", "description": "Hex like #ff8800"}, "hoist": {"type": "boolean"}, "mentionable": {"type": "boolean"}},
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
    await call("PUT" if args["action"] == "add" else "DELETE", f"/guilds/{args['guild_id']}/members/{args['user_id']}/roles/{args['role_id']}", reason=DEFAULT_REASON)
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
            until = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()
        await call("PATCH", f"/guilds/{g}/members/{u}", json_body={"communication_disabled_until": until}, reason=reason)
    else:
        raise ToolError("action must be kick, ban, unban, timeout or untimeout")
    return {"user_id": str(u), "action": action}
