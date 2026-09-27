"""DB-backed credentials: encryption, hashing, and env-fallback behaviour. No real Postgres needed here --
DATABASE_URL stays unset, so pulse/db.py is never actually connected to; these tests cover the parts that work
identically with or without a database (encryption, hashing) and the fallback path when there is none.

Run from the repo root:
    uv run --with fastapi --with aiohttp --with python-dotenv --with cryptography python tests/db_offline.py
"""

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
for name in ("MCP_API_KEY", "ENCRYPTION_KEY", "DATABASE_URL", "DISCORD_BOT_TOKEN"):
    os.environ.pop(name, None)

from pulse import creds, db, security

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


# ---------------------------------------------------------------- encryption

os.environ["ENCRYPTION_KEY"] = "test-encryption-key-not-a-real-secret-value"
ciphertext, nonce = security.encrypt("super-secret-token")
check("encrypt produces bytes ciphertext and nonce", isinstance(ciphertext, bytes) and isinstance(nonce, bytes))
check("ciphertext does not contain the plaintext", b"super-secret-token" not in ciphertext)
check("decrypt recovers the original plaintext", security.decrypt(ciphertext, nonce) == "super-secret-token")

try:
    security.decrypt(ciphertext, os.urandom(12))
    check("decrypt with wrong nonce raises", False)
except Exception:
    check("decrypt with wrong nonce raises", True)

del os.environ["ENCRYPTION_KEY"]
try:
    security.encrypt("x")
    check("encrypt without ENCRYPTION_KEY raises", False)
except Exception:
    check("encrypt without ENCRYPTION_KEY raises", True)

# ---------------------------------------------------------------- hash_key

h1, h2 = security.hash_key("some-api-key"), security.hash_key("some-api-key")
check("hash_key is deterministic", h1 == h2)
check("hash_key differs for different input", security.hash_key("other-key") != h1)
check("hash_key never returns the input itself", "some-api-key" not in h1)

# ---------------------------------------------------------------- creds.get() without a database

check("db.configured() is False with no DATABASE_URL", db.configured() is False)
check("creds.get falls back to the env var when DB is unconfigured", run(creds.get("DISCORD_BOT_TOKEN")) is None)
os.environ["DISCORD_BOT_TOKEN"] = "env-token-value"
check("creds.get returns the env var when set", run(creds.get("DISCORD_BOT_TOKEN")) == "env-token-value")

try:
    run(creds.set("DISCORD_BOT_TOKEN", "x"))
    check("creds.set without a database raises", False)
except db.DatabaseUnavailable:
    check("creds.set without a database raises", True)

# ---------------------------------------------------------------- verify_bearer / key_matches without any key configured

check("key_matches is False when MCP_API_KEY is unset", security.key_matches("anything") is False)

try:
    run(security.verify_bearer("Bearer anything"))
    check("verify_bearer with no key and no DB raises 500", False)
except Exception as e:
    check("verify_bearer with no key and no DB raises 500", getattr(e, "status_code", None) == 500)

# ---------------------------------------------------------------- verify_bearer with the legacy single key

os.environ["MCP_API_KEY"] = "legacy-test-key-0123456789abcdef"
run(security.verify_bearer("Bearer legacy-test-key-0123456789abcdef"))
check("verify_bearer accepts the legacy MCP_API_KEY", True)

try:
    run(security.verify_bearer("Bearer wrong-key-entirely"))
    check("verify_bearer rejects a wrong key", False)
except Exception as e:
    check("verify_bearer rejects a wrong key", getattr(e, "status_code", None) == 403)

check("key_matches accepts the legacy key", security.key_matches("legacy-test-key-0123456789abcdef") is True)

# ---------------------------------------------------------------- apikeys.py / creds.py against a fake in-memory "database"
# No real Postgres here -- db.fetch/fetchrow/execute are replaced with a tiny fake that understands just the
# fixed queries this codebase actually sends, to exercise the calling code's logic (hashing, encryption,
# row shaping, revoked/expired filtering) without needing a live connection.

import uuid
from datetime import UTC, datetime

from pulse import apikeys

_secrets: dict[str, tuple] = {}
_keys: dict[str, dict] = {}


async def fake_fetch(query, *args):
    if "from api_keys" in query:
        return [dict(id=k, **{f: v for f, v in row.items() if f != "id"}) for k, row in sorted(_keys.items(), key=lambda kv: kv[1]["created_at"], reverse=True)]
    raise AssertionError(f"unexpected fetch: {query}")


async def fake_fetchrow(query, *args):
    if query.startswith("insert into api_keys"):
        label, key_hash, expires_at = args
        row = {"id": uuid.uuid4(), "label": label, "key_hash": key_hash, "created_at": datetime.now(UTC), "expires_at": expires_at, "revoked_at": None}
        _keys[str(row["id"])] = row
        return row
    if query.startswith("select ciphertext, nonce from secrets"):
        (name,) = args
        row = _secrets.get(name)
        return {"ciphertext": row[0], "nonce": row[1]} if row else None
    if query.startswith("select 1 from api_keys where key_hash"):
        (key_hash,) = args
        now = datetime.now(UTC)
        for row in _keys.values():
            if row["key_hash"] == key_hash and row["revoked_at"] is None and (row["expires_at"] is None or row["expires_at"] > now):
                return {"ok": 1}
        return None
    raise AssertionError(f"unexpected fetchrow: {query}")


async def fake_execute(query, *args):
    if query.startswith("insert into secrets"):
        name, ciphertext, nonce = args
        _secrets[name] = (ciphertext, nonce)
        return "INSERT 0 1"
    if query.startswith("delete from secrets"):
        (name,) = args
        _secrets.pop(name, None)
        return "DELETE 1"
    if query.startswith("update api_keys set revoked_at"):
        (key_id,) = args
        row = _keys.get(key_id)
        if row is None or row["revoked_at"] is not None:
            return "UPDATE 0"
        row["revoked_at"] = "now"
        return "UPDATE 1"
    raise AssertionError(f"unexpected execute: {query}")


db.fetch, db.fetchrow, db.execute = fake_fetch, fake_fetchrow, fake_execute
db.configured = lambda: True
os.environ["ENCRYPTION_KEY"] = "test-encryption-key-not-a-real-secret-value"

check("creds.get returns None before anything is set", run(creds.get("APIFY_TOKEN")) is None)
run(creds.set("APIFY_TOKEN", "apify-secret-value"))
check("creds.get returns the decrypted value after creds.set", run(creds.get("APIFY_TOKEN")) == "apify-secret-value")
check("the fake secrets table never holds the plaintext", b"apify-secret-value" not in _secrets["APIFY_TOKEN"][0])
run(creds.clear("APIFY_TOKEN"))
check("creds.get returns None after creds.clear", run(creds.get("APIFY_TOKEN")) is None)

created = run(apikeys.create_key("test key", None))
check("create_key returns the plaintext key once", isinstance(created.get("key"), str) and len(created["key"]) > 20)
check("create_key's row never has a hash field", "key_hash" not in created)
listed = run(apikeys.list_keys())
check("list_keys shows the new key without its plaintext", len(listed) == 1 and listed[0]["label"] == "test key" and "key" not in listed[0])
check("the newly issued key validates via verify_bearer's DB path", run(security._db_key_valid(created["key"])) is True)
check("revoke_key revokes an existing key", run(apikeys.revoke_key(created["id"])) is True)
check("revoking the same key again reports not-found", run(apikeys.revoke_key(created["id"])) is False)
check("a revoked key no longer validates", run(security._db_key_valid(created["key"])) is False)
check("revoking an unknown id reports not-found", run(apikeys.revoke_key(str(uuid.uuid4()))) is False)

del os.environ["ENCRYPTION_KEY"]

# ---------------------------------------------------------------- Supabase Direct-connection hint

check("no hint for a normal (pooler-style) DATABASE_URL", db._connect_hint() == "")
os.environ["DATABASE_URL"] = "postgresql://postgres:secret@db.abcdefghijklmnop.supabase.co:5432/postgres"
check("Supabase Direct connection URL gets an actionable hint", "Session pooler" in db._connect_hint() and "IPv6" in db._connect_hint())
os.environ["DATABASE_URL"] = "postgresql://postgres.abcdefgh:secret@aws-0-us-east-1.pooler.supabase.com:5432/postgres"
check("Supabase Session pooler URL gets no hint", db._connect_hint() == "")
del os.environ["DATABASE_URL"]

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
