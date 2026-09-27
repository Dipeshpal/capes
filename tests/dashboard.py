"""Dashboard security and behaviour tests. No credentials or network needed (Redis is faked by a local HTTP server).

Run from the repo root:
    uv run --with fastapi --with aiohttp --with python-dotenv --with httpx python tests/dashboard.py
"""

import asyncio
import hashlib
import hmac
import json
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
KEY = "dashboard-test-key-0123456789abcdef"
SECRET_TOKEN = "SECRET-DISCORD-TOKEN-VALUE-987654321"
os.environ["MCP_API_KEY"] = KEY
os.environ["DISCORD_BOT_TOKEN"] = SECRET_TOKEN

from fastapi.testclient import TestClient

from api.index import app
from pulse import db, security, store
from pulse.mcp import handle_rpc
from pulse.registry import TOOLS, tool

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


@tool("zz_read", "test read tool", {"q": {"type": "string"}}, hint="read")
async def _read(args):
    return {"echo": args.get("q")}


@tool("zz_write", "test write tool", {}, hint="write")
async def _write(args):
    return {"done": True}


# ---------------------------------------------------------------- fake Upstash REST server
class FakeRedis(BaseHTTPRequestHandler):
    data: dict = {}
    lists: dict = {}
    fail = False
    seen_auth: list = []

    def do_POST(self):
        FakeRedis.seen_auth.append(self.headers.get("Authorization"))
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if FakeRedis.fail or self.headers.get("Authorization") != "Bearer redis-token":
            self.send_response(500 if FakeRedis.fail else 401)
            self.end_headers()
            self.wfile.write(b'{"error":"nope"}')
            return
        cmd, *a = body
        d, ls = FakeRedis.data, FakeRedis.lists
        if cmd == "GET":
            result = d.get(a[0])
        elif cmd == "SET":
            d[a[0]] = a[1]
            result = "OK"
        elif cmd == "INCR":
            d[a[0]] = int(d.get(a[0], 0)) + 1
            result = d[a[0]]
        elif cmd == "EXPIRE":
            result = 1
        elif cmd == "LPUSH":
            ls.setdefault(a[0], []).insert(0, a[1])
            result = len(ls[a[0]])
        elif cmd == "LTRIM":
            ls[a[0]] = ls.get(a[0], [])[int(a[1]) : int(a[2]) + 1]
            result = "OK"
        elif cmd == "LRANGE":
            result = ls.get(a[0], [])[int(a[1]) : int(a[2]) + 1]
        else:
            result = None
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({"result": result}).encode())

    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), FakeRedis)
threading.Thread(target=server.serve_forever, daemon=True).start()
REDIS_URL = f"http://127.0.0.1:{server.server_address[1]}"


def fresh_client(https=True):
    store.reset_for_tests()
    return TestClient(app, base_url="https://testserver" if https else "http://testserver")


def login(c, key=KEY, **kw):
    return c.post("/dashboard/api/login", json={"key": key}, **kw)


def csrf_of(c):
    return c.get("/dashboard/api/session").json()["csrf"]


def mut(c, method, path, body=None, token=True, **headers):
    h = {"content-type": "application/json", **headers}
    if token:
        h["x-csrf-token"] = csrf_of(c)
    return c.request(method, path, json=body if body is not None else {}, headers=h)


# ================================================================ login and cookies
c = fresh_client()
check("state needs a session", c.get("/dashboard/api/state").status_code == 401)
check("discord invite needs a session", c.get("/dashboard/api/discord-invite").status_code == 401)
check("session endpoint reports signed out without leaking", c.get("/dashboard/api/session").json() == {"authenticated": False, "login_mode": "key"})
r = login(c, "wrong-key-wrong-key-wrong-key-1")
check("wrong key rejected", r.status_code == 403 and not r.cookies)
r = c.post("/dashboard/api/login", json={"key": ["x"]})
check("non-string key rejected", r.status_code == 403)
check("login body must be JSON object", c.post("/dashboard/api/login", content=b"nope", headers={"content-type": "application/json"}).status_code == 400)
check(
    "oversized login body rejected",
    c.post("/dashboard/api/login", content=b" " * 3000, headers={"content-type": "application/json", "content-length": "3000"}).status_code == 413,
)
start = time.monotonic()
r = login(c)
check("login succeeds", r.status_code == 200 and r.json()["authenticated"] and time.monotonic() - start >= 0.35, r.text)
cookie_header = r.headers["set-cookie"]
check(
    "https cookie is __Host-, HttpOnly, Secure, SameSite=Strict, Path=/, no Domain",
    cookie_header.startswith("__Host-pulse_session=")
    and "HttpOnly" in cookie_header
    and "Secure" in cookie_header
    and "samesite=strict" in cookie_header.lower()
    and "Path=/" in cookie_header
    and "domain" not in cookie_header.lower(),
    cookie_header,
)
check("cookie has an 8 hour lifetime", "Max-Age=28800" in cookie_header)
check("session endpoint now authenticated with csrf", c.get("/dashboard/api/session").json()["authenticated"] is True and len(csrf_of(c)) == 40)
check("login response carries csrf, not the key", KEY not in r.text)

cp = fresh_client(https=False)
r = login(cp)
check(
    "http (local dev) cookie is not Secure and not __Host-",
    r.status_code == 200 and r.headers["set-cookie"].startswith("pulse_session=") and "Secure" not in r.headers["set-cookie"],
)

# ================================================================ rate limiting
c = fresh_client()
codes = [login(c, "bad-key-bad-key-bad-key-bad-key").status_code for _ in range(12)]
check("login is rate limited after 10 attempts", codes[:10] == [403] * 10 and codes[10:] == [429, 429], codes)
check("even the right key is blocked while rate limited", login(c).status_code == 429)

# ================================================================ cookie tampering
c = fresh_client()
login(c)
good = c.cookies.get("__Host-pulse_session")
payload, sig = good.split(".")
for label, value in (
    ("flipped signature", payload + "." + sig[:-2] + ("AA" if not sig.endswith("AA") else "BB")),
    ("no signature", payload),
    ("garbage", "x.y"),
    ("empty", ""),
    ("oversized", "a" * 600 + "." + "b" * 10),
    ("other payload same sig", "e30." + sig),
):
    t = fresh_client()
    t.cookies.set("__Host-pulse_session", value)
    check(f"rejects {label}", t.get("/dashboard/api/state").status_code == 401)
expired = security.make_session(now=time.time() - security.SESSION_TTL - 10)
t = fresh_client()
t.cookies.set("__Host-pulse_session", expired)
check("rejects expired session", t.get("/dashboard/api/state").status_code == 401)
os.environ["MCP_API_KEY"] = "another-key-0123456789-abcdefghijklmnop"
check("rotating MCP_API_KEY invalidates sessions", c.get("/dashboard/api/state").status_code == 401)
os.environ["MCP_API_KEY"] = KEY
check("...and they work again with the original key", c.get("/dashboard/api/state").status_code == 200)
os.environ["MCP_API_KEY"] = "short"
check("weak key blocks login", login(fresh_client()).status_code == 500)
os.environ["MCP_API_KEY"] = KEY

# ================================================================ CSRF and origin
c = fresh_client()
login(c)
body = {"read_only": False, "disabled_tools": [], "disabled_connectors": []}
check("no CSRF token -> 403", mut(c, "PUT", "/dashboard/api/settings", body, token=False).status_code == 403)
check("wrong CSRF token -> 403", mut(c, "PUT", "/dashboard/api/settings", body, token=False, **{"x-csrf-token": "0" * 40}).status_code == 403)
check(
    "form content-type -> 415",
    c.put("/dashboard/api/settings", content=b"a=b", headers={"content-type": "application/x-www-form-urlencoded", "x-csrf-token": csrf_of(c)}).status_code
    == 415,
)
check("cross-origin Origin -> 403", mut(c, "PUT", "/dashboard/api/settings", body, origin="https://evil.example").status_code == 403)
check("Sec-Fetch-Site cross-site -> 403", mut(c, "PUT", "/dashboard/api/settings", body, **{"sec-fetch-site": "cross-site"}).status_code == 403)
check("same-origin Origin accepted (reaches storage check)", mut(c, "PUT", "/dashboard/api/settings", body, origin="https://testserver").status_code == 409)
check("cross-origin login blocked", c.post("/dashboard/api/login", json={"key": KEY}, headers={"origin": "https://evil.example"}).status_code == 403)
other = fresh_client()
login(other)
check(
    "a CSRF token from another session is rejected",
    mut(c, "PUT", "/dashboard/api/settings", body, token=False, **{"x-csrf-token": csrf_of(other)}).status_code == 403,
)
for path in ("/dashboard/api/test/gmail", "/dashboard/api/run", "/dashboard/api/logout"):
    check(f"POST {path} requires CSRF", mut(c, "POST", path, {}, token=False).status_code == 403)
check("GET endpoints cannot change state (PUT on state not allowed)", c.put("/dashboard/api/state").status_code == 405)

# ================================================================ state never leaks secrets
c = fresh_client()
login(c)
state = c.get("/dashboard/api/state").json()
blob = json.dumps(state) + json.dumps(c.get("/dashboard/api/activity").json())
check(
    "state has 4 connectors and every tool",
    [x["id"] for x in state["connectors"]] == ["gmail", "discord", "apify", "telegram"] and state["server"]["tools_total"] == len(TOOLS),
)
check("no secret values in state/activity", SECRET_TOKEN not in blob and KEY not in blob and "GMAIL_APP_PASSWORD=" not in blob)
disc = next(x for x in state["connectors"] if x["id"] == "discord")
gm = next(x for x in state["connectors"] if x["id"] == "gmail")
check(
    "configured flags are booleans, env names listed",
    disc["configured"] is True and gm["configured"] is False and gm["missing_env"] == ["GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"],
)
check("state exposes an https MCP URL", state["server"]["mcp_url"] == "https://testserver/mcp")
check("no Redis -> cannot edit, storage env", state["settings"]["can_edit"] is False and state["settings"]["storage"] == "env")
r = mut(c, "POST", "/dashboard/api/test/gmail")
check(
    "test connection for unconfigured connector explains what is missing",
    r.status_code == 200 and r.json()["ok"] is False and "GMAIL_ADDRESS" in r.json()["detail"],
    r.text,
)
check("test connection for unknown connector 404", mut(c, "POST", "/dashboard/api/test/nope").status_code == 404)
check("test result never echoes the token", SECRET_TOKEN not in mut(c, "POST", "/dashboard/api/test/discord").text)

# ================================================================ playground
r = mut(c, "POST", "/dashboard/api/run", {"tool": "zz_read", "arguments": {"q": "hi"}})
check("read-only tool runs from the dashboard", r.status_code == 200 and r.json()["ok"] and '"hi"' in r.json()["output"], r.text)
check("write tool refused", mut(c, "POST", "/dashboard/api/run", {"tool": "zz_write", "arguments": {}}).status_code == 403)
check("destructive tool refused", mut(c, "POST", "/dashboard/api/run", {"tool": "gmail_trash", "arguments": {"ids": [1]}}).status_code == 403)
check("unknown tool 404", mut(c, "POST", "/dashboard/api/run", {"tool": "nope"}).status_code == 404)
r = mut(c, "POST", "/dashboard/api/run", {"tool": "discord_read_channel", "arguments": {"channel_id": "../../x"}})
check("playground applies the same argument validation", r.json()["ok"] is False and "invalid format" in r.json()["output"], r.text)
acts = c.get("/dashboard/api/activity").json()
check(
    "activity shows dashboard runs without arguments",
    acts["source"] == "memory" and acts["entries"][0]["source"] == "dashboard" and "hi" not in json.dumps(acts),
)

# ================================================================ settings with Redis
os.environ["KV_REST_API_URL"] = REDIS_URL
os.environ["KV_REST_API_TOKEN"] = "redis-token"
c = fresh_client()
login(c)
st = c.get("/dashboard/api/state").json()["settings"]
check("Redis configured -> editable, storage kv", st["can_edit"] and st["storage"] == "kv" and not st["degraded"])
check(
    "bad token type rejected",
    mut(c, "PUT", "/dashboard/api/settings", {"read_only": "yes", "disabled_tools": [], "disabled_connectors": []}).status_code == 400,
)
check(
    "unknown tool name rejected",
    mut(c, "PUT", "/dashboard/api/settings", {"read_only": False, "disabled_tools": ["nope"], "disabled_connectors": []}).status_code == 400,
)
check(
    "unknown connector rejected",
    mut(c, "PUT", "/dashboard/api/settings", {"read_only": False, "disabled_tools": [], "disabled_connectors": ["nope"]}).status_code == 400,
)
check(
    "lists must be lists",
    mut(c, "PUT", "/dashboard/api/settings", {"read_only": False, "disabled_tools": "gmail_trash", "disabled_connectors": []}).status_code == 400,
)
r = mut(c, "PUT", "/dashboard/api/settings", {"read_only": False, "disabled_tools": ["gmail_trash"], "disabled_connectors": ["apify"]})
check("settings saved", r.status_code == 200 and r.json()["saved"], r.text)
names = {t["name"] for t in run(handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}))["result"]["tools"]}
check("MCP tools/list reflects saved settings", "gmail_trash" not in names and "twitter_search" not in names and "gmail_search" in names)
r = run(handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "gmail_trash", "arguments": {"ids": [1]}}}))
check("MCP call of a dashboard-disabled tool is refused", r["result"]["isError"] and "disabled by the server owner" in r["result"]["content"][0]["text"])
state = c.get("/dashboard/api/state").json()
check(
    "dashboard state shows the switches",
    next(t for t in state["tools"] if t["name"] == "gmail_trash")["disabled"] and not next(x for x in state["connectors"] if x["id"] == "apify")["enabled"],
)
r = mut(c, "PUT", "/dashboard/api/settings", {"read_only": True, "disabled_tools": [], "disabled_connectors": []})
ro_names = {t["name"] for t in run(handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}))["result"]["tools"]}
check("read-only mode via dashboard hides write tools", r.status_code == 200 and "gmail_send_email" not in ro_names and "gmail_search" in ro_names)
check("settings persisted in Redis as JSON", json.loads(FakeRedis.data["pulse:settings"])["read_only"] is True)
os.environ["PULSE_DISABLED_TOOLS"] = "gmail_search"
store.reset_for_tests()
mut(c, "PUT", "/dashboard/api/settings", {"read_only": False, "disabled_tools": [], "disabled_connectors": []})
st = c.get("/dashboard/api/state").json()
locked = next(t for t in st["tools"] if t["name"] == "gmail_search")
check("environment restrictions cannot be undone from the dashboard", locked["locked"] and not locked["enabled"])
del os.environ["PULSE_DISABLED_TOOLS"]
check("Redis received the bearer token", set(FakeRedis.seen_auth) == {"Bearer redis-token"})
acts = c.get("/dashboard/api/activity").json()
check(
    "activity comes from Redis and holds no arguments",
    acts["source"] == "kv" and all(set(e) <= {"ts", "tool", "source", "ok", "ms", "error"} for e in acts["entries"]),
)

# ---- failure behaviour: fail closed
FakeRedis.data["pulse:settings"] = json.dumps({"read_only": False, "disabled_tools": [], "disabled_connectors": []})
store.reset_for_tests()
FakeRedis.fail = True
pol = run(store.load_policy())
check("Redis down with no cache fails closed (read-only, degraded)", pol.read_only and pol.degraded)
r = run(
    handle_rpc(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "gmail_send_email", "arguments": {"to": ["a@b.co"], "subject": "x", "body": "y"}},
        }
    )
)
check("...so write tools are refused", r["result"]["isError"] and "read-only" in r["result"]["content"][0]["text"])
FakeRedis.fail = False
pol = run(store.load_policy(force=True))
check("recovers when Redis is back", not pol.read_only and not pol.degraded)
FakeRedis.fail = True
store._cache["at"] = 0.0
pol = run(store.load_policy())
check("Redis down after a good read reuses the last known settings", not pol.read_only and pol.degraded)
FakeRedis.fail = False
check(
    "saving while Redis is down reports 409",
    (
        lambda: (
            setattr(FakeRedis, "fail", True),
            mut(c, "PUT", "/dashboard/api/settings", {"read_only": False, "disabled_tools": [], "disabled_connectors": []}).status_code,
        )[1]
    )()
    == 409,
)
FakeRedis.fail = False
del os.environ["KV_REST_API_URL"], os.environ["KV_REST_API_TOKEN"]
store.reset_for_tests()

# ================================================================ headers and static assets
_c = fresh_client()
for _n, _t in (("logo.png", "image/png"), ("favicon.png", "image/png"), ("favicon.ico", "image/x-icon")):
    _r = _c.get("/dashboard/" + _n)
    check(
        f"logo asset {_n} is served as {_t}",
        _r.status_code == 200 and _r.headers["content-type"].startswith(_t) and _r.headers.get("x-content-type-options") == "nosniff",
    )
c = fresh_client()
for path in ("/dashboard", "/dashboard/app.js", "/dashboard/style.css", "/dashboard/api/session", "/health"):
    r = c.get(path)
    check(
        f"security headers on {path}",
        r.headers["x-content-type-options"] == "nosniff"
        and r.headers["x-frame-options"] == "DENY"
        and r.headers["referrer-policy"] == "no-referrer"
        and r.headers["cache-control"] == "no-store"
        and "max-age" in r.headers["strict-transport-security"],
        dict(r.headers),
    )
csp = c.get("/dashboard").headers["content-security-policy"]
check(
    "CSP: default none, self scripts/styles, no inline, no framing, no external",
    all(x in csp for x in ("default-src 'none'", "script-src 'self'", "style-src 'self'", "frame-ancestors 'none'", "base-uri 'none'"))
    and "unsafe" not in csp
    and "http" not in csp,
)
check("http requests get no HSTS", "strict-transport-security" not in fresh_client(https=False).get("/dashboard").headers)
for path in (
    "/dashboard/../pulse/store.py",
    "/dashboard/%2e%2e/pulse/store.py",
    "/dashboard/..%2fpulse%2fstore.py",
    "/dashboard/secret.txt",
    "/dashboard/index.html",
    "/dashboard/api",
):
    check(f"static allow-list: {path} not served", c.get(path).status_code in (404, 405, 307, 308) and "MCP_API_KEY" not in c.get(path).text)

html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
css = (ROOT / "dashboard" / "style.css").read_text(encoding="utf-8")
check(
    "HTML: every script has src (no inline scripts), no inline event handlers or style attributes",
    all("src=" in tag for tag in re.findall(r"<script[^>]*>", html))
    and not re.search(r"<script[^>]*>[^<]+</script>", html)
    and not re.search(r"\son\w+\s*=", html)
    and not re.search(r"\sstyle\s*=", html),
)
check(
    "HTML/JS/CSS load nothing from other origins",
    not re.search(r"(src|href)=\"https?://", html) and not re.search(r"@import|url\(\s*['\"]?https?:", css) and not re.search(r"fetch\(\s*['\"]https?:", js),
)
check(
    "JS never uses innerHTML/eval/document.write",
    not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|\beval\(|new Function|setTimeout\(\s*['\"]", js),
)
check("JS never stores anything in localStorage/sessionStorage/cookies", not re.search(r"localStorage|sessionStorage|document\.cookie", js))

# ================================================================ regressions found in review
from types import SimpleNamespace

from fastapi import HTTPException

c = fresh_client()
login(c)
r = mut(c, "POST", "/dashboard/api/logout", {})
sc = r.headers["set-cookie"].lower()
check(
    "logout overwrites the __Host- cookie (Secure, Path=/, Max-Age=0, HttpOnly, no Domain) so browsers accept the deletion",
    sc.startswith("__host-pulse_session=") and "secure" in sc and "max-age=0" in sc and "path=/" in sc and "httponly" in sc and "domain" not in sc,
    sc,
)
check("...and the session is gone", c.get("/dashboard/api/session").json()["authenticated"] is False)


def forged(exp):
    payload = security._b64(json.dumps({"exp": exp, "n": "x"}).encode())
    sig = security._b64(hmac.new(security._signing_key(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


for bad in ("x", None, True, [1], {}):
    check(f"correctly signed session with exp={bad!r} is rejected, not a crash", security.read_session(forged(bad)) is None)
check("correctly signed session with a future exp is accepted", security.read_session(forged(int(time.time()) + 100)) is not None)


def content_length_status(value):
    try:
        return security.content_length(SimpleNamespace(headers={"content-length": value}))
    except HTTPException as e:
        return e.status_code


check("garbage Content-Length is a 400, not a crash", content_length_status("abc") == 400 and content_length_status("1e9") == 400)
check("negative Content-Length is clamped", content_length_status("-5") == 0)

for value, expected in (("12", 12), ("0", 1), ("-5", 1), ("999", 168), ("abc", 8), ("", 8)):
    os.environ["PULSE_SESSION_HOURS"] = value
    check(f"PULSE_SESSION_HOURS={value!r} gives {expected} hours", security._session_ttl() == expected * 3600)
del os.environ["PULSE_SESSION_HOURS"]
check("default session length is 8 hours", security._session_ttl() == 8 * 3600 and security.SESSION_TTL == 8 * 3600)

store.reset_for_tests()
store._memory_hits.update({f"b{i}": [time.monotonic() - 10_000] for i in range(6000)})
run(store.allow_attempt("new-caller", 10, 900))
check("the in-memory rate-limit table is pruned", len(store._memory_hits) < 10, len(store._memory_hits))
store.reset_for_tests()

# ================================================================ API keys and connector secrets, no database configured
check("db.configured() is False in this test environment", db.configured() is False)
c = fresh_client()
login(c)
r = c.get("/dashboard/api/keys")
check(
    "keys list works without a database, reports db_configured false",
    r.status_code == 200 and r.json() == {"db_configured": False, "degraded": False, "keys": []},
)
check("creating a key without a database is 409", mut(c, "POST", "/dashboard/api/keys", {"label": "test"}).status_code == 409)
check("revoking a key without a database is 409", mut(c, "DELETE", "/dashboard/api/keys/00000000-0000-0000-0000-000000000000").status_code == 409)
check("keys list needs a session", fresh_client().get("/dashboard/api/keys").status_code == 401)
check("creating a key needs CSRF", mut(c, "POST", "/dashboard/api/keys", {"label": "x"}, token=False).status_code == 403)
check("label must be a string", mut(c, "POST", "/dashboard/api/keys", {"label": 5}).status_code == 400)
check("expires_days must be a positive int", mut(c, "POST", "/dashboard/api/keys", {"expires_days": 0}).status_code == 400)
check("expires_days rejects a bool", mut(c, "POST", "/dashboard/api/keys", {"expires_days": True}).status_code == 400)
check("expires_days rejects a float", mut(c, "POST", "/dashboard/api/keys", {"expires_days": 1.5}).status_code == 400)

check("unknown connector 404 for setting secrets", mut(c, "PUT", "/dashboard/api/connectors/nope/secrets", {"values": {"X": "y"}}).status_code == 404)
check(
    "gmail secrets need a database (db-backed like the others now)",
    mut(c, "PUT", "/dashboard/api/connectors/gmail/secrets", {"values": {"GMAIL_ADDRESS": "a@b.com"}}).status_code == 409,
)
check(
    "discord secrets need a database",
    mut(c, "PUT", "/dashboard/api/connectors/discord/secrets", {"values": {"DISCORD_BOT_TOKEN": "x"}}).status_code == 409,
)

# A database that IS configured but unreachable (wrong URL, paused, network blip) must degrade, not crash.
real_configured, real_execute, real_fetch = db.configured, db.execute, db.fetch
db.configured = lambda: True
os.environ["ENCRYPTION_KEY"] = "test-encryption-key-not-a-real-secret-value"


async def unreachable(*a, **kw):
    raise db.DatabaseUnavailable("simulated: could not connect")


db.execute, db.fetch = unreachable, unreachable
check(
    "an unreachable (but configured) database is a 409, not a 500 on connector secrets",
    mut(c, "PUT", "/dashboard/api/connectors/discord/secrets", {"values": {"DISCORD_BOT_TOKEN": "x"}}).status_code == 409,
)
r = c.get("/dashboard/api/keys")
check(
    "an unreachable (but configured) database degrades the keys list to empty, not a 500",
    r.status_code == 200 and r.json() == {"db_configured": True, "degraded": True, "keys": []},
    r.text,
)
db.configured, db.execute, db.fetch = real_configured, real_execute, real_fetch
del os.environ["ENCRYPTION_KEY"]

# ================================================================ dashboard username/password login (DASHBOARD_USER/DASHBOARD_PASSWORD)
os.environ["DASHBOARD_USER"] = "owner"
os.environ["DASHBOARD_PASSWORD"] = "a-fine-dashboard-password"

c = fresh_client()
check(
    "session reports login_mode userpass once DASHBOARD_USER/PASSWORD are set",
    c.get("/dashboard/api/session").json() == {"authenticated": False, "login_mode": "userpass"},
)
check("legacy key login is refused once userpass mode is active", c.post("/dashboard/api/login", json={"key": KEY}).status_code == 403)
check("wrong username is refused", c.post("/dashboard/api/login", json={"username": "nope", "password": "a-fine-dashboard-password"}).status_code == 403)
check("wrong password is refused", c.post("/dashboard/api/login", json={"username": "owner", "password": "wrong-password"}).status_code == 403)
check("non-string username/password is refused, not a crash", c.post("/dashboard/api/login", json={"username": ["x"], "password": 5}).status_code == 403)
r = c.post("/dashboard/api/login", json={"username": "owner", "password": "a-fine-dashboard-password"})
check("correct username/password signs in", r.status_code == 200 and r.json()["authenticated"] and "csrf" in r.json(), r.text)
check("state reachable after userpass login", c.get("/dashboard/api/state").status_code == 200)

os.environ["MCP_API_KEY"] = "a-completely-different-key-0123456789abcdef"
check("rotating MCP_API_KEY does NOT sign out a userpass session (decoupled)", c.get("/dashboard/api/state").status_code == 200)
os.environ["MCP_API_KEY"] = KEY

os.environ["DASHBOARD_PASSWORD"] = "a-different-dashboard-password"
check("rotating DASHBOARD_PASSWORD signs out existing userpass sessions", c.get("/dashboard/api/state").status_code == 401)
os.environ["DASHBOARD_PASSWORD"] = "a-fine-dashboard-password"

os.environ["DASHBOARD_PASSWORD"] = "short"
check(
    "weak DASHBOARD_PASSWORD (<8 chars) is a 500 on login",
    fresh_client().post("/dashboard/api/login", json={"username": "owner", "password": "short"}).status_code == 500,
)

del os.environ["DASHBOARD_USER"]
del os.environ["DASHBOARD_PASSWORD"]
check("without DASHBOARD_USER/PASSWORD, mode reverts to key", fresh_client().get("/dashboard/api/session").json()["login_mode"] == "key")

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
