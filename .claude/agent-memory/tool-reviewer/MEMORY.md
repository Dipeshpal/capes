# tool-reviewer memory

Shared, committed lessons about this codebase. Keep entries short and factual. Never store credentials, personal IDs or message content here.

## Platform limits and API facts
- Discord bots cannot create servers (error 20001, endpoint removed for bots). They can edit only their own messages. Bulk delete works only for messages younger than 14 days.
- A Discord bot token carries no permissions. Abilities come from the invite's permission integer and the bot's role position. A fresh bot usually has only `@everyone` permissions, so manage-style tools fail with 50013 until it is re-authorized with the README invite link.
- A bot looks up its own membership with `GET /guilds/{id}/members/{bot_user_id}`; `/members/@me` is OAuth-only.
- Pins use `/channels/{id}/messages/pins` (the older `/pins` routes are deprecated).
- The Apify actor `apidojo~tweet-scraper` works on the free plan with input `searchTerms`, `maxItems`, `sort`. The first actor id in the project's history (`nwua9nN8WJjIHDLIJ`) never existed.
- Gmail over IMAP: All Mail excludes Trash and Spam; `X-GM-RAW` gives full Gmail search syntax; special folders must be found through special-use flags; `imaplib` does not quote mailbox names; app passwords need 2-Step Verification.

## Vercel
- FastAPI preset routes every path to the app. A `rewrites` entry in `vercel.json` changes the path the app sees and returns 404 on `/mcp`.
- Env var changes need a new deployment. Deployment Protection returns a login page/401 for the endpoint and breaks MCP clients.
- `capes.vercel.app` may already be taken (it was, for this project, so the project is named `capes-mcp`); Vercel may also assign a suffix (for example `capes-mcp-six`). The installer reads the real alias with `vercel inspect`.
- Imports work from the repo root package (`pulse/`) because `api/index.py` inserts the repo root into `sys.path`.

## Clients
- Claude Desktop cannot use `url` entries; it launches local commands. The `mcp-remote` bridge with the key in `env` works and is what the installer writes. On Windows, Claude Desktop from the Microsoft Store logs to `%LOCALAPPDATA%\Claude\Logs\mcp-server-<name>.log`.
- A transient DNS failure (`ENOTFOUND`) at Claude Desktop start-up on a brand-new `*.vercel.app` host resolves itself; restart the app.

## Process lessons
- GitHub keeps orphaned commits reachable by SHA after a force-push. A repo that ever contained a secret must be recreated, not just rewritten.
- Helper functions in test scripts must not take a parameter named `name` positionally: many tool arguments are called `name`. Use `def call(tool, /, **args)`.
- Do not test mutating Discord tools on a real community server; use a disposable one.
- Quoted heredocs and backslashes get mangled by the shell tool on Windows; edit files with the editor tools instead of inline Python patch scripts.

## Dashboard, validation and guardrails
- Tool arguments are validated centrally in `pulse/mcp.py` against each tool's schema. A Discord ID without the `sid()` snowflake pattern is a security bug: an ID like `123/../../users/@me` would otherwise change the API path.
- Policy (disabled connectors/tools, read-only mode) is enforced in `pulse/mcp.py` for `tools/list` and `tools/call`; environment variables (`PULSE_*`) lock settings so the dashboard cannot loosen them. If Redis is configured but unreachable, use the last known settings, else fail closed.
- Dashboard front end: no inline scripts/styles, no `innerHTML`, no browser storage, nothing from other origins. `tests/dashboard.py` greps for these.
- The guard (`scripts/check_claude_config.py`) hash-pins executable/config files under `.claude/` and `.github/`. After a reviewed change, re-pin with `--update`. On pull requests CI runs the base branch's copy of the guard so a PR cannot weaken it.
- Linting: ruff with security rules (`ruff.toml`). `ruff check --fix` plus `ruff format` clean most findings; review the rest by hand.
- A live test found that Gmail marks drafts with the `\Draft` label in All Mail rather than the IMAP flag; fakes must mimic the real service or tests hide real bugs.
- A QA report produced by an assistant is not evidence: it once claimed cleanup was done while test mail and a label remained. Verify state directly.
