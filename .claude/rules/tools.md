---
paths:
  - "pulse/**/*.py"
  - "api/**/*.py"
---

# Writing MCP tools

- Register with `@tool(name, description, properties, required, hint=...)` from `pulse/registry.py`. Names are `<service>_<verb>_<noun>` in snake_case (`discord_send_message`, `gmail_search`).
- `hint` must be honest: `read` (no side effects), `write` (creates or changes things but is recoverable), `destructive` (deletes, or is hard to undo such as moderation).
- Descriptions are read by a language model. Say what the tool does, what it needs (a permission, an env var) and any limit, in one or two sentences. Describe accepted values in `properties`, using `enum` where the set is closed.
- List every mandatory argument in `required`; `pulse/mcp.py` rejects calls that miss them before your function runs.
- Raise `ToolError("...")` for expected failures and include the fix ("Enable Server Members Intent..."). Do not catch broad exceptions just to hide them.
- Return small dicts/lists with only the useful fields. Convert upstream payloads instead of passing them through.
- Snowflake IDs and other big integers are strings in schemas.
- Blocking libraries (imaplib, smtplib) run inside `asyncio.to_thread`; network code with `aiohttp` sets an explicit timeout under 60 s (Vercel `maxDuration`).
- Read secrets from `os.getenv` inside the function, never at import time, so a missing token only breaks that service.
- New module? Import it in `api/index.py` so it registers. Then update `README.md` (tool list), `.env.example` and add a test.
