"""Offline Discord tests: a fake Discord REST server records every request so we can check exactly what each tool sends.

No credentials, no network, and nothing touches a real server. This is the safe way to verify the write tools' request shapes.
Run from the repo root:
    uv run --with fastapi --with aiohttp --with python-dotenv python tests/discord_offline.py
"""

import asyncio
import base64
import json
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["DISCORD_BOT_TOKEN"] = "fake-bot-token-for-tests"

from pulse import discord
from pulse.mcp import run_tool

passed = failed = 0
LOG: list[dict] = []
HITS: dict[str, int] = {}
WEBHOOK_TOKEN = "SECRETWEBHOOKTOKEN-abc123"


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print("ok  ", name)
    else:
        failed += 1
        print("FAIL", name, extra)


MSG = {
    "id": "300000000000000001",
    "channel_id": "100000000000000001",
    "timestamp": "2026-01-01T00:00:00+00:00",
    "edited_timestamp": None,
    "author": {"id": "111111111111111111", "username": "pulsebot"},
    "content": "hi",
    "attachments": [{"url": "https://cdn.example.invalid/f.txt"}],
    "embeds": [],
    "reactions": [{"emoji": {"name": "x"}, "count": 2}],
    "pinned": False,
}
CHANNEL = {"id": "400000000000000001", "name": "c", "type": 0, "position": 0}
ROLE = {"id": "500000000000000001", "name": "r", "color": 0, "position": 1, "hoist": False, "mentionable": False, "managed": False, "permissions": "0"}
FORUM = {
    "id": "600000000000000001",
    "name": "forum",
    "type": 15,
    "available_tags": [{"id": "610000000000000001", "name": "bug", "moderated": False, "emoji_id": None, "emoji_name": None}],
}
HOOK = {
    "id": "700000000000000001",
    "name": "hook",
    "channel_id": "100000000000000001",
    "guild_id": "200000000000000001",
    "user": {"username": "owner"},
    "token": WEBHOOK_TOKEN,
}


def respond(method: str, path: str, query: dict, body):
    """Canned Discord answers. Returns (status, json)."""
    if "99000000000000" in path and HITS.get(path, 0) == 0:
        HITS[path] = 1
        return 429, {"message": "rate limited", "retry_after": 0.01}
    if "880000000000000001" in path:
        return 403, {"message": "Missing Permissions", "code": 50013}
    if "770000000000000001" in path:
        return 502, None  # not JSON
    routes = [
        ("GET", r"/guilds/600000000000000001/scheduled-events", lambda: []),
        (
            "GET",
            r"/guilds/\d+/scheduled-events",
            lambda: [
                {
                    "id": "500000000000000001",
                    "name": "Voice meetup",
                    "scheduled_start_time": "2026-10-01T10:00:00Z",
                    "scheduled_end_time": None,
                    "channel_id": "100000000000000001",
                    "entity_metadata": None,
                    "status": 1,
                    "user_count": 0,
                    "creator": {"username": "private"},
                },
                {
                    "id": "500000000000000002",
                    "name": "External meetup",
                    "scheduled_start_time": "2026-10-02T10:00:00Z",
                    "scheduled_end_time": "2026-10-02T11:00:00Z",
                    "channel_id": None,
                    "entity_metadata": {"location": "Community hall"},
                    "status": 2,
                    "user_count": 12,
                },
            ],
        ),
        ("GET", r"/users/@me", lambda: {"id": "111111111111111111", "username": "pulsebot"}),
        ("POST", r"/users/@me/channels", lambda: {"id": "800000000000000001", "type": 1}),
        ("GET", r"/users/@me/guilds", lambda: [{"id": "200000000000000001", "name": "G"}]),
        ("GET", r"/channels/\d+/messages", lambda: [] if "before" in query else [MSG]),
        ("POST", r"/channels/\d+/messages", lambda: MSG),
        ("GET", r"/channels/\d+/messages/\d+", lambda: MSG),
        ("PATCH", r"/channels/\d+/messages/\d+", lambda: {**MSG, "edited_timestamp": "2026-01-02T00:00:00+00:00"}),
        ("GET", r"/channels/\d+/messages/\d+/reactions/[^/]+", lambda: [{"id": "1", "username": "u1"}]),
        ("GET", r"/channels/600000000000000001", lambda: FORUM),
        ("PATCH", r"/channels/600000000000000001", lambda: {**FORUM, "available_tags": body["available_tags"]}),
        ("GET", r"/channels/\d+", lambda: CHANNEL),
        ("GET", r"/channels/\d+/webhooks", lambda: [HOOK]),
        ("POST", r"/channels/\d+/webhooks", lambda: HOOK),
        ("GET", r"/guilds/\d+/webhooks", lambda: [HOOK]),
        ("GET", r"/webhooks/\d+", lambda: HOOK),
        ("POST", r"/webhooks/\d+/[A-Za-z0-9_\-]+", lambda: MSG),
        (
            "GET",
            r"/guilds/\d+/invites",
            lambda: [{"code": "abc123", "channel": {"name": "gen"}, "inviter": {"username": "owner"}, "uses": 3, "max_uses": 0, "expires_at": None}],
        ),
        (
            "GET",
            r"/guilds/\d+/audit-logs",
            lambda: {
                "users": [{"id": "9", "username": "mod"}],
                "audit_log_entries": [{"id": "1", "action_type": 22, "user_id": "9", "target_id": "5", "reason": "spam", "changes": [{"key": "x"}]}],
            },
        ),
        ("POST", r"/channels/\d+/threads", lambda: {**CHANNEL, "type": 11}),
        ("POST", r"/channels/\d+/messages/\d+/threads", lambda: {**CHANNEL, "type": 11}),
        ("POST", r"/guilds/\d+/channels", lambda: CHANNEL),
        ("PATCH", r"/channels/\d+", lambda: CHANNEL),
        ("DELETE", r"/channels/\d+", lambda: CHANNEL),
        ("POST", r"/channels/\d+/invites", lambda: {"code": "zzz", "expires_at": None}),
        ("POST", r"/guilds/\d+/roles", lambda: ROLE),
        ("PATCH", r"/guilds/\d+/roles/\d+", lambda: ROLE),
    ]
    for m, pattern, make in routes:
        if m == method and re.fullmatch(pattern, path):
            return 200, make()
    return 204, None  # PUT/DELETE and anything else succeed with no content


class FakeDiscord(BaseHTTPRequestHandler):
    def _handle(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        ctype = self.headers.get("Content-Type", "")
        body = json.loads(raw) if raw and ctype.startswith("application/json") else None
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        path = parsed.path.removeprefix("/api/v10")
        LOG.append({"method": self.command, "path": path, "query": query, "headers": dict(self.headers), "json": body, "raw": raw, "ctype": ctype})
        status, payload = respond(self.command, path, query, body)
        self.send_response(status)
        if status == 502:
            self.end_headers()
            self.wfile.write(b"<html>Bad gateway</html>")
            return
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if payload is not None:
            self.wfile.write(json.dumps(payload).encode())

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _handle

    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), FakeDiscord)
threading.Thread(target=server.serve_forever, daemon=True).start()
discord.API = f"http://127.0.0.1:{server.server_address[1]}/api/v10"


def tool(tool_name, /, **args):
    """Run a tool through the real pipeline (validation, policy, handler). Returns (ok, parsed_or_text, requests_made)."""
    start = len(LOG)
    ok, text = asyncio.run(run_tool(tool_name, args))
    return ok, (json.loads(text) if ok and text[:1] in "[{" else text), LOG[start:]


G, C, M, U, R = "200000000000000001", "100000000000000001", "300000000000000001", "900000000000000001", "500000000000000001"

ok, r, reqs = tool("discord_list_scheduled_events", guild_id=G)
check(
    "scheduled events return compact channel and external event fields",
    ok
    and r
    == [
        {"id": R, "name": "Voice meetup", "scheduled_start_time": "2026-10-01T10:00:00Z", "channel_id": C, "status": "scheduled", "user_count": 0},
        {
            "id": "500000000000000002",
            "name": "External meetup",
            "scheduled_start_time": "2026-10-02T10:00:00Z",
            "scheduled_end_time": "2026-10-02T11:00:00Z",
            "location": "Community hall",
            "status": "active",
            "user_count": 12,
        },
    ],
)
check(
    "scheduled events request interested counts with no payload",
    len(reqs) == 1
    and reqs[0]["method"] == "GET"
    and reqs[0]["path"] == f"/guilds/{G}/scheduled-events"
    and reqs[0]["json"] is None
    and reqs[0]["query"] == {"with_user_count": "true"},
)
ok, r, reqs = tool("discord_list_scheduled_events", guild_id="600000000000000001")
check("empty scheduled events", ok and r == [])
for arguments in ({}, {"guild_id": "../bad"}, {"guild_id": True}):
    ok, r, reqs = tool("discord_list_scheduled_events", **arguments)
    check("invalid scheduled event guild ID makes no request", not ok and not reqs)

# ================================================================ transport behaviour
ok, r, reqs = tool("discord_get_message", channel_id=C, message_id=M)
h = reqs[0]["headers"]
check(
    "Authorization is 'Bot <token>' and a Discord-style User-Agent is sent",
    h["Authorization"] == "Bot fake-bot-token-for-tests" and h["User-Agent"].startswith("DiscordBot ("),
)
ok, r, reqs = tool("discord_delete_message", channel_id=C, message_id=M, reason="spam & abuse")
check("audit-log reason header is URL-encoded", reqs[0]["method"] == "DELETE" and reqs[0]["headers"]["X-Audit-Log-Reason"] == "spam%20%26%20abuse")
ok, r, reqs = tool("discord_delete_message", channel_id=C, message_id=M)
check("default audit reason says 'via capes'", unquote(reqs[0]["headers"]["X-Audit-Log-Reason"]) == "via capes")
ok, r, reqs = tool("discord_send_message", channel_id="990000000000000001", content="retry me")
check("a short 429 is retried once, then succeeds", ok and len(reqs) == 2 and reqs[0]["path"] == reqs[1]["path"], (ok, r, len(reqs)))
ok, r, reqs = tool("discord_send_message", channel_id="880000000000000001", content="x")
check("Discord 403 becomes a ToolError with the fix-it hint", not ok and "50013" in r and "Hint: Missing Permissions" in r, r)
ok, r, reqs = tool("discord_send_message", channel_id="770000000000000001", content="x")
check("a non-JSON error page is a clean error, not a crash", not ok and "502" in r and "Traceback" not in r, r)

# ================================================================ messages
ok, r, reqs = tool("discord_send_message", channel_id=C, content="hello")
q = reqs[0]
check(
    "send_message: POST body has content and users-only mentions",
    q["method"] == "POST"
    and q["path"] == f"/channels/{C}/messages"
    and q["json"]["content"] == "hello"
    and q["json"]["allowed_mentions"] == {"parse": ["users"]},
    q["json"],
)
ok, r, reqs = tool("discord_send_message", channel_id=C, content="all", mentions="all")
check("mentions=all allows role and everyone pings only on request", reqs[0]["json"]["allowed_mentions"] == {"parse": ["users", "roles", "everyone"]})
ok, r, reqs = tool("discord_send_message", channel_id=C, content="quiet", mentions="none")
check("mentions=none blocks all pings", reqs[0]["json"]["allowed_mentions"] == {"parse": []})
ok, r, reqs = tool("discord_send_message", channel_id=C, content="re", reply_to_message_id=M, embed={"title": "t"})
check("reply and embed are sent", reqs[0]["json"]["message_reference"] == {"message_id": M} and reqs[0]["json"]["embeds"] == [{"title": "t"}])
ok, r, reqs = tool("discord_edit_message", channel_id=C, message_id=M, content="new")
check("edit_message: PATCH", reqs[0]["method"] == "PATCH" and reqs[0]["path"] == f"/channels/{C}/messages/{M}" and reqs[0]["json"]["content"] == "new")
ok, r, reqs = tool("discord_bulk_delete_messages", channel_id=C, message_ids=[M, "300000000000000002"])
check(
    "bulk delete: POST bulk-delete with the IDs",
    reqs[0]["path"] == f"/channels/{C}/messages/bulk-delete" and reqs[0]["json"]["messages"] == [M, "300000000000000002"],
)
ok, r, reqs = tool("discord_bulk_delete_messages", channel_id=C, message_ids=[M])
check("bulk delete needs at least 2 IDs", not ok and not reqs)
ok, r, reqs = tool("discord_pin_message", channel_id=C, message_id=M)
ok2, r2, reqs2 = tool("discord_pin_message", channel_id=C, message_id=M, unpin=True)
check(
    "pin uses PUT and unpin DELETE on /messages/pins/",
    reqs[0]["method"] == "PUT" and reqs2[0]["method"] == "DELETE" and reqs[0]["path"] == f"/channels/{C}/messages/pins/{M}",
)
ok, r, reqs = tool("discord_add_reaction", channel_id=C, message_id=M, emoji="👍")
check(
    "reaction emoji is percent-encoded in the path",
    (reqs[0]["method"] == "PUT" and reqs[0]["path"].endswith("/reactions/%F0%9F%91%8D/@me")) or "%F0" in reqs[0]["path"],
    reqs[0]["path"],
)
ok, r, reqs = tool("discord_remove_reaction", channel_id=C, message_id=M, emoji="x", user_id=U)
ok2, r2, reqs2 = tool("discord_remove_reaction", channel_id=C, message_id=M, clear_all=True)
check(
    "remove_reaction: specific user, and clear_all",
    reqs[0]["path"].endswith(f"/reactions/x/{U}") and reqs2[0]["path"] == f"/channels/{C}/messages/{M}/reactions" and reqs2[0]["method"] == "DELETE",
)
ok, r, reqs = tool("discord_list_reactions", channel_id=C, message_id=M, emoji="x", limit=10)
check("list_reactions returns usernames", ok and r == [{"id": "1", "username": "u1"}] and reqs[0]["query"] == {"limit": "10"}, r)
ok, r, reqs = tool("discord_get_message", channel_id=C, message_id=M)
check("get_message returns a compact message", ok and r["id"] == MSG["id"] and r["author"] == "pulsebot" and r["reactions"] == [{"emoji": "x", "count": 2}])

# ================================================================ direct messages
ok, r, reqs = tool("discord_send_dm", user_id=U, content="private hello")
check(
    "send_dm opens a DM channel then posts to it, pinging nobody",
    [(q["method"], q["path"]) for q in reqs] == [("POST", "/users/@me/channels"), ("POST", "/channels/800000000000000001/messages")]
    and reqs[0]["json"] == {"recipient_id": U}
    and reqs[1]["json"]["allowed_mentions"] == {"parse": []}
    and reqs[1]["json"]["content"] == "private hello",
    reqs,
)
ok, r, reqs = tool("discord_send_dm", user_id=U)
check("send_dm needs content or embed and makes no call without it", not ok and not reqs)
ok, r, reqs = tool("discord_read_dm", user_id=U, limit=5)
check(
    "read_dm opens the channel and reads its messages",
    reqs[0]["path"] == "/users/@me/channels"
    and reqs[1]["path"] == "/channels/800000000000000001/messages"
    and reqs[1]["query"]["limit"] == "5"
    and ok
    and r["count"] == 1,
    r,
)

# ================================================================ files
data = b"hello file \x00\x01 bytes"
ok, r, reqs = tool(
    "discord_send_file", channel_id=C, filename="report.txt", content_base64=base64.b64encode(data).decode(), mime_type="text/plain", content="see attached"
)
q = reqs[0]
check(
    "send_file: multipart with payload_json and the file bytes",
    ok
    and q["ctype"].startswith("multipart/form-data")
    and b'name="payload_json"' in q["raw"]
    and b'filename="report.txt"' in q["raw"]
    and data in q["raw"]
    and b"text/plain" in q["raw"]
    and b"see attached" in q["raw"],
    q["ctype"],
)
check("send_file returns the attachment URL", ok and r["attachments"] == ["https://cdn.example.invalid/f.txt"], r)
ok, r, reqs = tool("discord_send_file", channel_id="990000000000000002", filename="a.txt", content_base64=base64.b64encode(b"x").decode())
check("a rate-limited upload is rebuilt and retried, not corrupted", ok and len(reqs) == 2 and b'filename="a.txt"' in reqs[1]["raw"], (ok, r))
ok, r, reqs = tool("discord_send_file", channel_id=C, filename="big.bin", content_base64=base64.b64encode(b"a" * 2_500_000).decode())
check("a 2.5 MB file is accepted (the documented limit is 3 MB)", ok and reqs and len(reqs[0]["raw"]) > 2_500_000, r)
for label, args in (
    ("path traversal in filename", {"filename": "../../etc/passwd", "content_base64": "eA=="}),
    ("filename with quote", {"filename": 'a".txt', "content_base64": "eA=="}),
    ("filename with newline", {"filename": "a\r\nX: y.txt", "content_base64": "eA=="}),
    ("invalid base64", {"filename": "a.txt", "content_base64": "!!not base64!!"}),
    ("empty file", {"filename": "a.txt", "content_base64": ""}),
    ("oversized file", {"filename": "big.bin", "content_base64": base64.b64encode(b"a" * 3_000_001).decode()}),
):
    ok, r, reqs = tool("discord_send_file", channel_id=C, **args)
    check(f"send_file refuses {label} before any request", not ok and not reqs, r)

# ================================================================ polls
ok, r, reqs = tool("discord_create_poll", channel_id=C, question="Lunch?", answers=["Pizza", "Sushi", "Salad"], duration_hours=48, allow_multiselect=True)
poll = reqs[0]["json"]["poll"]
check(
    "create_poll sends the native poll object",
    ok
    and poll
    == {
        "question": {"text": "Lunch?"},
        "answers": [{"poll_media": {"text": a}} for a in ("Pizza", "Sushi", "Salad")],
        "duration": 48,
        "allow_multiselect": True,
    },
    poll,
)
ok, r, reqs = tool("discord_create_poll", channel_id=C, question="Q", answers=["a", "b"])
check("poll defaults: 24 hours, single choice", reqs[0]["json"]["poll"]["duration"] == 24 and reqs[0]["json"]["poll"]["allow_multiselect"] is False)
for label, args in (
    ("one answer", {"answers": ["a"]}),
    ("eleven answers", {"answers": [str(i) for i in range(11)]}),
    ("blank answer", {"answers": ["a", " "]}),
    ("answer over 55 chars", {"answers": ["a", "b" * 56]}),
    ("duration 0", {"answers": ["a", "b"], "duration_hours": 0}),
    ("duration 769", {"answers": ["a", "b"], "duration_hours": 769}),
):
    ok, r, reqs = tool("discord_create_poll", channel_id=C, question="Q", **args)
    check(f"create_poll refuses {label}", not ok and not reqs, r)

# ================================================================ forum tags
F = FORUM["id"]
ok, r, reqs = tool("discord_list_forum_tags", channel_id=F)
check("list_forum_tags", ok and r == [{"id": "610000000000000001", "name": "bug"}], r)
ok, r, reqs = tool("discord_list_forum_tags", channel_id=C)
check("list_forum_tags refuses a non-forum channel", not ok and "not a forum" in r, r)
ok, r, reqs = tool("discord_manage_forum_tag", channel_id=F, action="add", name="feature", emoji="✨", moderated=True)
tags = reqs[1]["json"]["available_tags"]
check(
    "add tag keeps existing tags and appends the new one",
    reqs[1]["method"] == "PATCH"
    and tags[0] == {"id": "610000000000000001", "name": "bug", "moderated": False}
    and tags[1] == {"name": "feature", "moderated": True, "emoji_name": "✨"},
    tags,
)
ok, r, reqs = tool("discord_manage_forum_tag", channel_id=F, action="rename", tag_id="610000000000000001", name="defect")
check("rename tag by id", reqs[1]["json"]["available_tags"][0]["name"] == "defect" and reqs[1]["json"]["available_tags"][0]["id"] == "610000000000000001")
ok, r, reqs = tool("discord_manage_forum_tag", channel_id=F, action="remove", tag_id="610000000000000001")
check("remove tag sends an empty list", reqs[1]["json"]["available_tags"] == [])
ok, r, reqs = tool("discord_manage_forum_tag", channel_id=F, action="remove", tag_id="610000000000000009")
check("unknown tag id is refused and nothing is patched", not ok and len(reqs) == 1 and "No tag" in r, r)
ok, r, reqs = tool("discord_manage_forum_tag", channel_id=F, action="add")
check("add without a name is refused", not ok and len(reqs) == 1)
ok, r, reqs = tool("discord_create_thread", channel_id=F, name="Bug report", content="steps...", tag_ids=["610000000000000001"])
check(
    "forum post applies tags",
    reqs[0]["path"] == f"/channels/{F}/threads"
    and reqs[0]["json"]["applied_tags"] == ["610000000000000001"]
    and reqs[0]["json"]["message"]["content"] == "steps...",
    reqs[0]["json"],
)

# ================================================================ webhooks (token stays on the server)
ok, r, reqs = tool("discord_list_webhooks", channel_id=C)
check(
    "list_webhooks omits the token",
    ok and r == [{"id": HOOK["id"], "name": "hook", "channel_id": C, "guild_id": G, "created_by": "owner"}] and WEBHOOK_TOKEN not in json.dumps(r),
    r,
)
ok, r, reqs = tool("discord_list_webhooks", guild_id=G)
check("list_webhooks by server", reqs[0]["path"] == f"/guilds/{G}/webhooks")
ok, r, reqs = tool("discord_list_webhooks")
check("list_webhooks needs a channel or a server", not ok and not reqs)
ok, r, reqs = tool("discord_create_webhook", channel_id=C, name="hook")
check("create_webhook never returns the token", ok and WEBHOOK_TOKEN not in json.dumps(r) and reqs[0]["json"] == {"name": "hook"}, r)
ok, r, reqs = tool("discord_send_webhook_message", webhook_id=HOOK["id"], content="from webhook", username="Announcer")
check(
    "send_webhook_message looks the token up server-side and posts with wait=true",
    [q["method"] for q in reqs] == ["GET", "POST"]
    and reqs[1]["path"] == f"/webhooks/{HOOK['id']}/{WEBHOOK_TOKEN}"
    and reqs[1]["query"] == {"wait": "true"}
    and reqs[1]["json"]["username"] == "Announcer"
    and reqs[1]["json"]["allowed_mentions"] == {"parse": ["users"]},
    reqs,
)
check("...and the token is not in the result", WEBHOOK_TOKEN not in json.dumps(r))
ok, r, reqs = tool("discord_send_webhook_message", webhook_id="880000000000000001", content="x")
check("webhook errors never contain a token", not ok and WEBHOOK_TOKEN not in r and "fake-bot-token" not in r, r)
ok, r, reqs = tool("discord_delete_webhook", webhook_id=HOOK["id"])
check("delete_webhook", reqs[0]["method"] == "DELETE" and reqs[0]["path"] == f"/webhooks/{HOOK['id']}")

# ================================================================ invites and audit log
ok, r, reqs = tool("discord_list_invites", guild_id=G)
check("list_invites is compact", ok and r == [{"code": "abc123", "channel": "gen", "inviter": "owner", "uses": 3}], r)
ok, r, reqs = tool("discord_delete_invite", code="abc-123")
check("delete_invite", reqs[0]["method"] == "DELETE" and reqs[0]["path"] == "/invites/abc-123")
for bad in ("../guilds/1", "abc/def", "a", "abc?x=1"):
    ok, r, reqs = tool("discord_delete_invite", code=bad)
    check(f"delete_invite refuses code {bad!r}", not ok and not reqs)
ok, r, reqs = tool("discord_get_audit_log", guild_id=G, limit=10, user_id=U, action_type=22)
check(
    "audit log query parameters and compact result",
    reqs[0]["query"] == {"limit": "10", "user_id": U, "action_type": "22"}
    and ok
    and r == [{"id": "1", "action_type": 22, "by": "mod", "target_id": "5", "reason": "spam", "changed": ["x"]}],
    (reqs[0]["query"], r),
)

# ================================================================ existing write tools: request shapes
ok, r, reqs = tool("discord_create_channel", guild_id=G, name="ann", type="announcement", topic="t", slowmode_seconds=5)
check(
    "create_channel maps type names and slowmode",
    reqs[0]["json"]["type"] == 5 and reqs[0]["json"]["rate_limit_per_user"] == 5 and reqs[0]["json"]["topic"] == "t",
)
ok, r, reqs = tool("discord_create_channel", guild_id=G, name="secret", private=True)
ov = reqs[1]["json"]["permission_overwrites"]
check(
    "private channel hides from @everyone and keeps the bot in",
    reqs[0]["path"] == "/users/@me"
    and ov[0]["id"] == G
    and ov[0]["type"] == 0
    and int(ov[0]["deny"]) == 1 << 10
    and ov[1]["id"] == "111111111111111111"
    and ov[1]["type"] == 1,
    ov,
)
ok, r, reqs = tool("discord_edit_channel", channel_id=C, name="new", archived=True, locked=True, auto_archive_minutes=60)
check("edit_channel/thread maps fields", reqs[0]["json"] == {"name": "new", "archived": True, "locked": True, "auto_archive_duration": 60}, reqs[0]["json"])
ok, r, reqs = tool("discord_edit_channel", channel_id=C)
check("edit_channel with nothing to change is refused", not ok and not reqs)
ok, r, reqs = tool(
    "discord_set_channel_permission", channel_id=C, target_id=R, target_type="role", allow=["VIEW_CHANNEL", "SEND_MESSAGES"], deny=["ADD_REACTIONS"]
)
b = reqs[0]["json"]
check(
    "channel permission names become bit strings",
    reqs[0]["method"] == "PUT" and b["type"] == 0 and int(b["allow"]) == (1 << 10) | (1 << 11) and int(b["deny"]) == 1 << 6,
    b,
)
ok, r, reqs = tool("discord_set_channel_permission", channel_id=C, target_id=U, target_type="member", allow=["NOT_A_PERMISSION"])
check("unknown permission name is refused by the schema before any request", not ok and "must be one of" in r and not reqs, r)
ok, r, reqs = tool(
    "discord_create_role", guild_id=G, name="mod", permissions=["MANAGE_MESSAGES", "KICK_MEMBERS"], color="#ff8800", hoist=True, mentionable=True
)
b = reqs[0]["json"]
check(
    "create_role: permission bits, colour, flags",
    int(b["permissions"]) == (1 << 13) | (1 << 1) and b["color"] == 0xFF8800 and b["hoist"] and b["mentionable"],
    b,
)
ok, r, reqs = tool("discord_member_role", guild_id=G, user_id=U, role_id=R, action="add")
ok2, r2, reqs2 = tool("discord_member_role", guild_id=G, user_id=U, role_id=R, action="remove")
check(
    "member_role: PUT to add, DELETE to remove",
    reqs[0]["method"] == "PUT" and reqs2[0]["method"] == "DELETE" and reqs[0]["path"] == f"/guilds/{G}/members/{U}/roles/{R}",
)
for action, method, has_body in (("kick", "DELETE", False), ("ban", "PUT", True), ("unban", "DELETE", False)):
    ok, r, reqs = tool("discord_moderate_member", guild_id=G, user_id=U, action=action, reason="because")
    path_ok = reqs[0]["path"] == (f"/guilds/{G}/members/{U}" if action == "kick" else f"/guilds/{G}/bans/{U}")
    check(
        f"moderate {action}: {method} with reason",
        reqs[0]["method"] == method
        and path_ok
        and unquote(reqs[0]["headers"]["X-Audit-Log-Reason"]) == "because"
        and (reqs[0]["json"] is not None) == has_body,
    )
ok, r, reqs = tool("discord_moderate_member", guild_id=G, user_id=U, action="timeout", timeout_minutes=15)
until = reqs[0]["json"]["communication_disabled_until"]
check("timeout sends an ISO time in the future", reqs[0]["method"] == "PATCH" and re.match(r"20\d\d-\d\d-\d\dT", until) is not None)
ok, r, reqs = tool("discord_moderate_member", guild_id=G, user_id=U, action="timeout", timeout_minutes=99999)
check("timeout longer than 28 days refused", not ok and not reqs)
ok, r, reqs = tool("discord_moderate_member", guild_id=G, user_id=U, action="untimeout")
check("untimeout sends null", reqs[0]["json"] == {"communication_disabled_until": None})
ok, r, reqs = tool("discord_thread_member", thread_id=C, action="join")
ok2, r2, reqs2 = tool("discord_thread_member", thread_id=C, action="add", user_id=U)
check(
    "thread membership calls",
    reqs[0]["method"] == "PUT" and reqs[0]["path"] == f"/channels/{C}/thread-members/@me" and reqs2[0]["path"] == f"/channels/{C}/thread-members/{U}",
)
ok, r, reqs = tool("discord_create_invite", channel_id=C, max_age_seconds=3600, max_uses=1)
check(
    "create_invite parameters",
    reqs[0]["json"] == {"max_age": 3600, "max_uses": 1, "temporary": False, "unique": True} and r["url"] == "https://discord.gg/zzz",
    reqs[0]["json"],
)

# ================================================================ nothing leaked anywhere
blob = json.dumps([{k: v for k, v in q.items() if k not in ("raw", "headers")} for q in LOG])
check("the bot token only ever travels in the Authorization header", "fake-bot-token" not in blob)

print(f"\n{passed} passed, {failed} failed  ({len(LOG)} requests recorded by the fake server)")
sys.exit(1 if failed else 0)
