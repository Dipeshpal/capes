"""Owner settings, activity log and rate limiting.

Settings come from two places, merged so the stricter answer always wins:
  1. Environment variables (always available, locked in the dashboard):
       PULSE_READ_ONLY=1, PULSE_DISABLED_CONNECTORS=discord,apify, PULSE_DISABLED_TOOLS=discord_delete_channel,...
  2. Optional Redis (Upstash via the Vercel Marketplace, free) so the dashboard can change them live.
     Recognised variables: KV_REST_API_URL + KV_REST_API_TOKEN, or UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN.

If Redis is configured but unreachable, the last known settings are used; with none cached the server fails closed
(read-only) rather than silently allowing writes.
"""

import json
import os
import time
from collections import deque
from dataclasses import dataclass, field

import aiohttp

SETTINGS_KEY = "pulse:settings"
ACTIVITY_KEY = "pulse:activity"
CACHE_TTL = 10.0
ACTIVITY_MAX = 100
MAX_LIST = 500

_memory_activity: deque = deque(maxlen=ACTIVITY_MAX)
_memory_hits: dict[str, list[float]] = {}
_cache: dict = {"policy": None, "at": 0.0}


class StoreUnavailable(Exception):
    """Raised when a feature needs Redis and it is not configured or not reachable."""


@dataclass(frozen=True)
class Policy:
    read_only: bool = False
    disabled_tools: frozenset = frozenset()
    disabled_connectors: frozenset = frozenset()
    locked_read_only: bool = False
    locked_tools: frozenset = frozenset()
    locked_connectors: frozenset = frozenset()
    storage: str = "env"  # "env" or "kv"
    degraded: bool = False
    extra: dict = field(default_factory=dict)


def kv_config() -> tuple[str, str] | None:
    url = os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL")
    token = os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN")
    return (url.rstrip("/"), token) if url and token else None


def _csv(name: str) -> frozenset:
    return frozenset(x.strip() for x in os.getenv(name, "").split(",") if x.strip())


def env_policy() -> Policy:
    read_only = os.getenv("PULSE_READ_ONLY", "").strip().lower() in ("1", "true", "yes", "on")
    tools, connectors = _csv("PULSE_DISABLED_TOOLS"), _csv("PULSE_DISABLED_CONNECTORS")
    return Policy(
        read_only=read_only,
        disabled_tools=tools,
        disabled_connectors=connectors,
        locked_read_only=read_only,
        locked_tools=tools,
        locked_connectors=connectors,
    )


async def kv_command(*args):
    cfg = kv_config()
    if not cfg:
        raise StoreUnavailable("Redis is not configured")
    url, token = cfg
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.post(url, json=list(args), headers={"Authorization": f"Bearer {token}"}, timeout=aiohttp.ClientTimeout(total=3)) as resp,
        ):
            data = await resp.json(content_type=None)
    except (TimeoutError, aiohttp.ClientError, ValueError) as e:
        raise StoreUnavailable("Redis is not reachable") from e
    if resp.status != 200 or not isinstance(data, dict) or "error" in data:
        raise StoreUnavailable("Redis rejected the request")
    return data.get("result")


def _clean_names(value) -> frozenset:
    if not isinstance(value, list):
        return frozenset()
    return frozenset(str(x)[:80] for x in value[:MAX_LIST] if isinstance(x, str))


def _merge(env: Policy, stored: dict) -> Policy:
    return Policy(
        read_only=env.read_only or bool(stored.get("read_only")),
        disabled_tools=env.disabled_tools | _clean_names(stored.get("disabled_tools")),
        disabled_connectors=env.disabled_connectors | _clean_names(stored.get("disabled_connectors")),
        locked_read_only=env.locked_read_only,
        locked_tools=env.locked_tools,
        locked_connectors=env.locked_connectors,
        storage="kv",
    )


async def load_policy(force: bool = False) -> Policy:
    """Effective policy = environment restrictions + stored settings (cached for a few seconds)."""
    env = env_policy()
    if not kv_config():
        return env
    now = time.monotonic()
    cached = _cache["policy"]
    if not force and cached is not None and now - _cache["at"] < CACHE_TTL:
        return cached
    try:
        raw = await kv_command("GET", SETTINGS_KEY)
        policy = _merge(env, json.loads(raw) if raw else {})
    except (StoreUnavailable, ValueError):
        if cached is not None:
            return Policy(**{**cached.__dict__, "degraded": True})
        return Policy(**{**_merge(env, {"read_only": True}).__dict__, "degraded": True})
    _cache.update(policy=policy, at=now)
    return policy


async def save_policy(read_only: bool, disabled_tools: list, disabled_connectors: list) -> Policy:
    if not kv_config():
        raise StoreUnavailable("Add Redis (see docs/dashboard.md) to change settings from the dashboard")
    payload = {
        "read_only": bool(read_only),
        "disabled_tools": sorted(_clean_names(disabled_tools)),
        "disabled_connectors": sorted(_clean_names(disabled_connectors)),
    }
    await kv_command("SET", SETTINGS_KEY, json.dumps(payload))
    return await load_policy(force=True)


async def record_activity(entry: dict) -> None:
    """Keep the last calls (tool name, time, outcome, duration). Never arguments or results."""
    _memory_activity.appendleft(entry)
    if kv_config():
        try:
            await kv_command("LPUSH", ACTIVITY_KEY, json.dumps(entry))
            await kv_command("LTRIM", ACTIVITY_KEY, 0, ACTIVITY_MAX - 1)
        except StoreUnavailable:
            pass


async def recent_activity(limit: int = 50) -> tuple[list, str]:
    if kv_config():
        try:
            rows = await kv_command("LRANGE", ACTIVITY_KEY, 0, limit - 1)
            return [json.loads(r) for r in rows or []], "kv"
        except (StoreUnavailable, ValueError):
            pass
    return list(_memory_activity)[:limit], "memory"


async def allow_attempt(bucket: str, limit: int, window: int) -> bool:
    """Count an attempt; return False once `limit` attempts happened within `window` seconds."""
    if kv_config():
        try:
            key = f"pulse:rl:{bucket}"
            count = await kv_command("INCR", key)
            if count == 1:
                await kv_command("EXPIRE", key, window)
            return int(count) <= limit
        except StoreUnavailable:
            pass
    now = time.monotonic()
    if len(_memory_hits) > 5000:  # bound memory: forget callers with no recent attempts
        for key in [k for k, v in _memory_hits.items() if not v or now - v[-1] >= window]:
            del _memory_hits[key]
    hits = [t for t in _memory_hits.get(bucket, []) if now - t < window]
    hits.append(now)
    _memory_hits[bucket] = hits
    return len(hits) <= limit


def reset_for_tests() -> None:
    _memory_activity.clear()
    _memory_hits.clear()
    _cache.update(policy=None, at=0.0)
