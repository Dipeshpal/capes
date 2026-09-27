"""Connector credential lookup: database first (if configured), env var otherwise.

Every connector module already reads its token by name (e.g. os.getenv("DISCORD_BOT_TOKEN")); this is a drop-in
async replacement so the same name can also live encrypted in the database, without changing how connectors are
configured for anyone still using plain env vars.
"""

import os

from . import db, security


async def get(name: str) -> str | None:
    value = None
    if db.configured():
        try:
            row = await db.fetchrow("select ciphertext, nonce from secrets where name = $1", name)
        except db.DatabaseUnavailable:
            row = None
        if row is not None:
            value = security.decrypt(row["ciphertext"], row["nonce"])
    return value or os.getenv(name)


async def set(name: str, value: str) -> None:
    if not db.configured():
        raise db.DatabaseUnavailable("No database configured; set the credential as an environment variable instead")
    ciphertext, nonce = security.encrypt(value)
    await db.execute(
        "insert into secrets (name, ciphertext, nonce) values ($1, $2, $3) "
        "on conflict (name) do update set ciphertext = $2, nonce = $3, updated_at = now()",
        name,
        ciphertext,
        nonce,
    )


async def clear(name: str) -> None:
    if db.configured():
        await db.execute("delete from secrets where name = $1", name)
