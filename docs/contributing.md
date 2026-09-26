# Contributing

Thanks for helping. This page tells you how the repo is organized, how to run and test it, and how the `.claude/` folder helps you (and your AI assistant) contribute safely.

## Set up

```bash
git clone <this repo>
cd pulse-mcp
cp .env.example .env        # fill in only what you want to test
uv run --with fastapi --with aiohttp --with python-dotenv --with uvicorn python api/index.py
```

The server listens on `http://127.0.0.1:8000`. Set `MCP_API_KEY` in `.env` and call `POST /mcp` with `Authorization: Bearer <key>`, or point an MCP client at it.

## Repo map

| Path | What it is |
|------|------------|
| `api/index.py` | FastAPI app: auth, `/mcp`, health. Importing a module in `pulse/` registers its tools. |
| `pulse/registry.py` | `@tool(...)` decorator and `ToolError`. |
| `pulse/mcp.py` | JSON-RPC handling for MCP (`initialize`, `tools/list`, `tools/call`). |
| `pulse/discord.py`, `gmail.py`, `twitter.py` | The integrations. |
| `scripts/pulse.mjs` | Zero-dependency installer and client connector. |
| `tests/` | Offline tests and an opt-in Discord end-to-end script. |
| `docs/` | Per-service guides linked from the README. |
| `CLAUDE.md`, `.claude/` | Project context for Claude Code (below). |

## Tests

Run all offline checks before every pull request (none need credentials):

```bash
uv run --with fastapi --with aiohttp --with python-dotenv --with httpx python tests/protocol.py
uv run --with fastapi --with aiohttp --with python-dotenv python tests/gmail_offline.py
python tests/check_docs.py
node --check scripts/pulse.mjs
```

`tests/discord_e2e.py` runs against a live server and a Discord server. Use `MODE=read` anywhere. Use `MODE=full` only on a disposable test server, because it posts messages and creates and deletes channels, roles and threads. See the header of the file for variables.

The same offline checks run in GitHub Actions (`.github/workflows/ci.yml`) on every push and pull request.

## The `.claude/` folder

The repo ships its Claude Code setup so every contributor's assistant starts with the same knowledge. Read [`CLAUDE.md`](../CLAUDE.md) first; it is loaded automatically in every Claude Code session. Everything below follows the [Claude Code directory layout](https://code.claude.com/docs/en/claude-directory).

| Path | Purpose | Loaded |
|------|---------|--------|
| `CLAUDE.md` | Project overview, commands, conventions, gotchas, security rules | Every session |
| `.claude/settings.json` | Shared permissions: allows the safe test/git commands, denies reading `.env*`, `.pulse.local.json`, force pushes, `vercel env pull` | Every session |
| `.claude/settings.local.json` | Your personal overrides (git-ignored, never committed) | Every session |
| `.claude/rules/security.md` | Secret-handling rules | Every session |
| `.claude/rules/tools.md` | How to write a tool | When you touch `pulse/` or `api/` |
| `.claude/rules/discord.md` | Discord specifics and limits | When you touch `pulse/discord.py` or its doc |
| `.claude/rules/gmail.md` | IMAP/SMTP conventions | When you touch `pulse/gmail.py`, its doc or test |
| `.claude/rules/installer.md` | Installer conventions | When you touch `scripts/` |
| `.claude/rules/docs.md` | Documentation conventions | When you touch README, docs, CLAUDE.md |
| `.claude/skills/add-tool/` | `/add-tool <service> <tool>`: scaffold a tool, tests and docs | When you run it |
| `.claude/skills/run-tests/` | `/run-tests`: run every credential-free test | When you run it |
| `.claude/skills/deploy/` | `/deploy`: test, deploy to Vercel, smoke-test without printing secrets | When you run it |
| `.claude/skills/security-audit/` | `/security-audit`: scan all history for leaks | When you run it |
| `.claude/agents/tool-reviewer.md` | Subagent that reviews tool changes (`@tool-reviewer`) | When invoked |
| `.claude/agent-memory/tool-reviewer/MEMORY.md` | Shared, committed lessons the reviewer reads and extends | By the reviewer |

Typical flow with Claude Code: run `claude` in the repo, ask it to add a tool with `/add-tool slack slack_send_message`, let it write code, tests and docs, run `/run-tests`, then ask `@tool-reviewer` to review the diff.

Editing the `.claude/` folder:

- Rules with a `paths:` list load only when Claude reads a matching file, which keeps context small. Keep each rule short and specific.
- Add lessons to `.claude/agent-memory/tool-reviewer/MEMORY.md` only if they are durable and safe for a shared file: no credentials, no personal IDs, no message content.
- Personal preferences belong in `.claude/settings.local.json` or your own `~/.claude/`, not in the shared files.

Not using Claude Code? The same content is plain Markdown: `CLAUDE.md` and `.claude/rules/*.md` are the project's coding and security guidelines.

## Pull request checklist

- [ ] Offline tests, docs link check and `node --check` pass.
- [ ] New or changed tool has an honest `hint` (`read`, `write`, `destructive`) and a test.
- [ ] README tool list, `docs/<service>.md`, `.env.example` and installer prompts are updated.
- [ ] No secrets, tokens, real IDs or message content anywhere in the diff (`/security-audit`).
- [ ] You say in the PR what you could not test.

## Security

Never commit credentials. If you think you did, tell the maintainer immediately; the fix is to rotate the secret and recreate the repository, not just to delete the line. Details in [`CLAUDE.md`](../CLAUDE.md#security-non-negotiable).
