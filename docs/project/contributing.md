# Contributing

Thanks for helping. By contributing you agree your work is released under the project's [MIT license](../../LICENSE). Anyone can contribute: fix a bug, improve a guide, add a tool, or build a whole new service. This page covers how to get started, the workflow, the standards, and how the `.claude/` folder makes it faster.

Read [What Capes is for](architecture.md) first if you want the big picture. **Who can merge what, and why you cannot push to `main`, is in [Governance](governance.md).** In short: fork, open a pull request, and the maintainer reviews and merges it.

## Ways to contribute

| You want to | Do this |
|-------------|---------|
| Report a bug | Open an issue with the bug template. Include the exact error text and what you expected. Never paste tokens, keys or app passwords. |
| Fix a typo or unclear step in a guide | Edit the file in `docs/` or `README.md` and open a pull request. If a menu name changed, say which page you saw. |
| Add or improve a tool | Follow [Add a tool](#add-a-tool) below. |
| Add a whole service (Calendar, Slack, ...) | Open an issue first with the feature template: the service's API, how a user gets credentials, whether it is free, and which tools you plan. Then follow [Add a service](#add-a-service). |
| Improve tests | Add cases to `tests/`. A test that reproduces a real bug is especially welcome. |

## Set up (contributors only)

End users deploy to Vercel and never run the server locally. As a contributor you can run it to try changes:

```bash
git clone <this repo>
cd capes
cp .env.example .env        # fill in only what you want to test; MCP_API_KEY must be 24+ characters, DATABASE_URL is optional locally
uv run --with fastapi --with aiohttp --with python-dotenv --with uvicorn python api/index.py
```

The server listens on `http://127.0.0.1:8000`: the dashboard is at `/dashboard`, and `POST /mcp` takes `Authorization: Bearer <key>` (examples in [Usage](../usage/usage.md#calling-the-server-without-an-ai-client)). Most work needs no credentials at all because the tests fake the outside world.

## Workflow

1. Fork the repo (or create a branch if you have access): `git switch -c feat/gmail-snooze` (prefixes: `feat/`, `fix/`, `docs/`, `test/`).
2. Make your change. Keep it focused: one topic per pull request.
3. Run the checks below until they pass.
4. Commit with an imperative subject line and a short body that says **why**, for example `Fix draft deletion: Gmail marks drafts with a label, not a flag`.
5. Open a pull request using the template. Say what you tested and, honestly, what you could not test (for example "no access to a real Discord server").
6. Respond to review. CI must be green. Only a code owner can approve and merge; see [Governance](governance.md).

## Checks

Run before every pull request. None needs credentials.

```bash
uv run --with fastapi --with aiohttp --with python-dotenv --with httpx python tests/protocol.py
uv run --with fastapi --with aiohttp --with python-dotenv --with httpx --with asyncpg --with cryptography python tests/dashboard.py
uv run --with fastapi --with aiohttp --with python-dotenv python tests/gmail_offline.py
uv run --with fastapi --with aiohttp --with python-dotenv python tests/discord_offline.py
uv run --with fastapi --with aiohttp --with python-dotenv python tests/telegram_offline.py
uv run --with fastapi --with aiohttp --with python-dotenv --with asyncpg --with cryptography python tests/db_offline.py
python tests/claude_config.py
python scripts/check_claude_config.py
uv run --with aiohttp python scripts/gen_tools_doc.py --check
python tests/check_docs.py
node --check scripts/capes.mjs && node --check dashboard/app.js
uvx ruff check . && uvx ruff format --check .
```

What they protect:

- `protocol.py`: the MCP protocol, authentication, argument validation, read-only and disabled-tool enforcement, every tool's schema and safety label, and that the README tool list, the Discord permission number and the environment variables in docs agree with the code.
- `dashboard.py`: sign-in (both `MCP_API_KEY` and `DASHBOARD_USER`/`DASHBOARD_PASSWORD` modes), cookie flags, rate limiting, tampered and expired sessions, CSRF and origin checks, secrets never leaking, settings through a fake Redis, API keys and connector credentials through a fake database (including an unreachable-but-configured database degrading gracefully, not crashing), fail-closed behaviour, security headers and the Content-Security-Policy, and rules for the front-end code (no inline scripts, no `innerHTML`, no outside origins).
- `gmail_offline.py`: all Gmail tools against an in-memory fake IMAP/SMTP server that answers like real Gmail, including credentials supplied through the (faked) database instead of env vars.
- `discord_offline.py`: the Discord tools against a fake Discord REST server that records every request, so the exact endpoint, method, payload, headers, multipart upload and retry behaviour of each write tool is checked without touching a real server.
- `telegram_offline.py`: the Telegram tools against a fake Bot API server, the same way.
- `db_offline.py`: encryption, key hashing, the Supabase Direct-connection-vs-pooler hint, and the API-key/connector-credential create/list/revoke logic against a fake in-memory Postgres double (no real database needed).
- `claude_config.py` and `check_claude_config.py`: the guard for assistant and CI configuration, and proof that each attack it exists for is blocked (see [below](#the-guard-for-assistant-and-ci-configuration)).
- `gen_tools_doc.py --check`: [docs/usage/tools.md](../usage/tools.md) matches the code. If it fails, run `python scripts/gen_tools_doc.py` and commit the result.
- `check_docs.py`: every relative link and `#anchor` in the docs resolves.
- `ruff`: lint (including security rules) and formatting. `uvx ruff check . --fix && uvx ruff format .` fixes most findings.

`tests/discord_e2e.py` runs against a live server and a real Discord server. Use `MODE=read` anywhere. Use `MODE=full` only on a disposable test server, because it posts messages and creates and deletes channels, roles and threads. The file header lists its variables.

The same checks run in GitHub Actions on every push and pull request, together with a scan of the whole git history for secrets.

## The guard for assistant and CI configuration

Files that steer AI assistants and CI decide what runs on every contributor's machine and in the pipeline, so `scripts/check_claude_config.py` polices them. It fails a pull request that:

- adds hooks, environment variables, MCP servers or a helper command to `.claude/settings.json`, or adds a permission that is not on its approved list, or removes a required deny rule;
- adds a `.mcp.json`, a hooks folder, slash commands or any `.claude/` entry outside `agents`, `rules`, `skills`, `agent-memory` and `settings.json`;
- puts hidden text in assistant files (zero-width or bidirectional characters, HTML comments), prompt-injection wording, links to unapproved hosts, network or remote-execution commands, or shell injections outside an approved list;
- gives an agent tools beyond `Read`, `Grep`, `Glob` and `Bash`, or adds `allowed-tools`, `model` or `hooks` frontmatter;
- adds a workflow with `pull_request_target`, write permissions, repository secrets, third-party actions or untrusted event data in a shell command;
- adds a dependency to `requirements.txt` that is not approved, or anything but `functions` to `vercel.json`;
- changes any executable or configuration file under `.claude/` or `.github/` without re-pinning its hash.

If your change is legitimate, CI failing is expected: describe why in the pull request. A maintainer reviews it, updates the approved lists in the script if appropriate, and re-pins with `python scripts/check_claude_config.py --update`. On pull requests CI runs the base branch's copy of the guard, so a pull request cannot loosen its own check. `CODEOWNERS` sends these paths, the guard, authentication code and the dashboard to the maintainer for review.

## Add a tool

1. Find the module (`pulse/discord.py`, `pulse/gmail.py`, ...) and add an async function with `@tool(...)`:

   ```python
   @tool(
       "gmail_snooze",
       "Hide a message from the inbox until a date.",
       {"id": {"type": "integer"}, "until": {"type": "string", "description": "ISO date"}},
       ["id", "until"],
       hint="write",
   )
   async def gmail_snooze(args: dict): ...
   ```

2. Choose the honest `hint`: `read` (no side effects), `write` (creates or changes things), `destructive` (deletes or is hard to undo).
3. Write a description a language model can act on: what it does, what it needs, limits. Raise `ToolError("what to do next")` for expected failures.
4. Add a test (offline if at all possible), then run `python scripts/gen_tools_doc.py` and add the tool name to the README tool list. `tests/protocol.py` fails if the README or docs/usage/tools.md miss it.

The conventions are in [`CLAUDE.md`](../../CLAUDE.md) and `.claude/rules/tools.md`.

## Add a service

A "connector" (Gmail, Discord, ...) is its own module, its own credentials, its own row in the dashboard. Here is the full checklist, in order.

1. **Create `pulse/<service>.py`** with its `@tool` functions (see [Add a tool](#add-a-tool) above for the tool-level conventions). Prefer the standard library or `aiohttp`; a new dependency needs a reason in the pull request and must be added to `ALLOWED_DEPENDENCIES` in `scripts/check_claude_config.py` -- as its own, separate pull request, reviewed and merged *before* the one that uses it (the guard checks a PR's `requirements.txt` against the base branch's copy of the allowlist by design, so a PR can never approve its own new dependency).

2. **Read credentials through `creds.get(name)`, not `os.getenv` directly** (`from . import creds`, then `token = await creds.get("SERVICE_TOKEN")`). This one call checks the database first (if `DATABASE_URL` is set and the value was entered from the dashboard's Connectors tab) and falls back to the plain environment variable of the same name -- so the service works identically for someone using env vars and someone using the dashboard, with no extra code. If your service's client library is synchronous (like `imaplib`/`smtplib` for Gmail), you can't call `creds.get` from inside a worker thread; see `pulse/gmail.py`'s `run()`/`session()`/`credentials()` for the pattern (fetch async, hand the value into the thread via a `contextvars.ContextVar`, since `asyncio.to_thread` copies the calling context).

3. **Import the module in `api/index.py`** (registers its tools) **and separately in `scripts/gen_tools_doc.py`** (add it to `SERVICES` there too -- this script imports independently of `api/index.py`, so it's easy to update one and forget the other, and `tests/protocol.py` will catch it if you do).

4. **Register the service in `pulse/connectors.py`**: a `Connector(id, name, tool_prefix, env_vars_tuple, guide_path, summary)`. Leave `db_backed` at its default (`True`) unless there's a real reason your credentials can't live in the database. This makes it appear in the dashboard with a configured/not-configured status, a **Test connection** button, and (if `db_backed`) a "Set credentials here" form -- write its connection test in `connectors.test_connection()`: read-only, must never raise, must never echo a secret in its result (route unexpected exceptions through `security.redact()`).

5. **Add the environment variables** to `.env.example`, the table in `docs/setup/vercel.md`, and the prompts in `scripts/capes.mjs` (both `install()` and `addEnv()`).

6. **Write `docs/setup/<service>.md`** in the style of the existing guides: where to click, what permissions, limits, how to check it works, common errors, how to rotate or revoke.

7. **Add a row to the README services table** and a line to `docs/usage/troubleshooting.md`.

8. **Add tests.** Offline if at all possible: build a fake server for the service's API (see `tests/discord_offline.py` or `tests/telegram_offline.py` for the pattern -- a `ThreadingHTTPServer` that records every request and answers with canned responses, monkeypatching your module's base-URL constant) so the test suite needs no real credentials or network access. Cover at minimum: a successful call, the exact request shape (method, path, body) for at least one write tool, a missing-credential error, and (if `db_backed`) that a credential supplied via a faked `creds.get` reaches the request instead of the env var.

With Claude Code, `/add-tool <service> <tool>` does the scaffolding and reminds you of every step.

## Code style

- Python 3.12, type hints where they help, no unused code or speculative options.
- Small functions, clear names, comments only for non-obvious reasons.
- Compact tool results: return the fields a person needs, not the raw API payload.
- No emojis in code or docs. Plain, direct language.

## Security rules for contributors

- Never commit credentials, keys, tokens, real IDs or message content. Use placeholders like `YOUR_API_KEY`.
- Do not print secrets in logs, tool results or error messages.
- Do not test destructive Discord tools on a real community server.
- If you think you committed a secret, tell the maintainer at once. The fix is to rotate it and recreate the repository, not just to delete the line ([why](../../CLAUDE.md#security-non-negotiable)).

## The `.claude/` folder

The repo ships its Claude Code setup so every contributor's assistant starts with the same knowledge. [`CLAUDE.md`](../../CLAUDE.md) is loaded automatically in every Claude Code session. The layout follows the [Claude Code directory guide](https://code.claude.com/docs/en/claude-directory).

| Path | Purpose | Loaded |
|------|---------|--------|
| `CLAUDE.md` | Project overview, commands, conventions, gotchas, security rules | Every session |
| `.claude/settings.json` | Shared permissions: allows the safe test and git commands, denies reading `.env*`, `.capes.local.json`, force pushes and `vercel env pull` | Every session |
| `.claude/settings.local.json` | Your personal overrides (git-ignored, never committed) | Every session |
| `.claude/rules/security.md` | Secret-handling rules | Every session |
| `.claude/rules/tools.md` | How to write a tool | When you touch `pulse/` or `api/` |
| `.claude/rules/dashboard.md` | Front-end, dashboard and database security rules | When you touch `dashboard/`, `pulse/dashboard.py`, `pulse/security.py`, `pulse/store.py`, `pulse/db.py`, `pulse/creds.py`, `pulse/apikeys.py` or `migrations/` |
| `.claude/rules/discord.md` | Discord specifics and limits | When you touch `pulse/discord.py` or its guide |
| `.claude/rules/gmail.md` | IMAP/SMTP conventions | When you touch `pulse/gmail.py`, its guide or its test |
| `.claude/rules/github.md` | CI, ruleset and governance rules | When you touch `.github/`, `docs/project/governance.md` or `SECURITY.md` |
| `.claude/rules/installer.md` | Installer conventions | When you touch `scripts/` |
| `.claude/rules/docs.md` | Documentation conventions | When you touch README, docs or CLAUDE.md |
| `.claude/skills/add-tool/` | `/add-tool <service> <tool>`: scaffold a tool, tests and docs | When you run it |
| `.claude/skills/run-tests/` | `/run-tests`: run every credential-free check | When you run it |
| `.claude/skills/deploy/` | `/deploy`: test, deploy to Vercel, smoke-test without printing secrets | When you run it |
| `.claude/skills/security-audit/` | `/security-audit`: scan all git history for leaks | When you run it |
| `.claude/agents/tool-reviewer.md` | Subagent that reviews tool changes (`@tool-reviewer`) | When invoked |
| `.claude/agent-memory/tool-reviewer/MEMORY.md` | Shared, committed lessons the reviewer reads and extends | By the reviewer |

Typical flow: run `claude` in the repo, ask it to add a tool with `/add-tool slack slack_send_message`, let it write code, tests and docs, run `/run-tests`, then ask `@tool-reviewer` to review the diff.

Editing the folder:

- Rules with a `paths:` list load only when Claude reads a matching file, which keeps context small. Keep each rule short and specific.
- Add lessons to `.claude/agent-memory/tool-reviewer/MEMORY.md` only if they are durable and safe to share: no credentials, no personal IDs, no message content.
- Personal preferences belong in `.claude/settings.local.json` or your own `~/.claude/`, not in the shared files.

Not using Claude Code? It is all plain Markdown: `CLAUDE.md` and `.claude/rules/*.md` are the project's coding and security guidelines.

## Pull request checklist

- [ ] The checks above pass and CI is green.
- [ ] New or changed tools have an honest `hint` and a test.
- [ ] README tool list, `docs/usage/tools.md`, `docs/setup/<service>.md`, `.env.example` and installer prompts are updated where relevant.
- [ ] No secrets, tokens, real IDs or message content in the diff.
- [ ] The description says what you could not test.
