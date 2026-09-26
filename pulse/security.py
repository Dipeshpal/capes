"""Authentication, dashboard sessions, CSRF and security headers. Standard library only."""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from urllib.parse import urlparse

from fastapi import HTTPException, Request

MIN_KEY_LENGTH = 24


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
    """The server secret. Refuses to run with a missing or weak key."""
    key = os.getenv("MCP_API_KEY", "")
    if not key:
        raise HTTPException(500, "MCP_API_KEY is not set on the server")
    if len(key) < MIN_KEY_LENGTH:
        raise HTTPException(
            500,
            f"MCP_API_KEY must be at least {MIN_KEY_LENGTH} characters. Generate one with: node -e \"console.log(require('crypto').randomBytes(32).toString('base64url'))\"",
        )
    return key


def verify_bearer(authorization: str | None) -> None:
    """Check `Authorization: Bearer <MCP_API_KEY>` for the /mcp endpoint."""
    expected = api_key()
    if not authorization:
        raise HTTPException(401, "Missing Authorization header")
    scheme, _, supplied = authorization.partition(" ")
    if scheme.lower() != "bearer" or not supplied:
        raise HTTPException(401, "Use the header: Authorization: Bearer <MCP_API_KEY>")
    if not secrets.compare_digest(supplied.strip().encode(), expected.encode()):
        raise HTTPException(403, "Invalid API key")


def key_matches(supplied: str) -> bool:
    return secrets.compare_digest(supplied.encode(), api_key().encode())


# ---------------------------------------------------------------------------
# Sessions and CSRF (stateless, signed with a key derived from MCP_API_KEY)
# ---------------------------------------------------------------------------


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _signing_key() -> bytes:
    return hmac.new(api_key().encode(), b"pulse-dashboard-session-v1", hashlib.sha256).digest()


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
