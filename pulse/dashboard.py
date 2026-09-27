"""Owner dashboard: sign in with MCP_API_KEY (or DASHBOARD_USER/DASHBOARD_PASSWORD), see connectors and tools,
manage credentials and API keys, switch things off, try read-only tools.

Security notes (details in docs/usage/dashboard.md and docs/project/architecture.md):
- The session is a signed, HttpOnly, SameSite=Strict cookie; every state-changing call also needs a per-session CSRF token.
- The API never returns secret values, only whether each variable is set.
- Only read-only tools can be run from the dashboard.
"""

import asyncio
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from . import apikeys, connectors, creds, db, security, store
from .mcp import run_tool, tool_allowed
from .registry import TOOLS, kind

ROOT = Path(__file__).resolve().parent.parent / "dashboard"
ASSETS = {
    "index.html": "text/html; charset=utf-8",
    "app.js": "text/javascript; charset=utf-8",
    "style.css": "text/css; charset=utf-8",
    "logo.png": "image/png",
    "favicon.png": "image/png",
    "favicon.ico": "image/x-icon",
}
LOGIN_ATTEMPTS, LOGIN_WINDOW = 10, 900
MAX_OUTPUT = 60_000

router = APIRouter()


def json_response(request: Request, data, status: int = 200) -> JSONResponse:
    return JSONResponse(data, status_code=status, headers=security.security_headers(request, "application/json"))


async def json_body(request: Request, limit: int = 20_000) -> dict:
    if security.content_length(request) > limit:
        raise HTTPException(413, "Request too large")
    try:
        body = await request.json()
    except ValueError as e:
        raise HTTPException(400, "Invalid JSON") from e
    if not isinstance(body, dict):
        raise HTTPException(400, "Expected a JSON object")
    return body


# ---------------------------------------------------------------------------
# Pages and static files
# ---------------------------------------------------------------------------


@router.get("/dashboard", include_in_schema=False)
async def page(request: Request):
    return _asset(request, "index.html")


@router.get("/dashboard/{name}", include_in_schema=False)
async def asset(request: Request, name: str):
    if name not in ASSETS or name == "index.html":
        raise HTTPException(404, "Not found")
    return _asset(request, name)


def _asset(request: Request, name: str) -> FileResponse:
    return FileResponse(ROOT / name, media_type=ASSETS[name].split(";")[0], headers=security.security_headers(request, ASSETS[name]))


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


@router.get("/dashboard/api/session")
async def session_state(request: Request):
    cookie = security.session_cookie(request)
    mode = security.login_mode()
    if security.read_session(cookie) is None:
        return json_response(request, {"authenticated": False, "login_mode": mode})
    return json_response(request, {"authenticated": True, "csrf": security.csrf_token(cookie), "login_mode": mode})


@router.post("/dashboard/api/login")
async def login(request: Request):
    security.check_same_origin(request)
    if not await store.allow_attempt("login:" + security.client_bucket(request), LOGIN_ATTEMPTS, LOGIN_WINDOW):
        raise HTTPException(429, "Too many attempts. Try again in 15 minutes.")
    body = await json_body(request, 2_000)
    await asyncio.sleep(0.4)  # uniform delay slows guessing
    if security.login_mode() == "userpass":
        username, password = body.get("username"), body.get("password")
        ok = isinstance(username, str) and isinstance(password, str) and security.credentials_match(username, password)
        if not ok:
            raise HTTPException(403, "That username or password is not correct")
    else:
        key = body.get("key")
        if not isinstance(key, str) or not security.key_matches(key):
            raise HTTPException(403, "That key is not correct")
    cookie = security.make_session()
    response = json_response(request, {"authenticated": True, "csrf": security.csrf_token(cookie)})
    response.set_cookie(
        security.cookie_name(request), cookie, max_age=security.SESSION_TTL, httponly=True, samesite="strict", secure=security.is_https(request), path="/"
    )
    return response


@router.post("/dashboard/api/logout")
async def logout(request: Request):
    cookie = security.require_session(request)
    security.require_csrf(request, cookie)
    response = json_response(request, {"authenticated": False})
    # A __Host- cookie can only be overwritten by a Set-Cookie that is also Secure, Path=/ and has no Domain.
    response.set_cookie(security.cookie_name(request), "", max_age=0, expires=0, httponly=True, samesite="strict", secure=security.is_https(request), path="/")
    return response


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------


def _tool_view(name: str, policy: store.Policy) -> dict:
    spec = TOOLS[name]["spec"]
    connector = connectors.connector_of(name)
    return {
        "name": name,
        "connector": connector.id if connector else None,
        "kind": kind(spec),
        "description": spec["description"],
        "schema": spec["inputSchema"],
        "enabled": tool_allowed(name, policy) is None,
        "blocked_reason": tool_allowed(name, policy),
        "locked": name in policy.locked_tools,
        "disabled": name in policy.disabled_tools,
    }


@router.get("/dashboard/api/state")
async def state(request: Request):
    security.require_session(request)
    policy = await store.load_policy()
    tools = [_tool_view(n, policy) for n in sorted(TOOLS)]
    cons = []
    for c in connectors.CONNECTORS:
        info = await connectors.describe(c)
        info["enabled"] = c.id not in policy.disabled_connectors
        info["locked"] = c.id in policy.locked_connectors
        cons.append(info)
    return json_response(
        request,
        {
            "server": {
                "version": "4.0",
                "mcp_url": f"{'https' if security.is_https(request) else 'http'}://{request.headers.get('host', request.url.netloc)}/mcp",
                "tools_total": len(tools),
                "tools_enabled": sum(1 for t in tools if t["enabled"]),
            },
            "settings": {
                "read_only": policy.read_only,
                "read_only_locked": policy.locked_read_only,
                "storage": policy.storage,
                "degraded": policy.degraded,
                "can_edit": store.kv_config() is not None,
                "session_hours": security.SESSION_TTL // 3600,
                "db_configured": db.configured(),
            },
            "connectors": cons,
            "tools": tools,
        },
    )


@router.get("/dashboard/api/activity")
async def activity(request: Request):
    security.require_session(request)
    rows, source = await store.recent_activity(50)
    return json_response(request, {"source": source, "entries": rows})


# ---------------------------------------------------------------------------
# Write endpoints (session + CSRF)
# ---------------------------------------------------------------------------


@router.put("/dashboard/api/settings")
async def save_settings(request: Request):
    cookie = security.require_session(request)
    security.require_csrf(request, cookie)
    body = await json_body(request)
    tools, cons = body.get("disabled_tools", []), body.get("disabled_connectors", [])
    if not isinstance(tools, list) or not isinstance(cons, list) or not isinstance(body.get("read_only", False), bool):
        raise HTTPException(400, "Invalid settings")
    if any(t not in TOOLS for t in tools if isinstance(t, str)) or any(c not in connectors.BY_ID for c in cons if isinstance(c, str)):
        raise HTTPException(400, "Unknown tool or connector name")
    try:
        policy = await store.save_policy(body.get("read_only", False), tools, cons)
    except store.StoreUnavailable as e:
        raise HTTPException(409, str(e)) from e
    return json_response(request, {"saved": True, "read_only": policy.read_only})


@router.post("/dashboard/api/test/{connector_id}")
async def test_connector(request: Request, connector_id: str):
    cookie = security.require_session(request)
    security.require_csrf(request, cookie)
    if connector_id not in connectors.BY_ID:
        raise HTTPException(404, "Unknown connector")
    return json_response(request, await connectors.test_connection(connector_id))


@router.get("/dashboard/api/discord-invite")
async def discord_invite(request: Request):
    """The bot's invite link, built from the configured token (a bot's user ID is its application ID)."""
    security.require_session(request)
    from . import discord

    try:
        me = await discord.call("GET", "/users/@me")
    except Exception as e:
        return json_response(request, {"ok": False, "detail": security.redact(str(e))[:200]})
    client_id = str(me.get("id", ""))
    if not re.fullmatch(discord.SNOWFLAKE, client_id):
        return json_response(request, {"ok": False, "detail": "Discord did not return a valid bot ID"})
    url = f"https://discord.com/oauth2/authorize?client_id={client_id}&scope=bot&permissions={discord.INVITE_PERMISSIONS}"
    return json_response(request, {"ok": True, "url": url, "bot": me.get("username")})


@router.post("/dashboard/api/run")
async def run(request: Request):
    """Run a read-only tool from the dashboard (goes through the same validation and policy as MCP calls)."""
    cookie = security.require_session(request)
    security.require_csrf(request, cookie)
    body = await json_body(request, 60_000)
    name = body.get("tool")
    if name not in TOOLS:
        raise HTTPException(404, "Unknown tool")
    if kind(TOOLS[name]["spec"]) != "read":
        raise HTTPException(403, "Only read-only tools can be run from the dashboard")
    ok, text = await run_tool(name, body.get("arguments") or {}, source="dashboard")
    return json_response(request, {"ok": ok, "output": text[:MAX_OUTPUT], "truncated": len(text) > MAX_OUTPUT})


# ---------------------------------------------------------------------------
# API keys (requires a database; the legacy MCP_API_KEY env var always works regardless)
# ---------------------------------------------------------------------------


@router.get("/dashboard/api/keys")
async def list_keys(request: Request):
    security.require_session(request)
    try:
        keys, degraded = await apikeys.list_keys(), False
    except db.DatabaseUnavailable:
        keys, degraded = [], True
    return json_response(request, {"db_configured": db.configured(), "degraded": degraded, "keys": keys})


@router.post("/dashboard/api/keys")
async def create_key(request: Request):
    cookie = security.require_session(request)
    security.require_csrf(request, cookie)
    body = await json_body(request, 500)
    label = body.get("label")
    expires_days = body.get("expires_days")
    if label is not None and not isinstance(label, str):
        raise HTTPException(400, "label must be a string")
    if expires_days is not None and (not isinstance(expires_days, int) or isinstance(expires_days, bool) or not (0 < expires_days <= 3650)):
        raise HTTPException(400, "expires_days must be a whole number of days between 1 and 3650")
    try:
        row = await apikeys.create_key(label, expires_days)
    except db.DatabaseUnavailable as e:
        raise HTTPException(409, str(e)) from e
    return json_response(request, row, status=201)


@router.delete("/dashboard/api/keys/{key_id}")
async def revoke_key(request: Request, key_id: str):
    cookie = security.require_session(request)
    security.require_csrf(request, cookie)
    try:
        found = await apikeys.revoke_key(key_id)
    except db.DatabaseUnavailable as e:
        raise HTTPException(409, str(e)) from e
    if not found:
        raise HTTPException(404, "Unknown or already-revoked key")
    return json_response(request, {"revoked": True})


# ---------------------------------------------------------------------------
# Connector credentials (requires a database; env vars always work regardless)
# ---------------------------------------------------------------------------


@router.put("/dashboard/api/connectors/{connector_id}/secrets")
async def set_connector_secrets(request: Request, connector_id: str):
    cookie = security.require_session(request)
    security.require_csrf(request, cookie)
    c = connectors.BY_ID.get(connector_id)
    if not c:
        raise HTTPException(404, "Unknown connector")
    if not c.db_backed:
        raise HTTPException(400, f"{c.name} credentials are env-var only for now (see issue #36)")
    if not db.configured():
        raise HTTPException(409, "Add DATABASE_URL to set credentials from the dashboard")
    body = await json_body(request, 4_000)
    values = body.get("values")
    if not isinstance(values, dict) or not values:
        raise HTTPException(400, "Expected a non-empty 'values' object")
    if any(k not in c.env for k in values):
        raise HTTPException(400, f"Unknown field(s) for {c.name}; expected one of {list(c.env)}")
    try:
        for name, value in values.items():
            if value is None or (isinstance(value, str) and not value.strip()):
                await creds.clear(name)
            elif isinstance(value, str):
                await creds.set(name, value.strip())
            else:
                raise HTTPException(400, f"{name} must be a string")
    except db.DatabaseUnavailable as e:
        raise HTTPException(409, str(e)) from e
    return json_response(request, await connectors.describe(c))
