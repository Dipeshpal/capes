"""MCP protocol, auth and consistency tests. No credentials or network needed.

Run from the repo root:
    uv run --with fastapi --with aiohttp --with python-dotenv --with httpx python tests/protocol.py
"""
import asyncio, os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.pop("DISCORD_BOT_TOKEN", None)
os.environ.pop("APIFY_TOKEN", None)
os.environ.pop("GMAIL_ADDRESS", None)
os.environ.pop("GMAIL_APP_PASSWORD", None)
os.environ["MCP_API_KEY"] = "test-key-123"

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api.index import app, verify_api_key  # noqa: E402
from pulse.discord import PERMISSIONS  # noqa: E402
from pulse.mcp import handle_rpc  # noqa: E402
from pulse.registry import TOOLS, tool  # noqa: E402

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


# ---------------------------------------------------------------- JSON-RPC
r = run(handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}}))
check("initialize echoes supported version", r["result"]["protocolVersion"] == "2025-03-26" and r["result"]["capabilities"] == {"tools": {}}, r)
r = run(handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}}))
check("initialize falls back to latest", r["result"]["protocolVersion"] == "2025-06-18")
check("ping", run(handle_rpc({"jsonrpc": "2.0", "id": 2, "method": "ping"}))["result"] == {})
check("notification gets no reply", run(handle_rpc({"jsonrpc": "2.0", "method": "notifications/initialized"})) is None)
check("unknown method", run(handle_rpc({"jsonrpc": "2.0", "id": 3, "method": "nope"}))["error"]["code"] == -32601)
check("unknown tool", run(handle_rpc({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "nope"}}))["error"]["code"] == -32602)

r = run(handle_rpc({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "discord_read_channel", "arguments": {}}}))
check("missing required argument", r["result"]["isError"] and "channel_id" in r["result"]["content"][0]["text"], r)
r = run(handle_rpc({"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "discord_list_guilds", "arguments": {}}}))
check("missing token is a clear ToolError", r["result"]["isError"] and "DISCORD_BOT_TOKEN" in r["result"]["content"][0]["text"], r)
r = run(handle_rpc({"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "twitter_search", "arguments": {"query": "x"}}}))
check("twitter without token", r["result"]["isError"] and "APIFY_TOKEN" in r["result"]["content"][0]["text"])
r = run(handle_rpc({"jsonrpc": "2.0", "id": 8, "method": "tools/call", "params": {"name": "gmail_search", "arguments": {}}}))
check("gmail without credentials", r["result"]["isError"] and "GMAIL_APP_PASSWORD" in r["result"]["content"][0]["text"])


@tool("zz_boom", "test only", {}, hint="read")
async def _boom(args):
    raise ValueError("kaboom")


r = run(handle_rpc({"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": "zz_boom", "arguments": {}}}))
check("unexpected exception becomes tool error", r["result"]["isError"] and "kaboom" in r["result"]["content"][0]["text"])
del TOOLS["zz_boom"]

# ---------------------------------------------------------------- tool catalogue
specs = [t["spec"] for t in TOOLS.values()]
names = [s["name"] for s in specs]
check("tool names unique and snake_case", len(names) == len(set(names)) and all(re.fullmatch(r"[a-z]+(_[a-z]+)+", n) for n in names), names)
check("every tool has description and object schema", all(s["description"].strip() and s["inputSchema"]["type"] == "object" for s in specs))
check("required args exist in properties", all(set(s["inputSchema"]["required"]) <= set(s["inputSchema"]["properties"]) for s in specs),
      [s["name"] for s in specs if not set(s["inputSchema"]["required"]) <= set(s["inputSchema"]["properties"])])
check("annotations valid", all(s["annotations"] in ({"readOnlyHint": True, "openWorldHint": True}, {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": True}, {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": True}) for s in specs))
risky = [s["name"] for s in specs if re.search(r"delete|trash|spam|moderate|bulk|remove_reaction", s["name"]) and not s["annotations"].get("destructiveHint")]
check("delete/trash/moderation tools are destructive", not risky, risky)
WRITE_VERBS = {"send", "create", "edit", "modify", "pin", "add", "reply", "forward"}
unsafe_reads = [s["name"] for s in specs if WRITE_VERBS & set(s["name"].split("_")) and s["annotations"].get("readOnlyHint")]
check("send/create/edit tools are not read-only", not unsafe_reads, unsafe_reads)
check("id-like properties are strings", all(p.get("type") == "string" for s in specs if s["name"].startswith("discord_") for k, p in s["inputSchema"]["properties"].items() if k.endswith("_id")),
      [(s["name"], k) for s in specs if s["name"].startswith("discord_") for k, p in s["inputSchema"]["properties"].items() if k.endswith("_id") and p.get("type") != "string"])

# ---------------------------------------------------------------- auth
for header, code in ((None, 401), ("Bearer wrong", 403), ("wrong", 403)):
    try:
        verify_api_key(header); check(f"auth rejects {header!r}", False)
    except HTTPException as e:
        check(f"auth rejects {header!r}", e.status_code == code, e.status_code)
check("auth accepts Bearer key", verify_api_key("Bearer test-key-123") is None)
check("auth accepts bare key", verify_api_key("test-key-123") is None)
saved = os.environ.pop("MCP_API_KEY")
try:
    verify_api_key("Bearer x"); check("auth fails closed without server key", False)
except HTTPException as e:
    check("auth fails closed without server key", e.status_code == 500)
os.environ["MCP_API_KEY"] = saved

# ---------------------------------------------------------------- HTTP surface
c = TestClient(app)
h = {"Authorization": "Bearer test-key-123"}
check("health is public", c.get("/").json()["tools"] == len(TOOLS))
check("POST /mcp needs auth", c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"}).status_code == 401)
check("POST /mcp works", c.post("/mcp", headers=h, json={"jsonrpc": "2.0", "id": 1, "method": "ping"}).json() == {"jsonrpc": "2.0", "id": 1, "result": {}})
check("notification returns 202", c.post("/mcp", headers=h, json={"jsonrpc": "2.0", "method": "notifications/initialized"}).status_code == 202)
check("batch", [x["id"] for x in c.post("/mcp", headers=h, json=[{"jsonrpc": "2.0", "id": 1, "method": "ping"}, {"jsonrpc": "2.0", "id": 2, "method": "ping"}]).json()] == [1, 2])
check("bad JSON is a parse error", c.post("/mcp", headers={**h, "Content-Type": "application/json"}, content=b"{nope").status_code == 400)
check("GET /mcp not allowed", c.get("/mcp", headers=h).status_code == 405)
check("tools/list over HTTP", len(c.post("/mcp", headers=h, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).json()["result"]["tools"]) == len(TOOLS))

# ---------------------------------------------------------------- consistency with docs and config
readme = (ROOT / "README.md").read_text(encoding="utf-8")
section = readme.split("## Tools", 1)[1].split("## Check that it works", 1)[0]
documented = set(re.findall(r"\b(?:discord|gmail|twitter)_[a-z_]+\b", section))
check("README tool list equals tools/list", documented == set(names), {"missing_in_readme": sorted(set(names) - documented), "unknown_in_readme": sorted(documented - set(names))})

check(f"README states the tool count ({len(TOOLS)})", f"{len(TOOLS)} tools" in readme, "update the number in README.md")

wanted = ["VIEW_CHANNEL", "SEND_MESSAGES", "SEND_MESSAGES_IN_THREADS", "EMBED_LINKS", "ATTACH_FILES", "READ_MESSAGE_HISTORY", "ADD_REACTIONS", "USE_EXTERNAL_EMOJIS", "MANAGE_MESSAGES", "MANAGE_CHANNELS", "MANAGE_ROLES", "MANAGE_THREADS", "CREATE_PUBLIC_THREADS", "CREATE_PRIVATE_THREADS", "CREATE_INSTANT_INVITE", "KICK_MEMBERS", "BAN_MEMBERS", "MODERATE_MEMBERS"]
integer = str(sum(1 << PERMISSIONS[n] for n in wanted))
for rel in ("docs/discord.md", "scripts/pulse.mjs"):
    check(f"permission integer {integer} present in {rel}", integer in (ROOT / rel).read_text(encoding="utf-8"))

env_used = set()
for f in list((ROOT / "pulse").glob("*.py")) + [ROOT / "api" / "index.py"]:
    env_used |= set(re.findall(r'getenv\("([A-Z_]+)"', f.read_text(encoding="utf-8")))
example = (ROOT / ".env.example").read_text(encoding="utf-8")
check("every env var used in code is in .env.example", all(v in example for v in env_used), sorted(v for v in env_used if v not in example))
import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location("gen_tools_doc", ROOT / "scripts" / "gen_tools_doc.py")
_gen = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_gen)
check("docs/tools.md is up to date (run scripts/gen_tools_doc.py)", (ROOT / "docs" / "tools.md").read_text(encoding="utf-8").splitlines() == _gen.render().splitlines())
vercel_doc = (ROOT / "docs" / "vercel.md").read_text(encoding="utf-8")
check("every env var used in code is in docs/vercel.md", all(v in vercel_doc for v in env_used), sorted(v for v in env_used if v not in vercel_doc))

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
