# tool-reviewer memory

Shared, committed lessons about this codebase. Keep entries short and factual. Never store credentials, personal IDs or message content here.

## Platform limits and API facts
- Discord bots cannot create servers (error 20001, endpoint removed for bots). They can edit only their own messages. Bulk delete works only for messages younger than 14 days.
- A Discord bot token carries no permissions. Abilities come from the invite's permission integer and the bot's role position. A fresh bot usually has only `@everyone` permissions, so manage-style tools fail with 50013 until it is re-authorized with the README invite link.
- A bot looks up its own membership with `GET /guilds/{id}/members/{bot_user_id}`; `/members/@me` is OAuth-only.
- Pinning needs the separate **Pin Messages** permission (bit 51) since 2025; Manage Messages alone returns 403 (50013). A bot's user ID equals its application ID, which is how the dashboard builds the invite link.
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

## Database (pulse/db.py, creds.py, apikeys.py)
- Supabase's **Direct connection** URL (`db.<ref>.supabase.co:5432`) is IPv6-only; Vercel has no IPv6 egress, so it just times out. Always the **Session pooler** URL. `pulse/db.py` pattern-matches the direct-connection host and surfaces a specific hint instead of a generic error.
- `asyncpg.create_pool(min_size=0, ...)` does not actually connect at creation (lazy pool); the first real connection attempt happens on first `acquire()`, so a refused connection surfaces there as a plain `OSError`, not `asyncpg.PostgresError`. Every place that queries the database must catch both, or an unreachable DB becomes an unhandled 500. Found and fixed live against a real unreachable Postgres URL during a browser test.
- Don't let a resource-unavailable exception (`db.DatabaseUnavailable`) also swallow "the input was malformed" -- validate the input (e.g. `uuid.UUID(key_id)`) as a separate, earlier step, so a genuinely down database is never misreported as "not found" (bit `apikeys.revoke_key` once: a bad-uuid guard and an unreachable-DB guard were the same blanket `except`, so a dropped connection mid-request silently looked like the key didn't exist).
- `security.credentials_match(user, password)` must compute both `secrets.compare_digest` calls unconditionally, not `and`-short-circuited -- otherwise a wrong username returns faster than a wrong password, a timing side channel on which part was wrong (the login route's fixed 0.4s delay already dominates this in practice, but the check itself should still be honest).
- Gmail's credentials can come from the database, but `imaplib`/`smtplib` are synchronous. The fix is a `contextvars.ContextVar` set right before `asyncio.to_thread` (which copies the calling context) -- not a function parameter threaded through every call site. Any new synchronous-library connector needing DB-backed credentials should follow the same `run()`/`session()`/`ContextVar` shape, not bypass it with a direct blocking call.

## GitHub and release process
- Branch rules need a public repo (a private free plan returns 403). Apply the ruleset, then verify: a direct push to `main` is rejected and a PR shows BLOCKED until a code owner approves. The owner merges with `gh pr merge N --squash --admin`.
- A `gh` token without the `workflow` scope cannot push changes to `.github/workflows/`.
- Renaming a git-ignored file un-ignores it. `git add -A` then commits a key file; check `git ls-files -o --exclude-standard` first.
- Dependabot PRs touching `requirements.txt` conflict with each other; `@dependabot rebase` one at a time.
- Only a Vercel project's automatic production domain is public; manual aliases return 302 (Deployment Protection).
- A transparent PNG looks black in the image viewer; check the alpha channel before flattening.
- Codex CLI with a ChatGPT login accepts only `gpt-6-luna`; treat its and Claude Desktop's reports as leads, not evidence.
