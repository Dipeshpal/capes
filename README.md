# pulse-mcp

Your personal [MCP](https://modelcontextprotocol.io) server for your own accounts. Deploy it once to your own Vercel account, add the services you use, and let Claude, Codex, Cursor or any MCP client work with them for you:

- **Discord**: read, post, edit, delete, react, threads, channels, roles, permissions, moderation.
- **Gmail**: search, read, send, reply, forward, drafts, labels, archive, trash.
- **X/Twitter**: search tweets.

Your tokens live only in your own Vercel project. Nothing is shared with anyone. You can start with one service and add the others later.

> "Summarize my unread emails from today and draft replies."  
> "Post the release notes in #announcements and pin them."  
> "Search X for people talking about MCP servers."

## Contents

- [What we are trying to achieve](#what-we-are-trying-to-achieve)
- [How it works](#how-it-works)
- [Set up in 6 steps](#set-up-in-6-steps)
- [Services and credentials](#services-and-credentials)
- [Deploy](#deploy)
- [Connect your AI client](#connect-your-ai-client)
- [Using it](#using-it)
- [Tools](#tools)
- [Check that it works](#check-that-it-works)
- [Contributing](#contributing)
- [The `.claude` folder](#the-claude-folder)
- [Security](#security)
- [All guides](#all-guides)

## What we are trying to achieve

Assistants are great at reading, summarizing and acting, but your real work lives in accounts they cannot reach: your inbox, your community chat, your social feeds. pulse-mcp is a small server that gives an assistant controlled access to **your own** accounts through one standard door (MCP), so the same setup works in Claude, Codex, Cursor and any other MCP client.

- **Personal and private:** you deploy your own copy; credentials stay in your own Vercel project; there is no central service.
- **Easy to set up:** one command or one button, plus a click-by-click guide per service. About 20 minutes from nothing.
- **Complete:** full toolkits for Discord, Gmail and X, not demos.
- **Safe by default:** tools are labelled read, write or destructive so clients ask before risky calls; sending is always explicit.
- **Free to run** for personal use, and **easy to extend** with your own tools.

The full picture, design decisions, security model and ideas for later are in [What pulse-mcp is for](docs/architecture.md).

## How it works

```
Claude / Codex / Cursor  --MCP over HTTPS + your key-->  your server on Vercel  -->  Discord, Gmail, X
```

Your server exposes one endpoint, `POST /mcp`, protected by a secret key you create (`MCP_API_KEY`). The service credentials (bot token, Gmail app password, Apify token) are stored as Vercel environment variables and never leave your project.

## Set up in 6 steps

Total time: about 20 minutes, most of it creating credentials. Skip any service you do not need.

| # | Step | Where | Time |
|---|------|-------|------|
| 1 | Install [Node.js 18+](https://nodejs.org) and clone this repo | your computer | 2 min |
| 2 | Create a Vercel account | [Vercel guide](docs/vercel.md) | 3 min |
| 3 | Get credentials for the services you want | [Discord](docs/discord.md), [Gmail](docs/gmail.md), [Apify](docs/apify.md) guides | 3 to 10 min each |
| 4 | Deploy with one command: `node scripts/pulse.mjs install` | your terminal | 3 min |
| 5 | Invite your Discord bot to your server (link printed by step 4) | Discord | 2 min |
| 6 | Restart your AI client and ask "List my Discord channels" | Claude, Codex, Cursor | 1 min |

```bash
git clone https://github.com/Dipeshpal/pulse-mcp.git
cd pulse-mcp
node scripts/pulse.mjs install
```

## Services and credentials

Click a guide for the exact steps, permissions and limits of each service.

| Service | What it unlocks | What you need | Where to get it | Setup guide |
|---------|-----------------|---------------|-----------------|-------------|
| **Vercel** (required) | Hosts your server (free Hobby plan) | A Vercel account and a key you invent, `MCP_API_KEY` | [vercel.com/signup](https://vercel.com/signup) | [Vercel setup](docs/vercel.md) |
| **Discord** | Read and manage servers, channels, messages, roles | Bot token `DISCORD_BOT_TOKEN`, bot invited with permissions | [Developer Portal](https://discord.com/developers/applications) | [Discord setup](docs/discord.md) |
| **Gmail** | Read, send and organize email (free, no Google Cloud project) | `GMAIL_ADDRESS` and an app password `GMAIL_APP_PASSWORD` | [Google app passwords](https://myaccount.google.com/apppasswords) | [Gmail setup](docs/gmail.md) |
| **Apify** (for X/Twitter) | Search tweets | API token `APIFY_TOKEN` | [Apify API settings](https://console.apify.com/settings/integrations) | [Apify setup](docs/apify.md) |

Only `MCP_API_KEY` is required. A tool whose credentials are missing returns a clear message instead of failing. Local runs read the same names from `.env` (copy `.env.example`).

## Deploy

### Option A: one command (recommended)

```bash
node scripts/pulse.mjs install
```

It will:

1. log you in to Vercel (a browser window opens) if needed,
2. ask for your Discord token, Gmail address and app password, and Apify token (press Enter to skip any),
3. generate your `MCP_API_KEY`,
4. create the Vercel project, set the environment variables and deploy,
5. check that the server answers,
6. connect your AI clients (Claude Desktop and Claude Code by default),
7. print your Discord invite link with every permission the tools need.

Your address and key are saved in `.pulse.local.json` (git-ignored). For scripts: `node scripts/pulse.mjs install --name my-pulse --discord TOKEN --apify TOKEN --gmail you@gmail.com --gmail-password APP_PASSWORD --clients desktop,cursor`.

### Option B: deploy with the Vercel button

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2FDipeshpal%2Fpulse-mcp&env=MCP_API_KEY,DISCORD_BOT_TOKEN,APIFY_TOKEN,GMAIL_ADDRESS,GMAIL_APP_PASSWORD&envDescription=MCP_API_KEY%20is%20any%20long%20random%20string%20you%20make%20up.%20All%20the%20others%20are%20optional.&envLink=https%3A%2F%2Fgithub.com%2FDipeshpal%2Fpulse-mcp%2Fblob%2Fmaster%2Fdocs%2Fvercel.md&project-name=pulse-mcp&repository-name=pulse-mcp)

The button works for anyone once the repository is public. It copies the repo to your GitHub and asks for the environment variables. Generate `MCP_API_KEY` first (see the [Vercel guide](docs/vercel.md#2-create-your-mcp_api_key)); leave the service variables blank to skip a service. Then connect your client (next section).

### Option C: manual

Step-by-step CLI and dashboard instructions, environment variables, Deployment Protection and key rotation are in the [Vercel guide](docs/vercel.md).

## Connect your AI client

Every client needs your address `https://<project>.vercel.app/mcp` and your `MCP_API_KEY` as `Authorization: Bearer <key>`.

```bash
node scripts/pulse.mjs connect        # configures Claude Desktop, Claude Code, Cursor, Codex
```

Or set a client up by hand. The [client guide](docs/clients.md) has the exact steps and config for each:

| Client | How it connects | Guide |
|--------|-----------------|-------|
| Claude Desktop | `mcp-remote` bridge in `claude_desktop_config.json` | [Claude Desktop](docs/clients.md#claude-desktop) |
| Claude Code | `claude mcp add --transport http ...` | [Claude Code](docs/clients.md#claude-code) |
| Cursor | `url` and `headers` in `~/.cursor/mcp.json` | [Cursor](docs/clients.md#cursor) |
| Codex | `codex mcp add ... --bearer-token-env-var` | [Codex](docs/clients.md#codex) |
| Anything else | Streamable HTTP with the Bearer header | [Other clients](docs/clients.md#any-other-mcp-client) |

Restart the client after connecting so it loads the tools.

## Using it

Once connected, just talk to your assistant and it picks the tools:

- "How many unread emails do I have? Summarize the five newest."
- "Draft a reply to the last email from Sam. Show me before sending."
- "Read the last 50 messages in #support and list the open questions."
- "Post the release notes in #announcements and pin them."
- "Search X for people talking about MCP servers."

Sending mail and messages cannot be undone, so ask for a draft first when it matters. [Using pulse-mcp](docs/usage.md) has more examples, safety habits, and how to call the server with `curl` for debugging.

## Tools

47 tools. The table below is the quick list; [docs/tools.md](docs/tools.md) is the generated reference with every tool's description, kind and arguments.

**Gmail**: `gmail_search`, `gmail_get_message`, `gmail_get_thread`, `gmail_get_attachment`, `gmail_list_labels`, `gmail_send_email` (HTML, cc/bcc, attachments), `gmail_reply` (reply-all, quoted original), `gmail_forward`, `gmail_create_draft`, `gmail_list_drafts`, `gmail_send_draft`, `gmail_delete_draft`, `gmail_modify` (read/unread, star, archive, labels), `gmail_trash`, `gmail_mark_spam`, `gmail_create_label`, `gmail_delete_label`

**Discord read**: `discord_list_guilds`, `discord_get_guild`, `discord_list_channels`, `discord_get_channel` (with permission overwrites), `discord_read_channel`, `discord_list_pins`, `discord_list_members` (search too), `discord_list_roles`, `discord_list_threads`

**Discord messages**: `discord_send_message` (text, embeds, replies), `discord_edit_message`, `discord_delete_message`, `discord_bulk_delete_messages`, `discord_pin_message`, `discord_add_reaction`, `discord_remove_reaction`

**Discord channels and threads**: `discord_create_channel` (text, voice, category, announcement, stage, forum, private), `discord_edit_channel` (also renames, archives and locks threads), `discord_delete_channel`, `discord_set_channel_permission`, `discord_delete_channel_permission`, `discord_create_invite`, `discord_create_thread` (from a message, standalone, private, or forum post), `discord_thread_member`

**Discord roles and moderation**: `discord_create_role`, `discord_edit_role`, `discord_delete_role`, `discord_member_role`, `discord_moderate_member` (kick, ban, unban, timeout)

**X/Twitter**: `twitter_search`

Notes: tools are flagged read, write or destructive so clients can ask before risky calls. Gmail send tools send immediately; ask for a draft first if you want to review. Discord channel and thread IDs are interchangeable wherever a `channel_id` is asked for. Limits and safety defaults are in each service guide.

## Check that it works

1. `curl https://<project>.vercel.app/` returns `"status":"online"`.
2. In your AI client, ask "List my Discord channels" (Discord), "How many unread emails do I have?" (Gmail) or "Search X for MCP servers" (Apify).
3. Something wrong? [Troubleshooting](docs/troubleshooting.md) maps every common error to its fix.

## Contributing

Anyone can contribute: fix a bug, sharpen a guide, add a tool, or build a whole new service (Calendar, Slack, Telegram...).

1. Read [What pulse-mcp is for](docs/architecture.md) and [Contributing](docs/contributing.md).
2. Fork, branch (`feat/...`, `fix/...`, `docs/...`), make one focused change.
3. Run the checks (no credentials needed):

   ```bash
   uv run --with fastapi --with aiohttp --with python-dotenv --with httpx python tests/protocol.py
   uv run --with fastapi --with aiohttp --with python-dotenv python tests/gmail_offline.py
   uv run --with aiohttp python scripts/gen_tools_doc.py --check
   python tests/check_docs.py
   ```

4. Open a pull request using the template. Say what you tested and what you could not. CI runs the same checks plus a secret scan.

New service? Open an issue first with the feature template. Adding a tool takes one Python function:

```python
# pulse/hello.py  (then import it in api/index.py)
from .registry import tool

@tool("hello", "Say hello", {"name": {"type": "string"}}, ["name"], hint="read")
async def hello(args: dict):
    return {"message": f"Hello {args['name']}"}
```

Run the server locally: `cp .env.example .env`, fill it in, then `uv run --with fastapi --with aiohttp --with python-dotenv --with uvicorn python api/index.py`.

## The `.claude` folder

The repo includes its Claude Code setup so a contributor's assistant knows the project from the first prompt:

| Path | What it gives you |
|------|-------------------|
| [`CLAUDE.md`](CLAUDE.md) | Overview, commands, conventions, gotchas and security rules, loaded in every session |
| [`.claude/rules/`](.claude/rules) | Focused rules that load when you touch matching files (tools, Discord, Gmail, installer, docs) plus always-on security rules |
| [`.claude/skills/`](.claude/skills) | Slash commands: `/add-tool`, `/run-tests`, `/deploy`, `/security-audit` |
| [`.claude/agents/tool-reviewer.md`](.claude/agents/tool-reviewer.md) | A reviewer subagent for tool changes, with shared memory in [`.claude/agent-memory/`](.claude/agent-memory/tool-reviewer/MEMORY.md) |
| [`.claude/settings.json`](.claude/settings.json) | Shared permissions: safe commands allowed; reading secret files and force pushes denied |

With Claude Code: run `claude` in the repo, then for example `/add-tool slack slack_send_message`, `/run-tests`, and ask `@tool-reviewer` to review your diff. The full table of what each file does is in [docs/contributing.md](docs/contributing.md#the-claude-folder).

## Security

- Never commit `.env*` or `.pulse.local.json` (both git-ignored; only `.env.example` is tracked).
- `MCP_API_KEY` is the only thing between the internet and your accounts. Anyone with it can read your email and act through your Discord bot. Keep it secret; rotate it as described in the [Vercel guide](docs/vercel.md#rotating-the-key).
- If a token leaks, rotate it at the provider (Discord: Reset Token; Apify: regenerate; Google: delete the app password) and update Vercel.
- Give each service only what you need. The Discord invite link and Gmail app password are powerful by design.

## All guides

**Setup:** [Vercel](docs/vercel.md) | [Discord](docs/discord.md) | [Gmail](docs/gmail.md) | [Apify](docs/apify.md) | [Connect your client](docs/clients.md)

**Use:** [Using pulse-mcp](docs/usage.md) | [Tool reference](docs/tools.md) | [Troubleshooting](docs/troubleshooting.md)

**Understand and contribute:** [What pulse-mcp is for](docs/architecture.md) | [Contributing](docs/contributing.md)
