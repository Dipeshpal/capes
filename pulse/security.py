"""Authentication, dashboard sessions, CSRF and security headers. Standard library only."""

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from urllib.parse import urlparse

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException, Request

MIN_KEY_LENGTH = 24
MIN_PASSWORD_LENGTH = 8


def _session_ttl() -> int:
    """Dashboard session length in seconds: PULSE_SESSION_HOURS (1-168), default 8."""
    try:
        hours = int(os.getenv("PULSE_SESSION_HOURS", "8"))
    except ValueError:
        hours = 8
    return min(max(hours, 1), 168) * 3600


SESSION_TTL = _session_ttl()
SESSION_COOKIE = "pulse_session"
SECURE_SESSION_COOKIE = "__Host-pulse_session"

CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
    "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)


def api_key() -> str:
    """The legacy single-key secret. Refuses to run with a weak key; empty means 'no legacy key configured'."""
    key = os.getenv("MCP_API_KEY", "")
    if key and len(key) < MIN_KEY_LENGTH:
        raise HTTPException(
            500,
            f"MCP_API_KEY must be at least {MIN_KEY_LENGTH} characters. Generate one with: node -e \"console.log(require('crypto').randomBytes(32).toString('base64url'))\"",
        )
    return key


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


async def _db_key_valid(supplied: str) -> bool:
    from . import db

    if not db.configured():
        return False
    try:
        row = await db.fetchrow(
            "select 1 from api_keys where key_hash = $1 and revoked_at is null and (expires_at is null or expires_at > now())",
            hash_key(supplied),
        )
    except db.DatabaseUnavailable:
        return False
    return row is not None


async def verify_bearer(authorization: str | None) -> None:
    """Check `Authorization: Bearer <key>` for the /mcp endpoint.

    Accepts either the legacy MCP_API_KEY env var (single key, no DB needed) or any non-revoked, non-expired key
    issued from the dashboard's Settings page (stored hashed in the database). Either path alone is enough.
    """
    if not authorization:
        raise HTTPException(401, "Missing Authorization header")
    scheme, _, supplied = authorization.partition(" ")
    supplied = supplied.strip()
    if scheme.lower() != "bearer" or not supplied:
        raise HTTPException(401, "Use the header: Authorization: Bearer <key>")
    legacy = api_key()
    if legacy and secrets.compare_digest(supplied.encode(), legacy.encode()):
        return
    if await _db_key_valid(supplied):
        return
    if not legacy and not db_configured():
        raise HTTPException(500, "No MCP_API_KEY set and no database configured; see docs/setup/vercel.md")
    raise HTTPException(403, "Invalid API key")


def db_configured() -> bool:
    from . import db

    return db.configured()


SECRET_ENV = (
    "MCP_API_KEY",
    "DISCORD_BOT_TOKEN",
    "APIFY_TOKEN",
    "GMAIL_APP_PASSWORD",
    "TELEGRAM_BOT_TOKEN",
    "KV_REST_API_TOKEN",
    "UPSTASH_REDIS_REST_TOKEN",
    "ENCRYPTION_KEY",
    "DATABASE_URL",
    "DASHBOARD_PASSWORD",
)
_WEBHOOK_TOKEN_IN_URL = re.compile(r"(/webhooks/\d+/)[A-Za-z0-9_\-.]+")


def redact(text: str) -> str:
    """Remove secrets from any text that goes back to a client or into a log.

    Unexpected exceptions can carry request URLs or values; a Discord webhook token is part of its URL. This masks the
    server's own secret values and webhook-token URL segments.
    """
    for name in SECRET_ENV:
        value = os.getenv(name, "").strip().strip("\"'")
        if len(value) >= 8:
            text = text.replace(value, "[redacted]")
            text = text.replace(value.replace(" ", ""), "[redacted]")
    return _WEBHOOK_TOKEN_IN_URL.sub(r"\1[redacted]", text)


def key_matches(supplied: str) -> bool:
    legacy = api_key()
    return bool(legacy) and secrets.compare_digest(supplied.encode(), legacy.encode())


# ---------------------------------------------------------------------------
# Dashboard username/password login (independent of MCP_API_KEY, which then only guards /mcp)
# ---------------------------------------------------------------------------


def dashboard_credentials() -> tuple[str, str] | None:
    """(user, password) if DASHBOARD_USER and DASHBOARD_PASSWORD are both set, else None (legacy MCP_API_KEY login)."""
    user = os.getenv("DASHBOARD_USER", "").strip()
    password = os.getenv("DASHBOARD_PASSWORD", "")
    if not user or not password:
        return None
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(500, f"DASHBOARD_PASSWORD must be at least {MIN_PASSWORD_LENGTH} characters")
    return user, password


def login_mode() -> str:
    """'userpass' if DASHBOARD_USER/DASHBOARD_PASSWORD are configured, else 'key' (legacy MCP_API_KEY login)."""
    return "userpass" if dashboard_credentials() else "key"


def credentials_match(user: str, password: str) -> bool:
    creds = dashboard_credentials()
    if creds is None:
        return False
    expected_user, expected_password = creds
    return secrets.compare_digest(user.encode(), expected_user.encode()) and secrets.compare_digest(password.encode(), expected_password.encode())


# ---------------------------------------------------------------------------
# Encryption for connector credentials stored in the database (AES-256-GCM, key from ENCRYPTION_KEY)
# ---------------------------------------------------------------------------


def _encryption_key() -> bytes:
    key = os.getenv("ENCRYPTION_KEY", "")
    if not key:
        raise HTTPException(500, "ENCRYPTION_KEY is not set on the server; required to store credentials in the database")
    return hashlib.sha256(key.encode()).digest()


def encrypt(plaintext: str) -> tuple[bytes, bytes]:
    """Returns (ciphertext, nonce). Raises if ENCRYPTION_KEY is not set."""
    nonce = secrets.token_bytes(12)
    return AESGCM(_encryption_key()).encrypt(nonce, plaintext.encode(), None), nonce


def decrypt(ciphertext: bytes, nonce: bytes) -> str:
    return AESGCM(_encryption_key()).decrypt(nonce, ciphertext, None).decode()


# ---------------------------------------------------------------------------
# Sessions and CSRF (stateless, signed with a key derived from MCP_API_KEY, or ENCRYPTION_KEY for DB-only deploys)
# ---------------------------------------------------------------------------


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _signing_key() -> bytes:
    creds = dashboard_credentials()
    secret = creds[1] if creds else (api_key() or os.getenv("ENCRYPTION_KEY", ""))
    if not secret:
        raise HTTPException(500, "Set DASHBOARD_USER/DASHBOARD_PASSWORD, MCP_API_KEY or ENCRYPTION_KEY on the server before signing in")
    return hmac.new(secret.encode(), b"pulse-dashboard-session-v1", hashlib.sha256).digest()


def make_session(now: float | None = None) -> str:
    payload = _b64(json.dumps({"exp": int((now or time.time()) + SESSION_TTL), "n": secrets.token_urlsafe(9)}).encode())
    sig = _b64(hmac.new(_signing_key(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def read_session(cookie: str | None, now: float | None = None) -> dict | None:
    """Return the session payload if the cookie is genuine and unexpired, else None."""
    if not cookie or cookie.count(".") != 1 or len(cookie) > 512:
        return None
    try:
        payload, sig = cookie.split(".")
        expected = _b64(hmac.new(_signing_key(), payload.encode(), hashlib.sha256).digest())
        if not secrets.compare_digest(sig.encode(), expected.encode()):
            return None
        data = json.loads(_unb64(payload))
    except (ValueError, HTTPException):
        return None
    exp = data.get("exp") if isinstance(data, dict) else None
    if isinstance(exp, bool) or not isinstance(exp, int | float) or exp < (now or time.time()):
        return None
    return data


def content_length(request: Request) -> int:
    """The declared request size; a malformed header is a client error, not a crash."""
    try:
        return max(0, int(request.headers.get("content-length") or 0))
    except ValueError as e:
        raise HTTPException(400, "Invalid Content-Length header") from e


def csrf_token(cookie: str) -> str:
    return hmac.new(_signing_key(), b"csrf:" + cookie.encode(), hashlib.sha256).hexdigest()[:40]


def is_https(request: Request) -> bool:
    return request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip() == "https"


def cookie_name(request: Request) -> str:
    return SECURE_SESSION_COOKIE if is_https(request) else SESSION_COOKIE


def session_cookie(request: Request) -> str | None:
    return request.cookies.get(cookie_name(request))


def client_bucket(request: Request) -> str:
    """Privacy-preserving identifier of the caller for rate limiting."""
    ip = request.headers.get("x-vercel-forwarded-for") or request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")
    return hashlib.sha256(ip.split(",")[0].strip().encode()).hexdigest()[:24]


def check_same_origin(request: Request) -> None:
    """Reject cross-site requests (defence in depth on top of SameSite=Strict and the CSRF token)."""
    site = request.headers.get("sec-fetch-site")
    if site and site not in ("same-origin", "none"):
        raise HTTPException(403, "Cross-site request blocked")
    origin = request.headers.get("origin")
    if origin and urlparse(origin).netloc != request.headers.get("host", ""):
        raise HTTPException(403, "Cross-origin request blocked")


def require_session(request: Request) -> str:
    cookie = session_cookie(request)
    if read_session(cookie) is None:
        raise HTTPException(401, "Not signed in")
    return cookie  # type: ignore[return-value]


def require_csrf(request: Request, cookie: str) -> None:
    """For every state-changing dashboard call: same origin, JSON body type, and the per-session token."""
    check_same_origin(request)
    if not request.headers.get("content-type", "").lower().startswith("application/json"):
        raise HTTPException(415, "Content-Type must be application/json")
    supplied = request.headers.get("x-csrf-token", "")
    if not secrets.compare_digest(supplied.encode(), csrf_token(cookie).encode()):
        raise HTTPException(403, "Missing or invalid CSRF token")


def security_headers(request: Request, content_type: str) -> dict[str, str]:
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        "Cache-Control": "no-store",
    }
    if content_type.startswith("text/html"):
        headers["Content-Security-Policy"] = CSP
    if is_https(request):
        headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return headers
