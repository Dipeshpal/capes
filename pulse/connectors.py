"""The services capes connects to: what each needs, whether it is configured, and a safe connection test."""

import asyncio
import os
from dataclasses import dataclass

import aiohttp

from .registry import TOOLS, ToolError, kind
from .security import redact

REPO_URL = os.getenv("PULSE_REPO_URL", "https://github.com/Dipeshpal/capes").rstrip("/")


@dataclass(frozen=True)
class Connector:
    id: str
    name: str
    prefix: str
    env: tuple
    guide: str
    summary: str


CONNECTORS = (
    Connector(
        "gmail", "Gmail", "gmail_", ("GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"), "docs/gmail.md", "Search, read, send, reply, forward, drafts, labels, trash."
    ),
    Connector("discord", "Discord", "discord_", ("DISCORD_BOT_TOKEN",), "docs/discord.md", "Read and manage servers, channels, threads, roles and messages."),
    Connector("apify", "Apify (X/Twitter search)", "twitter_", ("APIFY_TOKEN",), "docs/apify.md", "Search tweets through an Apify scraper."),
)
BY_ID = {c.id: c for c in CONNECTORS}


def connector_of(tool_name: str) -> Connector | None:
    return next((c for c in CONNECTORS if tool_name.startswith(c.prefix)), None)


def missing_env(c: Connector) -> list[str]:
    return [name for name in c.env if not os.getenv(name)]


def describe(c: Connector) -> dict:
    tools = sorted(n for n in TOOLS if n.startswith(c.prefix))
    return {
        "id": c.id,
        "name": c.name,
        "summary": c.summary,
        "env": list(c.env),
        "missing_env": missing_env(c),
        "configured": not missing_env(c),
        "guide": f"{REPO_URL}/blob/master/{c.guide}",
        "tools": tools,
        "kinds": {k: sum(1 for n in tools if kind(TOOLS[n]["spec"]) == k) for k in ("read", "write", "destructive")},
    }


async def test_connection(connector_id: str) -> dict:
    """Read-only check that the stored credentials work. Returns {ok, detail}; never raises, never echoes secrets."""
    c = BY_ID.get(connector_id)
    if not c:
        return {"ok": False, "detail": "Unknown connector"}
    if missing_env(c):
        return {"ok": False, "detail": "Missing environment variable(s): " + ", ".join(missing_env(c))}
    try:
        if c.id == "gmail":
            from . import gmail

            def check():
                with gmail.Mailbox() as mb:
                    typ, st = mb.m.status("INBOX", "(MESSAGES UNSEEN)")
                    return st[0].decode() if typ == "OK" and st and st[0] else "connected"

            detail = await asyncio.to_thread(check)
            return {"ok": True, "detail": f"Signed in to Gmail. {detail}"}
        if c.id == "discord":
            from . import discord

            me = await discord.call("GET", "/users/@me")
            guilds = await discord.call("GET", "/users/@me/guilds")
            return {"ok": True, "detail": f"Bot '{me.get('username')}' is in {len(guilds)} server(s)."}
        if c.id == "apify":
            async with (
                aiohttp.ClientSession() as session,
                session.get(
                    "https://api.apify.com/v2/users/me",
                    headers={"Authorization": f"Bearer {os.getenv('APIFY_TOKEN')}"},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp,
            ):
                body = await resp.json(content_type=None)
                if resp.status != 200:
                    return {"ok": False, "detail": f"Apify answered {resp.status}: check the token."}
            data = body.get("data", {})
            return {"ok": True, "detail": f"Apify account '{data.get('username')}' ({(data.get('plan') or {}).get('id', 'plan unknown')})."}
    except ToolError as e:
        return {"ok": False, "detail": redact(str(e))[:300]}
    except Exception as e:
        return {"ok": False, "detail": redact(f"{type(e).__name__}: {e!s}")[:200]}
    return {"ok": False, "detail": "No test available"}
