"""pulse-mcp: your personal MCP server for social accounts, deployed on Vercel.

Speaks MCP over HTTP (JSON-RPC at POST /mcp), protected by a Bearer API key.
Tools live in the pulse/ package (see pulse/discord.py); register new ones with @tool(...).
"""

import asyncio
import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pulse import discord, gmail, twitter  # noqa: E402,F401  (importing registers the tools)
from pulse.mcp import handle_rpc, rpc_error  # noqa: E402
from pulse.registry import TOOLS  # noqa: E402

load_dotenv()

app = FastAPI(title="pulse-mcp", version="3.0")


def verify_api_key(authorization: Optional[str]) -> None:
    expected = os.getenv("MCP_API_KEY")
    if not expected:
        raise HTTPException(500, "MCP_API_KEY is not set on the server")
    if not authorization:
        raise HTTPException(401, "Missing Authorization header")
    supplied = authorization[7:] if authorization.startswith("Bearer ") else authorization
    if not secrets.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(403, "Invalid API key")


@app.post("/mcp")
async def mcp(request: Request, authorization: Optional[str] = Header(None)):
    verify_api_key(authorization)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse(rpc_error(None, -32700, "Parse error"), status_code=400)

    if isinstance(body, list):
        results = [r for r in await asyncio.gather(*(handle_rpc(m) for m in body)) if r]
        return JSONResponse(results) if results else Response(status_code=202)
    result = await handle_rpc(body)
    return JSONResponse(result) if result else Response(status_code=202)


@app.get("/")
async def health():
    return {
        "status": "online",
        "name": "pulse-mcp",
        "mcp_endpoint": "/mcp",
        "tools": len(TOOLS),
        "time": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
