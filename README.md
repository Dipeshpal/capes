# pulse-mcp

**Your personal [MCP](https://modelcontextprotocol.io/docs/getting-started/intro) server for Gmail, Discord and X.** Deploy it once to your own Vercel account, add the services you use, and let Claude, Codex, Cursor or any MCP client read and act on them for you. Manage everything from a built-in dashboard. Your credentials live only in your own Vercel project.

![The pulse-mcp dashboard: tools available, connectors configured, mode and endpoint](docs/assets/dashboard-overview.png)

- **Gmail:** search, read, send, reply, forward, drafts, labels, archive, trash.
- **Discord:** read, post, edit, delete, react, threads, channels, roles, permissions, moderation.
- **X/Twitter:** search tweets (through Apify).
- **Dashboard:** see what is connected, test credentials, review the tools, try read-only ones, and see recent activity. Limit what assistants can do with simple settings (read-only mode, disabled tools).

## Contents

- [Why it is useful](#why-it-is-useful)
- [What we are trying to achieve](#what-we-are-trying-to-achieve)
- [How it works](#how-it-works)
- [Set up in 5 steps](#set-up-in-5-steps)
- [Services and credentials](#services-and-credentials)
- [Deploy](#deploy)
- [The dashboard](#the-dashboard)
- [Connect your AI client](#connect-your-ai-client)
- [Using it](#using-it)
- [Tools](#tools)
- [Check that it works](#check-that-it-works)
- [Contributing](#contributing)
- [The `.claude` folder](#the-claude-folder)
- [Security](#security)
- [All guides](#all-guides)
- [References](#references)

## Why it is useful

Assistants are good at reading, summarizing and acting, but your real work lives in accounts they cannot reach. Every AI app also wants its own integration for each service, so you set up the same Gmail and Discord access again and again, and each copy holds your credentials somewhere different. pulse-mcp is the one door: **one private server, one key, the same tools in every client.**

### A day with pulse-mcp

Sam runs a small product and its Discord community, and answers customers from one Gmail inbox. Every morning Sam asks one question in Claude:

> **Sam:** Give me a briefing. Unread customer emails from the last day, unanswered questions in #support, and what people are saying about our product on X.

The assistant, using tools from the same server:

1. `gmail_search` for `is:unread newer_than:1d`, then `gmail_get_message` on the ones that look like customers. It groups them: 3 billing questions, 1 bug report, 2 newsletters.
2. `discord_read_channel` on #support, and finds 4 questions nobody answered.
3. `twitter_search` for the product name, and summarizes the tone of 20 recent tweets.

> **Sam:** Draft replies to the billing emails, and answer the two easy Discord questions. Show me everything before you send.

4. `gmail_create_draft` for each reply (drafts, nothing sent yet).
5. Shows Sam the drafts and the two Discord answers. Sam approves.
6. `gmail_send_draft`, `discord_send_message`, and `gmail_modify` to label and archive the handled mail.

That is about five minutes instead of forty, and the assistant never had direct access to Sam's accounts: everything went through Sam's own server, with Sam's own limits. When Sam wants an assistant to only look, one switch in the dashboard hides every tool that sends or deletes.

*This is an illustration of what the tools make possible, not a recording.*

### Why not just use each app's built-in connectors?

- **One setup for every client.** The same server works in Claude Desktop, Claude Code, Cursor and Codex, not just one app.
- **You hold the credentials.** They sit in your own Vercel project, not in a third-party platform.
- **You set the limits.** Switch connectors and single tools off, or make the whole server read-only, and see what was called.
- **Free to run** for personal use, and easy to extend with your own tools.

Other ways to solve this exist (hosted platforms like Composio, gateways like MetaMCP, single-service MCP servers). A short comparison is in [What pulse-mcp is for](docs/architecture.md#how-it-compares).

## What we are trying to achieve

- **Personal and private:** you deploy your own copy; there is no central service.
- **Easy to set up:** deploy from your browser, then a click-by-click guide per service. About 20 minutes from nothing.
- **Complete:** full toolkits for Gmail, Discord and X, not demos.
- **Safe by default:** tools are labelled read, write or destructive so clients ask before risky calls; sending is always explicit; you can lock the server down with a setting.
- **Extendable and contributor-friendly:** a new tool is one Python function, and the repo ships its own Claude Code setup and safety checks.

The full picture, design decisions and security model: [What pulse-mcp is for](docs/architecture.md).

## How it works

```
Claude / Codex / Cursor  --MCP over HTTPS + your key-->  your server on Vercel  -->  Gmail, Discord, X
                                                                  ^
                                          you, in a browser -->  /dashboard
```

Your server exposes `POST /mcp`, protected by a secret key you create (`MCP_API_KEY`), and a dashboard at `/dashboard` that you sign in to with the same key (no database, no accounts). The service credentials (Gmail app password, Discord bot token, Apify token) are Vercel environment variables and never leave your project.

## Set up in 5 steps

About 20 minutes, most of it creating credentials. Skip any service you do not need.

| # | Step | Where | Time |
|---|------|-------|------|
| 1 | Create a free Vercel account and your `MCP_API_KEY` | [Vercel guide](docs/vercel.md) | 3 min |
| 2 | Get credentials for the services you want | [Discord](docs/discord.md), [Gmail](docs/gmail.md), [Apify](docs/apify.md) guides | 3 to 10 min each |
| 3 | **Deploy on Vercel** and paste your key and credentials | [Option A](#option-a-deploy-on-vercel-recommended) | 3 min |
| 4 | Open `/dashboard`, sign in, click **Test connection** on each connector; invite your Discord bot with the link in the Discord guide | your browser | 3 min |
| 5 | Connect your AI client and ask "List my Discord channels" | Claude, Codex, Cursor | 2 min |

## Services and credentials

Click a guide for the exact steps, permissions and limits of each service.

| Service | What it unlocks | What you need | Where to get it | Setup guide |
|---------|-----------------|---------------|-----------------|-------------|
| **Vercel** (required) | Hosts your server and dashboard (free Hobby plan) | A Vercel account and a key you invent, `MCP_API_KEY` (24+ characters) | [vercel.com/signup](https://vercel.com/signup) | [Vercel setup](docs/vercel.md) |
| **Gmail** | Read, send and organize email (free, no Google Cloud project) | `GMAIL_ADDRESS` and an app password `GMAIL_APP_PASSWORD` | [Google app passwords](https://myaccount.google.com/apppasswords) | [Gmail setup](docs/gmail.md) |
| **Discord** | Read and manage servers, channels, messages, roles | Bot token `DISCORD_BOT_TOKEN`, bot invited with permissions | [Developer Portal](https://discord.com/developers/applications) | [Discord setup](docs/discord.md) |
| **Apify** (for X/Twitter) | Search tweets | API token `APIFY_TOKEN` | [Apify API settings](https://console.apify.com/settings/integrations) | [Apify setup](docs/apify.md) |
| *Database* | **Not needed.** Nothing is stored on the server. | (Advanced, optional: a free Redis via `vercel integration add upstash` lets the dashboard flip switches without redeploying.) | [Vercel Marketplace](https://vercel.com/marketplace/upstash) | [Dashboard guide](docs/dashboard.md#switches-read-only-mode-and-where-settings-are-stored) |

Only `MCP_API_KEY` is required. A tool whose credentials are missing returns a clear message instead of failing.

## Deploy

### Option A: deploy on Vercel (recommended)

No install, no terminal.

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2FDipeshpal%2Fpulse-mcp&env=MCP_API_KEY,DISCORD_BOT_TOKEN,APIFY_TOKEN,GMAIL_ADDRESS,GMAIL_APP_PASSWORD&envDescription=MCP_API_KEY%20is%20any%20long%20random%20string%20you%20make%20up%20(24%2B%20characters).%20All%20the%20others%20are%20optional.&envLink=https%3A%2F%2Fgithub.com%2FDipeshpal%2Fpulse-mcp%2Fblob%2Fmaster%2Fdocs%2Fvercel.md&project-name=pulse-mcp&repository-name=pulse-mcp)

1. Click the button and sign in to Vercel. It copies the repository into your GitHub account.
2. Paste your `MCP_API_KEY` ([how to make one](docs/vercel.md#2-create-your-mcp_api_key)) and the credentials for the services you want. Leave the rest empty.
3. Click **Deploy**, then open `https://<project>.vercel.app/dashboard` and sign in with your key.

The button works for anyone once the repository is public. Before that, or from a fork, use **Vercel > Add New > Project > Import Git Repository**, choose the repo and add the same variables. Details, Deployment Protection and key rotation: [Vercel guide](docs/vercel.md).

### Option B: one command from your computer

Needs [Node.js 18+](https://nodejs.org). It logs you in to Vercel, generates a strong key, asks for your credentials (Enter skips any), deploys, connects your AI clients and prints your Discord invite link:

```bash
git clone https://github.com/Dipeshpal/pulse-mcp.git
cd pulse-mcp
node scripts/pulse.mjs install
```

Your address and key are saved to `.pulse.local.json` (git-ignored). Non-interactive: `node scripts/pulse.mjs install --name my-pulse --discord TOKEN --apify TOKEN --gmail you@gmail.com --gmail-password APP_PASSWORD --clients desktop,cursor`.

### Option C: Vercel CLI by hand

Step by step in the [Vercel guide](docs/vercel.md#option-c-vercel-cli-by-hand).

## The dashboard

Open `https://<project>.vercel.app/dashboard` and sign in with your `MCP_API_KEY`.

![Connectors: credentials status, tool counts, enable switch and connection test](docs/assets/dashboard-connectors.png)

- **Overview, Connectors, Tools:** what is connected and which tools clients can see.
- **Test connection:** a read-only check of each service's credentials.
- **Limits:** turn a service or a single tool off, or hide everything that changes data. No database needed: set `PULSE_READ_ONLY`, `PULSE_DISABLED_CONNECTORS` or `PULSE_DISABLED_TOOLS` on Vercel (an optional free Redis lets you flip these on the dashboard without redeploying).
- **Try:** run read-only tools with a form.
- **Activity:** recent calls, without arguments or results.
- **Connect a client:** copy-ready config for Claude, Cursor and Codex.

Full walkthrough and security details: [Dashboard guide](docs/dashboard.md).

## Connect your AI client

Every client needs your address `https://<project>.vercel.app/mcp` and your `MCP_API_KEY` as `Authorization: Bearer <key>`. The dashboard's **Connect a client** tab shows the exact config. Or, from a clone of the repo:

```bash
node scripts/pulse.mjs connect        # configures Claude Desktop, Claude Code, Cursor, Codex
```

By hand, per client ([client guide](docs/clients.md)):

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

Sending mail and messages cannot be undone, so ask for a draft first when it matters. [Using pulse-mcp](docs/usage.md) has more examples and safety habits.

## Tools

62 tools. The list below is the quick view; [docs/tools.md](docs/tools.md) is the generated reference with every tool's description, kind and arguments.

**Gmail**: `gmail_search`, `gmail_get_message`, `gmail_get_thread`, `gmail_get_attachment`, `gmail_list_labels`, `gmail_send_email` (HTML, cc/bcc, attachments), `gmail_reply` (reply-all, quoted original), `gmail_forward`, `gmail_create_draft`, `gmail_list_drafts`, `gmail_send_draft`, `gmail_delete_draft`, `gmail_modify` (read/unread, star, archive, labels), `gmail_trash`, `gmail_mark_spam`, `gmail_create_label`, `gmail_delete_label`

**Discord read**: `discord_list_guilds`, `discord_get_guild`, `discord_list_channels`, `discord_get_channel` (with permission overwrites), `discord_read_channel`, `discord_get_message`, `discord_list_pins`, `discord_list_reactions`, `discord_list_members` (search too), `discord_list_roles`, `discord_list_threads`, `discord_list_invites`, `discord_get_audit_log`, `discord_read_dm`

**Discord messages**: `discord_send_message` (text, embeds, replies), `discord_send_dm`, `discord_send_file` (base64 upload), `discord_create_poll`, `discord_edit_message`, `discord_delete_message`, `discord_bulk_delete_messages`, `discord_pin_message`, `discord_add_reaction`, `discord_remove_reaction`

**Discord channels and threads**: `discord_create_channel` (text, voice, category, announcement, stage, forum, private), `discord_edit_channel` (also renames, archives and locks threads), `discord_delete_channel`, `discord_set_channel_permission`, `discord_delete_channel_permission`, `discord_create_invite`, `discord_delete_invite`, `discord_create_thread` (from a message, standalone, private, or forum post with tags), `discord_thread_member`

**Discord forums and webhooks**: `discord_list_forum_tags`, `discord_manage_forum_tag`, `discord_list_webhooks`, `discord_create_webhook`, `discord_send_webhook_message` (the webhook token never leaves the server), `discord_delete_webhook`

**Discord roles and moderation**: `discord_create_role`, `discord_edit_role`, `discord_delete_role`, `discord_member_role`, `discord_moderate_member` (kick, ban, unban, timeout)

**X/Twitter**: `twitter_search`

Tools are flagged read, write or destructive so clients can ask before risky calls, and you can switch any of them off in the dashboard. Discord channel and thread IDs are interchangeable wherever a `channel_id` is asked for.

## Check that it works

1. Open `/dashboard`, sign in, and click **Test connection** on each connector.
2. Or `curl https://<project>.vercel.app/health` returns `"status":"online"`.
3. In your AI client, ask "List my Discord channels" (Discord), "How many unread emails do I have?" (Gmail) or "Search X for MCP servers" (Apify).
4. Something wrong? [Troubleshooting](docs/troubleshooting.md) maps every common error to its fix.

## Contributing

Anyone can contribute: fix a bug, sharpen a guide, add a tool, or improve the dashboard. Deployment for users is Vercel only, so contributor tooling is kept minimal.

1. Read [What pulse-mcp is for](docs/architecture.md) and [Contributing](docs/contributing.md).
2. Fork, branch (`feat/...`, `fix/...`, `docs/...`), make one focused change.
3. Run the checks (no credentials needed; the full list is in [Contributing](docs/contributing.md#checks)):

   ```bash
   uv run --with fastapi --with aiohttp --with python-dotenv --with httpx python tests/protocol.py
   uv run --with fastapi --with aiohttp --with python-dotenv --with httpx python tests/dashboard.py
   uv run --with fastapi --with aiohttp --with python-dotenv python tests/gmail_offline.py
   python tests/claude_config.py
   uvx ruff check . && uvx ruff format --check .
   ```

4. Open a pull request using the template. Say what you tested and what you could not. CI runs the same checks, a guard for assistant/CI configuration, and a secret scan.

Adding a tool takes one Python function:

```python
# pulse/hello.py  (then import it in api/index.py)
from .registry import tool

@tool("hello", "Say hello", {"name": {"type": "string"}}, ["name"], hint="read")
async def hello(args: dict):
    return {"message": f"Hello {args['name']}"}
```

Changes to `.claude/`, `.github/`, `scripts/`, authentication code, `vercel.json` or dependencies always need the maintainer's review (see [Security](#security)).

## The `.claude` folder

The repo includes its Claude Code setup so a contributor's assistant knows the project from the first prompt:

| Path | What it gives you |
|------|-------------------|
| [`CLAUDE.md`](CLAUDE.md) | Overview, commands, conventions, gotchas and security rules, loaded in every session |
| [`.claude/rules/`](.claude/rules) | Focused rules that load when you touch matching files (tools, dashboard, Discord, Gmail, installer, docs) plus always-on security rules |
| [`.claude/skills/`](.claude/skills) | Slash commands: `/add-tool`, `/run-tests`, `/deploy`, `/security-audit` |
| [`.claude/agents/tool-reviewer.md`](.claude/agents/tool-reviewer.md) | A reviewer subagent for tool changes, with shared memory in [`.claude/agent-memory/`](.claude/agent-memory/tool-reviewer/MEMORY.md) |
| [`.claude/settings.json`](.claude/settings.json) | Shared permissions: safe commands allowed; reading secret files and force pushes denied |

With Claude Code: run `claude` in the repo, then for example `/add-tool slack slack_send_message`, `/run-tests`, and ask `@tool-reviewer` to review your diff. What each file does is in [docs/contributing.md](docs/contributing.md#the-claude-folder).

## Security

- **One key guards everything.** `MCP_API_KEY` (24+ characters, checked in constant time) protects `/mcp` and the dashboard. Anyone who has it can read your email and act through your Discord bot, so keep it secret and rotate it if in doubt ([how](docs/vercel.md#rotating-the-key)).
- **Credentials stay in your Vercel project.** Never commit `.env*` or `.pulse.local.json` (git-ignored). The dashboard and tool results never show secret values.
- **Strict by default:** arguments are validated before any call, dashboard sessions are signed cookies with CSRF protection, and Redis outages fail closed into read-only mode.
- **Contributors cannot slip in behaviour changes unnoticed:** CI blocks hooks, wildcard permissions, hidden text, unapproved dependencies and risky workflows, hash-pins every executable file under `.claude/` and `.github/`, and `CODEOWNERS` routes sensitive paths to the maintainer.
- **If a token leaks,** rotate it at the provider (Discord: Reset Token; Apify: regenerate; Google: delete the app password) and update Vercel.

Details in [SECURITY.md](SECURITY.md) and the [security model](docs/architecture.md#security-model).

## All guides

**Setup:** [Vercel](docs/vercel.md) | [Discord](docs/discord.md) | [Gmail](docs/gmail.md) | [Apify](docs/apify.md) | [Connect your client](docs/clients.md)

**Use:** [Dashboard](docs/dashboard.md) | [Using pulse-mcp](docs/usage.md) | [Tool reference](docs/tools.md) | [Troubleshooting](docs/troubleshooting.md)

**Understand and contribute:** [What pulse-mcp is for](docs/architecture.md) | [Contributing](docs/contributing.md) | [Security policy](SECURITY.md) | [Release checklist](docs/release-checklist.md)

## References

- [Model Context Protocol: introduction](https://modelcontextprotocol.io/docs/getting-started/intro) and [connecting Claude Code to MCP servers](https://code.claude.com/docs/en/mcp)
- [Claude Code directory layout](https://code.claude.com/docs/en/claude-directory), which the `.claude/` folder follows
- [Discord developer documentation](https://discord.com/developers/docs/intro)
- [Gmail IMAP extensions](https://developers.google.com/workspace/gmail/imap/imap-extensions) (search syntax, labels, threads) and [Google app passwords](https://support.google.com/accounts/answer/185833)
- [Apify Tweet Scraper](https://apify.com/apidojo/tweet-scraper), the default actor behind `twitter_search`
- [Vercel Functions](https://vercel.com/docs/functions) and the [Upstash Redis integration](https://vercel.com/marketplace/upstash)
- Inspiration: [kebab-mcp](https://github.com/Yassinello/kebab-mcp) showed how useful a dashboard on a personal Vercel MCP server can be. pulse-mcp's dashboard is an independent implementation written from scratch.
