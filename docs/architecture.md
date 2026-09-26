# What pulse-mcp is for, and how it works

## The goal

AI assistants are good at reading, summarizing and acting, but your real work lives in accounts they cannot reach: your inbox, your community chat, your social feeds. pulse-mcp is a small server that gives an assistant safe, controlled access to **your own** accounts, through one standard door (the [Model Context Protocol](https://modelcontextprotocol.io)), so the same setup works in Claude, Codex, Cursor and any other MCP client.

What we are trying to achieve:

1. **Personal and private.** You deploy your own copy to your own Vercel account. There is no central service, no shared database and no one else's server between you and your data. Your credentials sit in your own Vercel project.
2. **Easy to set up.** One command, or one button, plus a guide for each service that says exactly where to click. A person who has never used MCP should be running in about 20 minutes.
3. **Useful by default.** Full toolkits, not toys: Discord (read, write, manage, moderate), Gmail (search, read, send, draft, organize), X search. Anything you can do by hand in these accounts, an assistant can do for you.
4. **Safe by default.** Tools are labelled read, write or destructive so clients ask before risky calls. Mentions are limited, sending is explicit, and every Discord change is tagged in the audit log.
5. **Free to run.** Vercel Hobby, Gmail app passwords and the Apify free plan cover personal use.
6. **Easy to extend.** A new service is one Python file with small decorated functions. Contributors get a ready-made Claude Code setup (`.claude/`) that knows the project's rules.

Not goals: a multi-user SaaS, storing your data anywhere, replacing the official apps, or working around the terms of the services it connects to.

## How a request flows

```
 AI client (Claude, Codex, Cursor)
        |  MCP over HTTPS, header: Authorization: Bearer <MCP_API_KEY>
        v
 your Vercel project: api/index.py  (FastAPI, POST /mcp)
        |  checks the key, then dispatches JSON-RPC: initialize, tools/list, tools/call
        v
 pulse/mcp.py  ->  pulse/registry.py  ->  the tool function
        |
        +--> pulse/discord.py  --> Discord REST API   (bot token)
        +--> pulse/gmail.py    --> imap/smtp.gmail.com (app password)
        +--> pulse/twitter.py  --> Apify API          (Apify token)
```

Each call is independent (stateless). The server holds no data between calls. Tokens are read from environment variables inside the tool that needs them, so a missing token only disables that one service.

## Components

| Path | Role |
|------|------|
| `api/index.py` | The web app: API-key check, the `/mcp` endpoint, a public health check |
| `pulse/mcp.py` | Minimal MCP server core (JSON-RPC over HTTP, no session state) |
| `pulse/registry.py` | The `@tool(...)` decorator, the `ToolError` type, and read/write/destructive labels |
| `pulse/discord.py`, `gmail.py`, `twitter.py` | The integrations |
| `scripts/pulse.mjs` | Installer: deploys to Vercel and wires up your AI clients |
| `scripts/gen_tools_doc.py` | Builds [docs/tools.md](tools.md) from the code |
| `tests/` | Offline tests plus an opt-in Discord end-to-end script |

## Security model

- **One key guards everything.** `MCP_API_KEY` is checked (in constant time) on every `/mcp` request. Whoever has it can use every connected service through your server, so treat it like a password and rotate it if it leaks ([how](vercel.md#rotating-the-key)).
- **Credentials never leave your Vercel project.** They are environment variables. They are not in the code, not in git, and not returned in tool results or error messages.
- **The AI client is trusted only as far as its labels.** Tools carry `read`, `write` or `destructive` hints so a client can ask you before deleting, banning or bulk-changing. The hints are advice to the client, not enforcement; the real limits are the permissions you grant each service (the Discord bot's role, the Gmail app password, the Apify plan).
- **Safe defaults.** Discord messages ping users only, never `@everyone`. Sending email is a separate, explicit tool from drafting it.
- **No rate limiting of its own.** A leaked key allows unlimited use of your accounts. Keep the key private and rotate on any doubt.
- **Blast radius.** A Gmail app password reaches the whole mailbox; a Discord bot reaches only the servers it was invited to and only with the permissions you chose. Grant the minimum you need.

## Design decisions

| Decision | Why |
|----------|-----|
| Serverless HTTP on Vercel | Free, no machine to run, works from any client, and each user gets an isolated deployment |
| Stateless JSON-RPC over plain HTTP | No sessions to store; works on short-lived functions; supported by current MCP clients |
| Discord over REST, no gateway | A gateway needs a long-lived connection, which serverless functions cannot keep. REST covers every action here |
| Gmail over IMAP/SMTP with an app password | Free and a minute to set up. Gmail's own API would need a Google Cloud project, an OAuth consent screen and periodic re-consent for personal apps. The trade-off is that an app password is broad; see the security model |
| `mcp-remote` for Claude Desktop | Claude Desktop only launches local commands, so a tiny bridge turns your URL into a local command |
| Tools return compact JSON | Smaller results cost fewer tokens and are easier for a model to use than raw API payloads |
| IDs are strings | Discord IDs exceed the safe range of JSON numbers |

## Known limits

- Vercel stops a request after 60 seconds.
- Discord: bots cannot create servers and can edit only their own messages. See the [Discord guide](discord.md#what-the-bot-cannot-do).
- Gmail: One account, and Trash/Spam are not searchable. See the [Gmail guide](gmail.md#limits).
- X search depends on a third-party scraper (Apify); its availability and prices are outside this project.

## Ideas for later (not promises)

- More services: Google Calendar, Slack, Telegram, GitHub, Notion.
- Gmail through the official API with OAuth, as an option next to the app password.
- Per-tool allow lists, so a deployment can expose only the tools you choose.
- Request logging and rate limiting.
- Multiple accounts per service.

Want to build one? See [Contributing](contributing.md).
