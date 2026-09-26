# pulse-mcp

Personal MCP server for social accounts (Discord, Gmail, X/Twitter), deployed by each user to their own Vercel account. It speaks MCP over HTTP (JSON-RPC at `POST /mcp`) behind a Bearer key (`MCP_API_KEY`). Clients: Claude Desktop/Code, Cursor, Codex. User-facing docs are in `README.md`.

## Layout

- `api/index.py`: FastAPI app, API-key auth, `/mcp` endpoint, `/` health. Importing a module from `pulse/` registers its tools.
- `pulse/registry.py`: `@tool(name, description, properties, required, hint)` and `ToolError`.
- `pulse/mcp.py`: JSON-RPC handler (initialize, tools/list, tools/call); validates required arguments.
- `pulse/discord.py`: Discord over REST only (no gateway). `pulse/gmail.py`: IMAP/SMTP with an app password. `pulse/twitter.py`: Apify.
- `scripts/pulse.mjs`: zero-dependency Node installer (`install`, `connect`): deploys to Vercel, connects clients.
- `tests/`: `protocol.py` (MCP protocol, auth, README/tool-list/permission/env-var consistency), `gmail_offline.py` (fake IMAP), `check_docs.py` (doc links), `discord_e2e.py` (needs a running server and a Discord test server).
- `docs/`: one guide per service (`vercel`, `discord`, `gmail`, `apify`) plus `clients`, `usage`, `architecture` (goals, design, security model), `troubleshooting`, `contributing`, and the generated `tools.md`. Linked from the README.
- `scripts/gen_tools_doc.py`: regenerates `docs/tools.md` from the tool registry (`--check` fails when stale).

## Commands

```bash
# run locally (needs a .env copied from .env.example)
uv run --with fastapi --with aiohttp --with python-dotenv --with uvicorn python api/index.py

# tests (no credentials needed; same set runs in CI)
uv run --with fastapi --with aiohttp --with python-dotenv --with httpx python tests/protocol.py
uv run --with fastapi --with aiohttp --with python-dotenv python tests/gmail_offline.py
uv run --with aiohttp python scripts/gen_tools_doc.py --check   # regenerate without --check after tool changes
python tests/check_docs.py
# opt-in, needs a running server and a Discord test server (MODE=full only on a disposable one)
GUILD=<test-server-id> MODE=read python tests/discord_e2e.py

# installer syntax check
node --check scripts/pulse.mjs

# deploy (Vercel CLI, project already linked)
vercel deploy --prod
printf '%s' 'VALUE' | vercel env add NAME production
```

Env vars: `MCP_API_KEY` (required), `DISCORD_BOT_TOKEN`, `APIFY_TOKEN`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` (all optional; a tool without its token returns a clear `ToolError`).

## Conventions

- Runtime is Python on Vercel. Runtime dependencies are only `fastapi`, `aiohttp`, `python-dotenv` (`requirements.txt`). Prefer the standard library; adding a dependency needs a reason.
- Every tool is registered with `@tool(...)` and a `hint`: `read`, `write` or `destructive`. Clients use the hint to ask before risky calls.
- Raise `ToolError("...")` for expected failures (bad input, missing permission, missing token). Anything else becomes a generic error.
- IDs (Discord snowflakes) are strings in tool schemas, never integers.
- Tool results are compact JSON dicts/lists with only useful fields, not raw upstream payloads.
- Keep `README.md` in sync when you add or rename a tool, env var or setup step.
- Commit messages: imperative subject, then a short body explaining why.

## Gotchas that cost time before

- `vercel.json` must not rewrite paths: the FastAPI preset already routes everything, and a rewrite breaks `/mcp`.
- Vercel function limit is 60 s (`maxDuration`); keep upstream calls under it (Apify sync run uses a 45 s timeout).
- Discord bots cannot create servers (API error 20001) and can only edit their own messages. What a bot may do depends on the permissions it was invited with and its role, not on the token. The permission integer in `README.md` and `scripts/pulse.mjs` must stay identical.
- Gmail ids are IMAP UIDs in All Mail. Trash and Spam are not in All Mail. Search uses `X-GM-RAW` sent as an IMAP literal.
- `imaplib` does not quote mailbox names: always pass them through `quote()`.
- A new Vercel deployment is needed after changing env vars. A `401` from the live URL usually means Deployment Protection is on.
- Windows: Git Bash `/tmp` is not the same directory as Python's `/tmp`; use repo-relative paths in scripts.

## Security (non-negotiable)

- Never commit `.env*` (except `.env.example`), `.pulse.local.json`, tokens, keys or app passwords, and never print them in logs, tool results or docs. Use placeholders like `YOUR_API_KEY`.
- If a secret is ever committed: rotate it first, then delete and recreate the GitHub repository. Rewriting history is not enough because GitHub keeps orphaned commits fetchable by SHA.
- Run `/security-audit` before making the repo public or after any suspicious commit.
- Write tools must stay safe by default (for example Discord messages ping users only unless `mentions: "all"`).

## Claude Code setup in this repo

- `.claude/rules/`: path-scoped rules that load when you touch matching files (tools, Discord, Gmail, installer, README) plus an always-on security rule.
- `.claude/skills/`: `/add-tool`, `/run-tests`, `/deploy`, `/security-audit`.
- `.claude/agents/tool-reviewer.md`: reviews a new or changed tool; its shared memory is `.claude/agent-memory/tool-reviewer/MEMORY.md` (committed, so lessons reach every contributor).
- `.claude/settings.json`: shared permissions. It denies reading secret files and force pushes. Personal overrides go in `.claude/settings.local.json` (git-ignored).
