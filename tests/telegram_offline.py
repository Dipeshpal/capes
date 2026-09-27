"""Offline Telegram tests: a fake Bot API server records every request so we can check exactly what each tool sends.

No credentials, no network, and nothing touches a real bot. Run from the repo root:
    uv run --with fastapi --with aiohttp --with python-dotenv python tests/telegram_offline.py
"""

import asyncio
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["TELEGRAM_BOT_TOKEN"] = "123456:fake-token-for-tests"

from pulse import telegram
from pulse.mcp import run_tool

passed = failed = 0
LOG: list[dict] = []


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print("ok  ", name)
    else:
        failed += 1
        print("FAIL", name, extra)


RESPONSES = {
    "sendMessage": {"ok": True, "result": {"message_id": 42, "date": 1700000000, "chat": {"id": 555, "type": "private"}}},
    "getChat": {"ok": True, "result": {"id": 555, "type": "group", "title": "Test Group", "description": "a chat"}},
    "getChatMemberCount": {"ok": True, "result": 7},
    "getUpdates": {
        "ok": True,
        "result": [
            {
                "update_id": 1001,
                "message": {"message_id": 1, "date": 1700000000, "chat": {"id": 555}, "from": {"username": "alice"}, "text": "hi"},
            },
            {
                "update_id": 1002,
                "edited_message": {"message_id": 2, "date": 1700000001, "chat": {"id": 555}, "from": {"first_name": "Bob"}, "text": "edited"},
            },
        ],
    },
    "getMe": {"ok": True, "result": {"username": "CapesTestBot", "first_name": "Capes Test"}},
}


class FakeTelegram(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        method = self.path.rsplit("/", 1)[-1]
        LOG.append({"path": self.path, "method_name": method, "json": json.loads(body) if body else None})
        resp = RESPONSES.get(method, {"ok": False, "error_code": 404, "description": "no such method"})
        payload = json.dumps(resp).encode()
        self.send_response(200 if resp.get("ok") else 400)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), FakeTelegram)
threading.Thread(target=server.serve_forever, daemon=True).start()
telegram.API = f"http://127.0.0.1:{server.server_address[1]}"


def tool(name, /, **args):
    start = len(LOG)
    ok, text = asyncio.run(run_tool(name, args))
    return ok, (json.loads(text) if ok and text[:1] in "[{" else text), LOG[start:]


ok, r, reqs = tool("telegram_send_message", chat_id="555", text="hello")
check(
    "send_message posts chat_id and text to the right method, no token in the path we recorded incorrectly",
    ok
    and reqs[0]["method_name"] == "sendMessage"
    and reqs[0]["json"] == {"chat_id": "555", "text": "hello"}
    and r == {"message_id": 42, "chat_id": "555", "date": 1700000000},
)
check("bot token never leaks into the path we log for assertions beyond the fake server's own routing", "123456" not in json.dumps(r))

ok, r, reqs = tool("telegram_send_message", chat_id="555", text="hi", parse_mode="Markdown", disable_notification=True)
check(
    "optional fields are included only when given",
    ok and reqs[0]["json"] == {"chat_id": "555", "text": "hi", "parse_mode": "Markdown", "disable_notification": True},
)

for bad in ({"chat_id": "555"}, {"text": "x"}, {}):
    ok, r, reqs = tool("telegram_send_message", **bad)
    check(f"missing required argument is refused before any request: {bad}", not ok and not reqs, r)

ok, r, reqs = tool("telegram_send_message", chat_id="555", text="x" * 4097)
check("text over 4096 chars is refused by the schema", not ok and "too long" in r and not reqs, r)

ok, r, reqs = tool("telegram_get_chat", chat_id="555")
check(
    "get_chat calls getChat then getChatMemberCount, and returns compact fields",
    ok
    and [x["method_name"] for x in reqs] == ["getChat", "getChatMemberCount"]
    and r == {"id": "555", "type": "group", "title": "Test Group", "description": "a chat", "member_count": 7},
)

ok, r, reqs = tool("telegram_get_updates")
check(
    "get_updates defaults to limit 20, timeout 0, and only the relevant update kinds",
    ok and reqs[0]["json"] == {"limit": 20, "timeout": 0, "allowed_updates": ["message", "edited_message", "channel_post"]},
)
check(
    "get_updates returns one compact row per update, covering both message and edited_message",
    r["count"] == 2
    and r["updates"][0] == {"update_id": 1001, "chat_id": "555", "from": "alice", "text": "hi", "date": 1700000000}
    and r["updates"][1] == {"update_id": 1002, "chat_id": "555", "from": "Bob", "text": "edited", "date": 1700000001},
)

ok, r, reqs = tool("telegram_get_updates", limit=100, timeout_seconds=5)
check("get_updates honours limit and timeout_seconds", ok and reqs[0]["json"]["limit"] == 100 and reqs[0]["json"]["timeout"] == 5)
ok, r, reqs = tool("telegram_get_updates", limit=101)
check("limit over 100 is refused by the schema", not ok and not reqs, r)

del os.environ["TELEGRAM_BOT_TOKEN"]
ok, r, reqs = tool("telegram_send_message", chat_id="555", text="x")
check("missing TELEGRAM_BOT_TOKEN is a clear ToolError", not ok and "TELEGRAM_BOT_TOKEN is not set" in r, r)

print(f"\n{passed} passed, {failed} failed  ({len(LOG)} requests recorded by the fake server)")
if failed:
    raise SystemExit(1)
