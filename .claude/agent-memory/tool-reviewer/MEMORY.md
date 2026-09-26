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
- `pulse-mcp.vercel.app` may already be taken; Vercel then assigns a suffix (for example `pulse-mcp-six`). The installer reads the real alias with `vercel inspect`.
- Imports work from the repo root package (`pulse/`) because `api/index.py` inserts the repo root into `sys.path`.

## Clients
- Claude Desktop cannot use `url` entries; it launches local commands. The `mcp-remote` bridge with the key in `env` works and is what the installer writes. On Windows, Claude Desktop from the Microsoft Store logs to `%LOCALAPPDATA%\Claude\Logs\mcp-server-<name>.log`.
- A transient DNS failure (`ENOTFOUND`) at Claude Desktop start-up on a brand-new `*.vercel.app` host resolves itself; restart the app.

## Process lessons
- GitHub keeps orphaned commits reachable by SHA after a force-push. A repo that ever contained a secret must be recreated, not just rewritten.
- Helper functions in test scripts must not take a parameter named `name` positionally: many tool arguments are called `name`. Use `def call(tool, /, **args)`.
- Do not test mutating Discord tools on a real community server; use a disposable one.
- Quoted heredocs and backslashes get mangled by the shell tool on Windows; edit files with the editor tools instead of inline Python patch scripts.
