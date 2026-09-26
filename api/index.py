"""capes: your personal MCP server for Gmail, Discord and X/Twitter (via Apify), deployed on Vercel.

- POST /mcp     MCP over HTTP (JSON-RPC), protected by `Authorization: Bearer <MCP_API_KEY>`
- /dashboard    owner dashboard (sign in with the same key)
- GET /health   public health check

Tools live in the pulse/ package (see pulse/discord.py); register new ones with @tool(...).
"""

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pulse import (  # noqa: F401  (importing registers the tools)
    discord,
    gmail,
    security,
    twitter,
)
from pulse.dashboard import router as dashboard_router
from pulse.mcp import handle_rpc, rpc_error
from pulse.registry import TOOLS

load_dotenv()

MAX_BODY = 6_000_000  # Vercel itself caps request bodies at 4.5 MB

app = FastAPI(title="capes", version="4.0", docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(dashboard_router)


@app.middleware("http")
async def harden(request: Request, call_next):
    response = await call_next(request)
    for name, value in security.security_headers(request, response.headers.get("content-type", "")).items():
        response.headers.setdefault(name, value)
    return response


def verify_api_key(authorization: str | None) -> None:
    security.verify_bearer(authorization)


@app.post("/mcp")
async def mcp(request: Request, authorization: str | None = Header(None)):
    verify_api_key(authorization)
    if security.content_length(request) > MAX_BODY:
        raise HTTPException(413, "Request too large")
    try:
        body = await request.json()
    except ValueError:
        return JSONResponse(rpc_error(None, -32700, "Parse error"), status_code=400)

    if isinstance(body, list):
        if not body or len(body) > 50:
            return JSONResponse(rpc_error(None, -32600, "Batch must contain 1-50 requests"), status_code=400)
        results = [r for r in await asyncio.gather(*(handle_rpc(m) for m in body)) if r]
        return JSONResponse(results) if results else Response(status_code=202)
    result = await handle_rpc(body)
    return JSONResponse(result) if result else Response(status_code=202)


@app.get("/")
async def root(request: Request):
    """Browsers go to the dashboard; everything else gets the JSON health check."""
    if "text/html" in request.headers.get("accept", ""):
        return RedirectResponse("/dashboard", status_code=302)
    return await health()


@app.get("/health")
async def health():
    return {
        "status": "online",
        "name": "capes",
        "mcp_endpoint": "/mcp",
        "dashboard": "/dashboard",
        "tools": len(TOOLS),
        "time": datetime.now(UTC).isoformat(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
