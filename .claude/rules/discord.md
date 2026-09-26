---
paths:
  - "pulse/discord.py"
  - "docs/discord.md"
---

# Discord module rules

- REST API v10 only. No gateway/websocket: it must work in a short-lived serverless function.
- Every call goes through `call()`, which adds the `Authorization: Bot` header, a valid `User-Agent`, one retry on a short 429, and turns Discord error codes into hints via `HINTS`. Add a hint there when you meet a new common error code.
- Permissions are named (`PERMISSIONS` maps name to bit index) and sent as decimal strings. Never hard-code bit math in a tool.
- Writes that appear in the server audit log pass `reason=DEFAULT_REASON` ("via capes") unless the caller gives one.
- Messages default to `allowed_mentions: {"parse": ["users"]}`. Role and `@everyone` pings need an explicit `mentions: "all"`.
- Threads are channels: thread IDs work with the channel tools. Do not add duplicate thread variants of edit/delete.
- Facts about Discord to keep true in docs and descriptions: bots cannot create servers (error 20001), bots can edit only their own messages, bulk delete only handles messages younger than 14 days, a bot can only manage roles below its own highest role, and it cannot grant permissions it lacks.
- The invite permission integer appears in `README.md`, `docs/discord.md` and `scripts/capes.mjs` (`DISCORD_PERMISSIONS`). If you change one, change all and recompute it from `PERMISSIONS`.
- Webhook tokens are secrets: `discord_send_webhook_message` looks the token up on the server and uses it internally; no tool result or error may ever contain one. Same for the bot token.
- File uploads are base64 only (no URL fetching, which would be an SSRF risk), capped at 3 MB (MAX_UPLOAD_BYTES; the schema allows the matching base64 length), with a strict filename pattern.
- Test every new or changed tool in `tests/discord_offline.py`: add a canned response to the fake server's routes and assert the exact request (endpoint, method, payload, headers). This is the only way write tools get verified without a real server.
- Mutating tools cannot be tested on a real community server. Test them with `tests/discord_e2e.py MODE=full` on a disposable server only.
