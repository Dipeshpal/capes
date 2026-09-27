# What Capes is for, and how it works

## The goal

AI assistants are good at reading, summarizing and acting, but your real work lives in accounts they cannot reach: your inbox, your community chat, your social feeds. Capes is a small server that gives an assistant controlled access to **your own** accounts through one standard door (the [Model Context Protocol](https://modelcontextprotocol.io/docs/getting-started/intro)), so the same setup works in Claude, Codex, Cursor and any other MCP client.

What we are trying to achieve:

1. **Personal and private.** You deploy your own copy to your own Vercel account, with your own Postgres database. There is no central service and no one else's server between you and your data. Your credentials sit in your own Vercel project and your own database, encrypted, never anywhere else.
2. **Easy to set up.** Deploy from your browser, then a click-by-click guide per service. A person who has never used MCP should be running in about 20 minutes.
3. **Useful by default.** Full toolkits, not toys: Gmail (search, read, send, draft, organize), Discord (read, write, manage, moderate), X search, Telegram (send, read, poll). Anything you can do by hand in these accounts, an assistant can do for you.
4. **Under your control.** A dashboard shows what is connected and lets you switch connectors and tools off or make the server read-only. Tools are labelled read, write or destructive so clients ask before risky calls.
5. **Free to run.** Vercel Hobby, Gmail app passwords, the Apify free plan and a free Redis cover personal use.
6. **Easy to extend and safe to contribute to.** A new tool is one Python function. Contributors get a ready-made Claude Code setup (`.claude/`), and CI blocks changes that would quietly alter what assistants or the pipeline can do.

Not goals: a multi-user SaaS, storing your data anywhere, replacing the official apps, providing self-hosted Docker or local-server options for end users (deployment is Vercel only), or working around the terms of the services it connects to.

## How a request flows

![Capes architecture: AI clients and the owner reach one server on Vercel; a guard checks every call before the tools reach Gmail, Discord and Apify](../diagrams/architecture.png)

The interactive version (pan, zoom, trace paths) is [architecture.html](../diagrams/architecture.html); download it and open it in a browser.

![Life of a tool call: the client calls /mcp with a key, the guard checks it, the tool calls the service with your token, and the result comes back redacted](../diagrams/request-lifecycle.png)

Interactive: [request-lifecycle.html](../diagrams/request-lifecycle.html). The same flow as text:

```
 AI client (Claude, Codex, Cursor)                     you, in a browser
        |  MCP over HTTPS                                     |  HTTPS, session cookie
        |  Authorization: Bearer <MCP_API_KEY or a           |  MCP_API_KEY, or DASHBOARD_USER/
        |  dashboard-issued key>                              |  DASHBOARD_PASSWORD if you set those
        v                                                     v
 your Vercel project: api/index.py  (FastAPI)  ------  /dashboard (pulse/dashboard.py + dashboard/)
        |  POST /mcp: verify key (env var or hashed in the database), then JSON-RPC
        v
 pulse/mcp.py : validate arguments -> apply owner policy (pulse/store.py) -> run tool -> log outcome
        |
        +--> pulse/gmail.py    --> imap/smtp.gmail.com   (app password)
        +--> pulse/discord.py  --> Discord REST API      (bot token)
        +--> pulse/twitter.py  --> Apify API             (Apify token)
        +--> pulse/telegram.py --> Telegram Bot API      (bot token)
        |
        +--> pulse/creds.py --> your Postgres (DATABASE_URL): connector credentials (AES-256-GCM
        |                       encrypted, key = ENCRYPTION_KEY) and extra MCP API keys (hashed).
        |                       Falls back to plain env vars wherever the database has no row, or
        |                       is not configured at all.
        v
 pulse/store.py --> optional Redis (Upstash): read-only-mode/tool switches, activity log, rate limits
                     (a separate, optional concern from the Postgres database above)
```

Each MCP call is independent (stateless); no session state is kept between calls. What state *does* exist lives in two independent, both-optional-at-the-code-level places: your Postgres database (credentials, extra API keys -- required for new deployments since #40, but a pre-existing deployment runs unchanged without it) and an optional Redis (live policy switches only). Credentials are read through `creds.get(name)`, which checks the database first and falls back to the environment variable of the same name, so a missing one only disables that service either way.

## Components

| Path | Role |
|------|------|
| `api/index.py` | The web app: API-key check for `/mcp`, security headers, health check, `/` routing |
| `pulse/mcp.py` | MCP core: JSON-RPC, argument validation against each tool's schema, policy enforcement, activity logging |
| `pulse/registry.py` | The `@tool(...)` decorator, `ToolError`, and read/write/destructive labels |
| `pulse/security.py` | Key and username/password checks, session cookies, CSRF, origin checks, security headers, AES-256-GCM encryption for database-stored credentials |
| `pulse/store.py` | Owner settings (environment plus optional Redis), activity log, rate limiting |
| `pulse/db.py` | Optional Postgres connection pool, migrations runner, the Supabase Direct-connection-vs-pooler hint |
| `pulse/creds.py` | Connector credential lookup: database first, environment variable fallback |
| `pulse/apikeys.py` | Extra, labelled, expiring MCP API keys stored hashed in the database |
| `migrations/` | Database schema, applied automatically in order on first use |
| `pulse/connectors.py` | The connected services: what each needs, whether it is configured, connection tests |
| `pulse/dashboard.py`, `dashboard/` | The dashboard API and its HTML, CSS and JavaScript |
| `pulse/gmail.py`, `discord.py`, `twitter.py`, `telegram.py` | The integrations |
| `scripts/capes.mjs` | Optional installer: deploys to Vercel, wires up your AI clients, and pulls upstream updates into an existing deployment (`update` command) |
| `scripts/gen_tools_doc.py`, `scripts/check_claude_config.py` | Doc generator; guard for assistant and CI configuration |
| `tests/` | Offline tests (including fake Postgres, IMAP, Discord and Telegram servers) plus an opt-in Discord end-to-end script |

## Security model

**Assets:** your email, your Discord bot's reach, your Apify account, and your Vercel project. **Attackers considered:** anyone on the internet who finds your URL; a malicious web page trying to drive your logged-in dashboard; a prompt-injected assistant sending odd arguments; a malicious contributor; a leaked secret.

| Threat | Defence |
|--------|---------|
| Guessing the key/password or brute-forcing the dashboard | Generated keys must be 24+ characters (weak ones are refused); a chosen `DASHBOARD_PASSWORD` must be 8+. Comparisons are constant time, computed unconditionally rather than short-circuited, so a wrong username can't be distinguished from a wrong password by timing. Dashboard sign-in adds a fixed delay and allows 10 attempts per 15 minutes per address (counted in Redis when present, per server instance otherwise). |
| Stolen or replayed dashboard session | Session cookie is signed, HttpOnly, SameSite=Strict, `__Host-` prefixed and Secure over HTTPS, lives 8 hours by default (`PULSE_SESSION_HOURS`), and stops working if the secret currently used to sign in (`DASHBOARD_PASSWORD` if set, else `MCP_API_KEY`, else `ENCRYPTION_KEY`) is changed. After it expires you just sign in again; there is no scheduled rotation. No key, token or password is stored in the browser. |
| Another website driving the dashboard (CSRF) | Every change requires a per-session CSRF token, a same-origin `Origin` / `Sec-Fetch-Site` check and `Content-Type: application/json`, on top of SameSite=Strict. |
| Script injection into the dashboard (XSS) | Strict Content-Security-Policy (no inline script or style, no other origins, no framing) and every value is inserted as text. Enforced by tests. |
| Secrets showing up in the UI, results or logs | The dashboard API returns only whether a variable is set, never its value; a newly created API key is the one exception, shown exactly once at creation and never retrievable again. Errors report the service's message, never a token, and all error text passes through a redaction step that masks the server's secret values and webhook-token URL segments. The activity log stores tool names, times and outcomes, never arguments or results. |
| Compromise of your database, or of a backup of it | Connector credentials and API keys are never stored in plaintext: connector tokens are AES-256-GCM encrypted with a key derived from `ENCRYPTION_KEY` (which lives only in Vercel env vars, not the database), and API keys are stored as a SHA-256 hash, never the key itself. A database leak alone is not enough to recover either. |
| An unreachable database (wrong URL, paused, network blip) | Every database-backed route fails closed in a controlled way: a write returns `409` with a clear message, a read degrades to an empty result with a `degraded` flag, and every credential lookup falls back to the environment variable of the same name. Never a raw `500`, and env-var-based deployments are entirely unaffected. |
| A model (or an attacker steering it) passing crafted arguments | Every argument is validated against the tool's schema before anything runs. IDs must match a strict pattern, so a value cannot add URL path or change which API endpoint is called. The Discord HTTP helper also allow-lists path characters. Mailbox names with control characters are refused so an IMAP command cannot be injected. Unknown arguments are dropped. |
| An assistant doing more than you intended | Tools are labelled read, write or destructive so clients ask first. You can switch connectors and tools off, or set read-only mode, and disabled tools are both hidden and refused. Discord messages ping users only unless asked otherwise. Sending mail is a separate, explicit tool from drafting it. |
| Losing the settings store | If Redis is configured but unreachable, the last known settings are used; with none, the server fails closed into read-only mode. |
| A contributor changing what assistants or CI can do | CI runs a guard that blocks hooks, wildcard permissions, project MCP servers, hidden Unicode or HTML comments, unapproved links and shell injections in assistant files, third-party actions, `pull_request_target`, write tokens, unapproved dependencies and `vercel.json` rewrites. Every executable file under `.claude/` and `.github/` is hash-pinned, so any change needs maintainer review and re-pinning. On pull requests the guard runs from the base branch so a PR cannot weaken its own check. `CODEOWNERS` routes these paths, authentication code, the database layer and the guard itself to the maintainer. |
| A leaked secret in git | A secret scan covers the whole history on every push. If one leaks: rotate it, then recreate the repository (GitHub keeps orphaned commits reachable by SHA). |

**Residual risks, stated plainly:** anyone holding `MCP_API_KEY` (or a dashboard-issued key) controls every connected service through your server. Multiple API keys with expiry exist now (Settings tab), but there is still no per-key *scope* -- every key can call every tool (tracked in issue #24). A Gmail app password reaches the whole mailbox. Without Redis, sign-in throttling is per server instance and therefore weak on serverless. Losing `ENCRYPTION_KEY` makes everything already stored in the database permanently unreadable -- there is no recovery path, by design (that's what makes it real encryption rather than obfuscation). Tool labels are advice to the client, not enforcement; the enforced limits are the ones you set in the dashboard, in environment variables, and in each service's own permissions. Branch protection with required code-owner review must be turned on in GitHub for `CODEOWNERS` to be binding.

## Design decisions

| Decision | Why |
|----------|-----|
| Serverless HTTP on Vercel, and nothing else for end users | Free, no machine to run, works from any client, and each user gets an isolated deployment. One supported path is easier to secure and document than several. |
| Stateless JSON-RPC over plain HTTP | No sessions to store; works on short-lived functions; supported by current MCP clients |
| Dashboard in plain HTML/CSS/JS with no build step | Nothing to compile or update, tiny attack surface, works under a strict Content-Security-Policy, easy to audit |
| Sign in with `MCP_API_KEY`, or a separate `DASHBOARD_USER`/`DASHBOARD_PASSWORD` | One secret by default, matching the API key. Setting a separate username/password decouples the dashboard login from the key that guards `/mcp`, so leaking or rotating one doesn't touch the other. Sessions derive from whichever secret is the active login credential, so rotating it signs everyone out. |
| Bring-your-own Postgres for credentials and API keys, Redis optional | New deployments provision their own Postgres (e.g. Supabase) so connector credentials and extra API keys can be encrypted and managed from the dashboard instead of living only in env vars -- required for the features this unlocks (multiple, expiring API keys; eventually Gmail OAuth). It changes nothing about the server's own state: read-only mode and per-tool/per-connector switches are still plain environment variables, unrelated to this database. Redis remains a separate, optional add-on for live switches, a durable activity log and shared sign-in throttling; if configured but down, the server fails closed. Deployments made before this was added keep running unchanged: every credential and API-key lookup falls back to env vars when no database is configured. |
| Credentials handed into a worker thread via a `ContextVar`, not a function argument (Gmail) | `imaplib`/`smtplib` are synchronous, so their work runs in `asyncio.to_thread`, but the credential may need an async database read first. `asyncio.to_thread` copies the calling context, so a `ContextVar` set just before it is the only way to get an async-fetched value into the thread without changing every function's signature. |
| `git`-native update path (`capes.mjs update`), not an auto-updater | Every deployment is a fork the owner controls; a merge from upstream is something they can read and reason about before it reaches production, unlike a service quietly patching itself. Reuses the identical link-then-deploy call `install()`/`env()` already use. |
| Only read tools can run from the dashboard | The dashboard is for looking and controlling, not for acting. Acting happens in your AI client, where you see and approve it. |
| Discord over REST, no gateway | A gateway needs a long-lived connection, which serverless functions cannot keep. REST covers every action here |
| Gmail over IMAP/SMTP with an app password | Free and a minute to set up. Gmail's own API would need a Google Cloud project, an OAuth consent screen and periodic re-consent for personal apps. The trade-off is that an app password is broad. |
| `mcp-remote` for Claude Desktop | Claude Desktop only launches local commands, so a tiny bridge turns your URL into a local command |
| Tools return compact JSON | Smaller results cost fewer tokens and are easier for a model to use than raw API payloads |
| IDs are strings | Discord IDs exceed the safe range of JSON numbers |

## How it compares

Nothing here is the first of its kind. Searching GitHub in September 2026 found overlapping projects; what Capes offers is a particular combination.

| Project | What it is | Where it differs from Capes |
|---------|------------|---------------------------------|
| [kebab-mcp](https://github.com/Yassinello/kebab-mcp) | Personal MCP framework on Vercel with a dashboard, 97+ tools (Google Workspace, Slack, Notion, GitHub and more) | Broader connectors and a richer dashboard; needs a key-value store; no Discord or X in its README; AGPL. Capes is narrower (Gmail, Discord, X, Telegram) with free Gmail that needs no Google Cloud project. |
| Single-service MCP servers (for example Gmail with OAuth, Discord on Cloudflare Workers with 59 tools) | One service each, often local, sometimes hosted | Deeper in one service (the Discord one has more tools than ours); you install and secure one server per service |
| Aggregators such as MetaMCP and MCPHub | Combine existing MCP servers behind one endpoint | They route to servers you still have to find, configure and host |
| Hosted platforms such as Composio | Managed sign-in and hundreds of toolkits | Much broader; your credentials and calls pass through a third party |

The dashboard idea was inspired by kebab-mcp. Capes's implementation is independent and written from scratch.

## Known limits

- Vercel stops a request after 60 seconds.
- New deployments need a Postgres database (a free Supabase project takes about two minutes); a pre-existing deployment does not and keeps working exactly as before.
- Gmail OAuth is not implemented -- app password only. Google's policy on unverified/testing-mode OAuth apps (possible periodic re-consent for the Gmail scope) is an external constraint outside this project's control, tracked in issue #36.
- No per-key scopes yet: any MCP API key (env-var or dashboard-issued) can call every tool the owner hasn't disabled. Tracked in issue #24.
- Discord: bots cannot create servers and can edit only their own messages. See the [Discord guide](../setup/discord.md#what-the-bot-cannot-do). The Discord tools are verified against a fake Discord server that checks the exact request each one sends, and most were also run by hand against a disposable test server (that run found that pinning needs the separate Pin Messages permission). The maintainer has also tested it on a real community server. Some tools, such as direct messages and audit-log filters, have not been exercised in a recorded run.
- Gmail: one account, and Trash/Spam are not searchable. See the [Gmail guide](../setup/gmail.md#limits).
- X search depends on a third-party scraper (Apify); its availability and prices are outside this project.
- The database layer's actual encrypt/store/decrypt round trip has been tested against a fake in-memory Postgres double (`tests/db_offline.py`), not yet against a real Supabase/Neon database in CI.

## Ideas for later (not promises)

- More Discord: application commands, scheduled events, stickers and emoji management, member nickname edits.
- Per-key tool scopes (multiple keys with expiry already exist; scoping which tools each key can call does not yet).
- Gmail OAuth, once the verification/re-consent question above is resolved one way or another.
- Multiple accounts per service.

Want to build one? See [Contributing](contributing.md).
