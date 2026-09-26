"""MCP protocol, auth, validation, policy and consistency tests. No credentials or network needed.

Run from the repo root:
    uv run --with fastapi --with aiohttp --with python-dotenv --with httpx python tests/protocol.py
"""

import asyncio
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
for name in (
    "DISCORD_BOT_TOKEN",
    "APIFY_TOKEN",
    "GMAIL_ADDRESS",
    "GMAIL_APP_PASSWORD",
    "KV_REST_API_URL",
    "KV_REST_API_TOKEN",
    "UPSTASH_REDIS_REST_URL",
    "UPSTASH_REDIS_REST_TOKEN",
    "PULSE_READ_ONLY",
    "PULSE_DISABLED_TOOLS",
    "PULSE_DISABLED_CONNECTORS",
):
    os.environ.pop(name, None)
KEY = "test-key-0123456789-abcdefghijkl"
os.environ["MCP_API_KEY"] = KEY

from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.index import app, verify_api_key
from pulse import store
from pulse.discord import INVITE_PERMISSIONS, PERMISSIONS
from pulse.mcp import handle_rpc, validate_args
from pulse.registry import TOOLS, ToolError, tool

passed = failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print("ok  ", name)
    else:
        failed += 1
        print("FAIL", name, extra)


def run(coro):
    return asyncio.run(coro)


def call(name, arguments=None, req_id=1):
    return run(handle_rpc({"jsonrpc": "2.0", "id": req_id, "method": "tools/call", "params": {"name": name, "arguments": arguments or {}}}))


def listed():
    return {t["name"] for t in run(handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}))["result"]["tools"]}


# ---------------------------------------------------------------- JSON-RPC
r = run(handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}}))
check("initialize echoes supported version", r["result"]["protocolVersion"] == "2025-03-26" and r["result"]["capabilities"] == {"tools": {}}, r)
r = run(handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}}))
check("initialize falls back to latest", r["result"]["protocolVersion"] == "2025-06-18")
check("ping", run(handle_rpc({"jsonrpc": "2.0", "id": 2, "method": "ping"}))["result"] == {})
check("notification gets no reply", run(handle_rpc({"jsonrpc": "2.0", "method": "notifications/initialized"})) is None)
check("unknown method", run(handle_rpc({"jsonrpc": "2.0", "id": 3, "method": "nope"}))["error"]["code"] == -32601)
check("unknown tool", run(handle_rpc({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "nope"}}))["error"]["code"] == -32602)
check("non-object request rejected", run(handle_rpc("hello"))["error"]["code"] == -32600)
check("non-object params rejected", run(handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": []}))["error"]["code"] == -32602)

r = call("discord_read_channel")
check("missing required argument", r["result"]["isError"] and "channel_id" in r["result"]["content"][0]["text"], r)
r = call("discord_list_guilds")
check("missing token is a clear ToolError", r["result"]["isError"] and "DISCORD_BOT_TOKEN" in r["result"]["content"][0]["text"], r)
r = call("twitter_search", {"query": "x"})
check("twitter without token", r["result"]["isError"] and "APIFY_TOKEN" in r["result"]["content"][0]["text"])
r = call("gmail_search")
check("gmail without credentials", r["result"]["isError"] and "GMAIL_APP_PASSWORD" in r["result"]["content"][0]["text"])


@tool("zz_boom", "test only", {}, hint="read")
async def _boom(args):
    raise ValueError("kaboom")


r = call("zz_boom")
check("unexpected exception becomes tool error", r["result"]["isError"] and "kaboom" in r["result"]["content"][0]["text"])
del TOOLS["zz_boom"]

# ---------------------------------------------------------------- secrets never leave in error text
os.environ["APIFY_TOKEN"] = "apify-secret-value-1234567890"
os.environ["GMAIL_APP_PASSWORD"] = "abcdefghijklmnop"
WEBHOOK_URL_ERROR = "connection reset for https://discord.com/api/v10/webhooks/123456789012345678/whTok-EN_secret.value123?wait=true"


@tool("zz_leaky", "test only", {}, hint="read")
async def _leaky(args):
    raise RuntimeError(f"upstream said no to token {os.environ['APIFY_TOKEN']} and password abcd efgh ijkl mnop {WEBHOOK_URL_ERROR}")


@tool("zz_leaky_toolerror", "test only", {}, hint="read")
async def _leaky_toolerror(args):
    raise ToolError(f"bad credentials {os.environ['APIFY_TOKEN']}")


for leaky in ("zz_leaky", "zz_leaky_toolerror"):
    text = call(leaky)["result"]["content"][0]["text"]
    check(
        f"{leaky}: error text has no token, password or webhook token",
        "apify-secret-value" not in text and "abcdefghijklmnop" not in text and "whTok-EN_secret" not in text and "[redacted]" in text,
        text,
    )
check("the URL shape is kept so the error stays useful", "/webhooks/123456789012345678/[redacted]" in call("zz_leaky")["result"]["content"][0]["text"])
acts = run(store.recent_activity(5))[0]
check("activity log errors are redacted too", all("apify-secret-value" not in json.dumps(a) and "whTok-EN" not in json.dumps(a) for a in acts))
del TOOLS["zz_leaky"], TOOLS["zz_leaky_toolerror"]
del os.environ["APIFY_TOKEN"], os.environ["GMAIL_APP_PASSWORD"]

# ---------------------------------------------------------------- argument validation
schema = TOOLS["discord_read_channel"]["spec"]["inputSchema"]
for bad in ("123/../../users/@me", "abc", "1", "12345 ", "12345/messages", "12345?x=1"):
    try:
        validate_args(schema, {"channel_id": bad})
        check(f"snowflake rejects {bad!r}", False)
    except ToolError:
        check(f"snowflake rejects {bad!r}", True)
check("integer ID coerced to string", validate_args(schema, {"channel_id": 1234567890123}) == {"channel_id": "1234567890123"})
check("numeric string coerced to integer", validate_args(schema, {"channel_id": "12345", "limit": "7"}) == {"channel_id": "12345", "limit": 7})
check("unknown arguments dropped", validate_args(schema, {"channel_id": "12345", "evil": 1}) == {"channel_id": "12345"})
for label, args in (("bool as integer", {"channel_id": "12345", "limit": True}), ("list as string", {"channel_id": ["1"]}), ("oversize emoji", None)):
    if args is None:
        try:
            validate_args(TOOLS["discord_add_reaction"]["spec"]["inputSchema"], {"channel_id": "12345", "message_id": "12345", "emoji": "x" * 101})
            check(f"rejects {label}", False)
        except ToolError:
            check(f"rejects {label}", True)
        continue
    try:
        validate_args(schema, args)
        check(f"rejects {label}", False)
    except ToolError:
        check(f"rejects {label}", True)
try:
    validate_args(TOOLS["discord_bulk_delete_messages"]["spec"]["inputSchema"], {"channel_id": "12345", "message_ids": ["12345", "../x"]})
    check("array items validated", False)
except ToolError:
    check("array items validated", True)
try:
    validate_args(TOOLS["discord_create_channel"]["spec"]["inputSchema"], {"guild_id": "12345", "name": "x", "type": "nonsense"})
    check("enum enforced", False)
except ToolError:
    check("enum enforced", True)
r = call("discord_read_channel", {"channel_id": "../users/@me"})
check("bad ID rejected before any network call", r["result"]["isError"] and "invalid format" in r["result"]["content"][0]["text"], r)

from pulse import discord as _discord

os.environ["DISCORD_BOT_TOKEN"] = "dummy-token-never-sent"
for path in ("/channels/1/../../users/@me", "/channels/1?x=y", "/channels/1 2", "/channels/1\r\nX: y", "//evil"):
    try:
        run(_discord.call("GET", path))
        check(f"Discord helper refuses unsafe path {path!r}", False)
    except ToolError as e:
        check(f"Discord helper refuses unsafe path {path!r}", "unsafe" in str(e), str(e))
del os.environ["DISCORD_BOT_TOKEN"]

for bad_name in (["x"], {"a": 1}, 5, None):
    r = run(handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": bad_name}}))
    check(f"unusable tool name {bad_name!r} is a clean error", r.get("error", {}).get("code") == -32602, r)
r = call("discord_send_message", {"channel_id": "12345", "content": "x" * 2001})
check("Discord message longer than 2000 characters is refused before any call", r["result"]["isError"] and "too long" in r["result"]["content"][0]["text"], r)
r = call("twitter_search", {"query": "x" * 501})
check("overlong search query is refused", r["result"]["isError"] and "too long" in r["result"]["content"][0]["text"], r)

# ---------------------------------------------------------------- policy: read-only mode, disabled connectors and tools
os.environ["PULSE_READ_ONLY"] = "1"
kinds_by_name = {n: t["spec"]["annotations"] for n, t in TOOLS.items()}
ro = listed()
check(
    "read-only hides every write/destructive tool", ro == {n for n, a in kinds_by_name.items() if a.get("readOnlyHint")} and 0 < len(ro) < len(TOOLS), len(ro)
)
r = call("gmail_send_email", {"to": ["a@b.co"], "subject": "x", "body": "y"})
check("read-only blocks a write tool at call time", r["result"]["isError"] and "read-only" in r["result"]["content"][0]["text"], r)
del os.environ["PULSE_READ_ONLY"]
os.environ["PULSE_DISABLED_CONNECTORS"] = "discord"
names = listed()
check("disabled connector hides its tools", not any(n.startswith("discord_") for n in names) and any(n.startswith("gmail_") for n in names))
r = call("discord_list_guilds")
check("disabled connector blocks calls", r["result"]["isError"] and "disabled" in r["result"]["content"][0]["text"], r)
del os.environ["PULSE_DISABLED_CONNECTORS"]
os.environ["PULSE_DISABLED_TOOLS"] = "gmail_trash, twitter_search"
names = listed()
check("disabled tools hidden", "gmail_trash" not in names and "twitter_search" not in names and "gmail_search" in names)
del os.environ["PULSE_DISABLED_TOOLS"]
check("everything is back when settings are cleared", listed() == set(TOOLS))

# ---------------------------------------------------------------- tool catalogue
specs = [t["spec"] for t in TOOLS.values()]
names = [s["name"] for s in specs]
check("tool names unique and snake_case", len(names) == len(set(names)) and all(re.fullmatch(r"[a-z]+(_[a-z]+)+", n) for n in names), names)
check("every tool has description and object schema", all(s["description"].strip() and s["inputSchema"]["type"] == "object" for s in specs))
check("required args exist in properties", all(set(s["inputSchema"]["required"]) <= set(s["inputSchema"]["properties"]) for s in specs))
check(
    "annotations valid",
    all(
        s["annotations"]
        in (
            {"readOnlyHint": True, "openWorldHint": True},
            {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": True},
            {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": True},
        )
        for s in specs
    ),
)
risky = [s["name"] for s in specs if re.search(r"delete|trash|spam|moderate|bulk|remove_reaction", s["name"]) and not s["annotations"].get("destructiveHint")]
check("delete/trash/moderation tools are destructive", not risky, risky)
WRITE_VERBS = {"send", "create", "edit", "modify", "pin", "add", "reply", "forward"}
unsafe_reads = [s["name"] for s in specs if WRITE_VERBS & set(s["name"].split("_")) and s["annotations"].get("readOnlyHint")]
check("send/create/edit tools are not read-only", not unsafe_reads, unsafe_reads)
loose_ids = [
    (s["name"], k)
    for s in specs
    if s["name"].startswith("discord_")
    for k, p in s["inputSchema"]["properties"].items()
    if k.endswith("_id") and (p.get("type") != "string" or "pattern" not in p)
]
check("every Discord *_id is a string with a snowflake pattern", not loose_ids, loose_ids)

# ---------------------------------------------------------------- auth
weak = os.environ["MCP_API_KEY"]
for header, code in ((None, 401), ("Bearer wrong", 403), ("wrong", 401), ("Basic abc", 401), ("Bearer", 401), (KEY, 401)):
    try:
        verify_api_key(header)
        check(f"auth rejects {header!r}", False)
    except HTTPException as e:
        check(f"auth rejects {header!r}", e.status_code == code, e.status_code)
check("auth accepts Bearer key", verify_api_key(f"Bearer {KEY}") is None)
check("auth scheme is case-insensitive", verify_api_key(f"bearer {KEY}") is None)
os.environ["MCP_API_KEY"] = "short-key"
try:
    verify_api_key("Bearer short-key")
    check("weak key refused", False)
except HTTPException as e:
    check("weak key refused", e.status_code == 500 and "at least" in e.detail, e.detail)
os.environ.pop("MCP_API_KEY")
try:
    verify_api_key("Bearer x")
    check("auth fails closed without server key", False)
except HTTPException as e:
    check("auth fails closed without server key", e.status_code == 500)
os.environ["MCP_API_KEY"] = weak

# ---------------------------------------------------------------- HTTP surface
c = TestClient(app)
h = {"Authorization": f"Bearer {KEY}"}
check("health is public", c.get("/health").json()["tools"] == len(TOOLS) and c.get("/").json()["status"] == "online")
check("browser hitting / is sent to the dashboard", c.get("/", headers={"accept": "text/html"}, follow_redirects=False).headers.get("location") == "/dashboard")
check("openapi/docs not exposed", c.get("/docs").status_code == 404 and c.get("/openapi.json").status_code == 404)
check("POST /mcp needs auth", c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"}).status_code == 401)
check("POST /mcp works", c.post("/mcp", headers=h, json={"jsonrpc": "2.0", "id": 1, "method": "ping"}).json() == {"jsonrpc": "2.0", "id": 1, "result": {}})
check("notification returns 202", c.post("/mcp", headers=h, json={"jsonrpc": "2.0", "method": "notifications/initialized"}).status_code == 202)
check(
    "batch",
    [x["id"] for x in c.post("/mcp", headers=h, json=[{"jsonrpc": "2.0", "id": 1, "method": "ping"}, {"jsonrpc": "2.0", "id": 2, "method": "ping"}]).json()]
    == [1, 2],
)
check("empty batch rejected", c.post("/mcp", headers=h, json=[]).status_code == 400)
check("oversized batch rejected", c.post("/mcp", headers=h, json=[{"jsonrpc": "2.0", "id": i, "method": "ping"} for i in range(51)]).status_code == 400)
check("bad JSON is a parse error", c.post("/mcp", headers={**h, "Content-Type": "application/json"}, content=b"{nope").status_code == 400)
check("oversized body rejected", c.post("/mcp", headers={**h, "Content-Type": "application/json"}, content=b" " * 6_100_000).status_code == 413)
check("GET /mcp not allowed", c.get("/mcp", headers=h).status_code == 405)
check("tools/list over HTTP", len(c.post("/mcp", headers=h, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).json()["result"]["tools"]) == len(TOOLS))
resp = c.post("/mcp", headers=h, json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
check(
    "security headers on /mcp",
    resp.headers["x-content-type-options"] == "nosniff" and resp.headers["cache-control"] == "no-store" and resp.headers["x-frame-options"] == "DENY",
)
check(
    "activity log records tool names, never arguments", all(set(e) <= {"ts", "tool", "source", "ok", "ms", "error"} for e in run(store.recent_activity(20))[0])
)

# ---------------------------------------------------------------- consistency with docs and config
readme = (ROOT / "README.md").read_text(encoding="utf-8")
section = readme.split("## Tools", 1)[1].split("## Check that it works", 1)[0]
documented = set(re.findall(r"\b(?:discord|gmail|twitter)_[a-z_]+\b", section))
check(
    "README tool list equals tools/list",
    documented == set(names),
    {"missing_in_readme": sorted(set(names) - documented), "unknown_in_readme": sorted(documented - set(names))},
)
check(f"README states the tool count ({len(TOOLS)})", f"{len(TOOLS)} tools" in readme, "update the number in README.md")

wanted = [
    "VIEW_CHANNEL",
    "SEND_MESSAGES",
    "SEND_MESSAGES_IN_THREADS",
    "EMBED_LINKS",
    "ATTACH_FILES",
    "READ_MESSAGE_HISTORY",
    "ADD_REACTIONS",
    "USE_EXTERNAL_EMOJIS",
    "MANAGE_MESSAGES",
    "PIN_MESSAGES",
    "MANAGE_CHANNELS",
    "MANAGE_ROLES",
    "MANAGE_THREADS",
    "CREATE_PUBLIC_THREADS",
    "CREATE_PRIVATE_THREADS",
    "CREATE_INSTANT_INVITE",
    "KICK_MEMBERS",
    "BAN_MEMBERS",
    "MODERATE_MEMBERS",
    "MANAGE_WEBHOOKS",
    "VIEW_AUDIT_LOG",
]
integer = str(sum(1 << PERMISSIONS[n] for n in wanted))
check("dashboard invite constant matches permission list", integer == INVITE_PERMISSIONS)
for rel in ("docs/discord.md", "scripts/capes.mjs"):
    check(f"permission integer {integer} present in {rel}", integer in (ROOT / rel).read_text(encoding="utf-8"))

env_used = set()
for f in [*(ROOT / "pulse").glob("*.py"), ROOT / "api" / "index.py"]:
    env_used |= set(re.findall(r'getenv\("([A-Z_]+)"', f.read_text(encoding="utf-8")))
example = (ROOT / ".env.example").read_text(encoding="utf-8")
check("every env var used in code is in .env.example", all(v in example for v in env_used), sorted(v for v in env_used if v not in example))
_spec = importlib.util.spec_from_file_location("gen_tools_doc", ROOT / "scripts" / "gen_tools_doc.py")
_gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gen)
check(
    "docs/tools.md is up to date (run scripts/gen_tools_doc.py)",
    (ROOT / "docs" / "tools.md").read_text(encoding="utf-8").splitlines() == _gen.render().splitlines(),
)
vercel_doc = (ROOT / "docs" / "vercel.md").read_text(encoding="utf-8")
internal = {"PULSE_REPO_URL", "APIFY_TWEET_ACTOR"}
check(
    "every env var used in code is in docs/vercel.md",
    all(v in vercel_doc for v in env_used if v not in internal),
    sorted(v for v in env_used if v not in vercel_doc and v not in internal),
)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
