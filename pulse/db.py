"""Optional Postgres (bring-your-own: Supabase, Neon, any Postgres URL) for credentials and API keys.

Without DATABASE_URL, capes runs exactly as before: connector credentials come from env vars, and the single
MCP_API_KEY env var is the only key. With DATABASE_URL set, connector credentials can live in the database
(encrypted with ENCRYPTION_KEY) and multiple MCP API keys can be issued, labelled and expired from the dashboard.

Runs on Fluid Compute, which reuses warm instances, so a small module-level connection pool is safe here -- it is
not the one-connection-per-request pattern that breaks classic serverless.
"""

import os
from pathlib import Path

import asyncpg

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

_pool: asyncpg.Pool | None = None
_migrated = False


def configured() -> bool:
    return bool(os.getenv("DATABASE_URL"))


class DatabaseUnavailable(Exception):
    """Raised when a feature needs the database and it is not configured or not reachable."""


async def pool() -> asyncpg.Pool:
    global _pool
    if not configured():
        raise DatabaseUnavailable("DATABASE_URL is not set")
    try:
        if _pool is None:
            _pool = await asyncpg.create_pool(os.getenv("DATABASE_URL"), min_size=0, max_size=5, command_timeout=10)
        if not _migrated:
            await _migrate(_pool)
    except (OSError, asyncpg.PostgresError) as e:
        raise DatabaseUnavailable("Could not connect to the database") from e
    return _pool


async def _migrate(p: asyncpg.Pool) -> None:
    global _migrated
    async with p.acquire() as conn:
        await conn.execute("create table if not exists schema_migrations (version int primary key, applied_at timestamptz not null default now())")
        applied = {r["version"] for r in await conn.fetch("select version from schema_migrations")}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = int(path.name.split("_", 1)[0])
            if version in applied:
                continue
            sql = path.read_text(encoding="utf-8")
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute("insert into schema_migrations (version) values ($1)", version)
    _migrated = True


async def fetch(query: str, *args):
    try:
        p = await pool()
        async with p.acquire() as conn:
            return await conn.fetch(query, *args)
    except DatabaseUnavailable:
        raise
    except (OSError, asyncpg.PostgresError) as e:
        raise DatabaseUnavailable("Database query failed") from e


async def fetchrow(query: str, *args):
    try:
        p = await pool()
        async with p.acquire() as conn:
            return await conn.fetchrow(query, *args)
    except DatabaseUnavailable:
        raise
    except (OSError, asyncpg.PostgresError) as e:
        raise DatabaseUnavailable("Database query failed") from e


async def execute(query: str, *args):
    try:
        p = await pool()
        async with p.acquire() as conn:
            return await conn.execute(query, *args)
    except DatabaseUnavailable:
        raise
    except (OSError, asyncpg.PostgresError) as e:
        raise DatabaseUnavailable("Database query failed") from e


def reset_for_tests() -> None:
    global _pool, _migrated
    _pool, _migrated = None, False
