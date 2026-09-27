"""Multiple, labelled, expiring MCP API keys, stored hashed in the database. See pulse/db.py and issue #36/#24.

The legacy single MCP_API_KEY env var keeps working regardless of any of this (see security.verify_bearer);
these are additional keys layered on top, managed from the dashboard's Settings page.
"""

import secrets
from datetime import UTC, datetime, timedelta

from . import db, security

MAX_LABEL = 60


def _row(r: dict) -> dict:
    return {
        "id": str(r["id"]),
        "label": r["label"],
        "created_at": r["created_at"].isoformat(),
        "expires_at": r["expires_at"].isoformat() if r["expires_at"] else None,
        "revoked_at": r["revoked_at"].isoformat() if r["revoked_at"] else None,
    }


async def list_keys() -> list[dict]:
    if not db.configured():
        return []
    rows = await db.fetch("select id, label, created_at, expires_at, revoked_at from api_keys order by created_at desc")
    return [_row(r) for r in rows]


async def create_key(label: str | None, expires_days: int | None) -> dict:
    """Returns the row plus the plaintext key under "key" -- shown once, never stored or retrievable again."""
    if not db.configured():
        raise db.DatabaseUnavailable("Add DATABASE_URL to issue additional API keys")
    key = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(days=expires_days) if expires_days else None
    row = await db.fetchrow(
        "insert into api_keys (label, key_hash, expires_at) values ($1, $2, $3) returning id, label, created_at, expires_at, revoked_at",
        (label or "").strip()[:MAX_LABEL] or None,
        security.hash_key(key),
        expires_at,
    )
    return {**_row(row), "key": key}


async def revoke_key(key_id: str) -> bool:
    if not db.configured():
        raise db.DatabaseUnavailable("No database configured")
    try:
        result = await db.execute("update api_keys set revoked_at = now() where id = $1::uuid and revoked_at is null", key_id)
    except db.DatabaseUnavailable:
        return False
    return result != "UPDATE 0"
