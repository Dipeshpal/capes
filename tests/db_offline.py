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

from pulse import creds, db, security  # noqa: E402

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

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
