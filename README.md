# pulse-mcp

Your personal MCP server for your social accounts. Deploy it once to your own Vercel account, connect your accounts, and let Claude, Codex, Cursor or any MCP client read and act on them for you. Your tokens live only in your own Vercel project.

Today it ships with a complete **Discord** toolkit (read, send, edit, delete, react, threads, channels, roles, permissions, moderation), a full **Gmail** toolkit (search, read, send, reply, forward, drafts, labels, trash) and **X/Twitter search**. Adding another service is one small Python function (see [Add your own tool](#add-your-own-tool)).

- [Prerequisites](#prerequisites)
- [Install in one command](#install-in-one-command)
- [Deploy with the Vercel button](#deploy-with-the-vercel-button)
- [Connect your AI client](#connect-your-ai-client)
- [Discord setup and permissions](#discord-setup-and-permissions)
- [Gmail setup](#gmail-setup)
- [Tools](#tools)
- [Add your own tool](#add-your-own-tool)
- [Troubleshooting](#troubleshooting)

## Prerequisites

| You need | Why | Required |
|----------|-----|----------|
| [Vercel account](https://vercel.com/signup) (free) | Hosts your server | Yes |
| [Node.js 18+](https://nodejs.org) | Runs the installer and the Claude Desktop bridge | Yes |
| Discord bot token | Discord tools | Optional |
| [Apify token](https://console.apify.com/settings/integrations) (free plan works) | X/Twitter search | Optional |
| Gmail address + [app password](https://myaccount.google.com/apppasswords) | Gmail tools (free, see [Gmail setup](#gmail-setup)) | Optional |

Tools without their token return a clear error, so you can start with one service and add the rest later.

## Install in one command

```bash
git clone https://github.com/Dipeshpal/pulse-mcp.git
cd pulse-mcp
node scripts/pulse.mjs install
```

The installer will:

1. log you in to Vercel (browser window) if needed,
2. ask for your Discord token, Apify token and Gmail address + app password (press Enter to skip any),
3. generate a private API key for your server,
4. create the Vercel project, set the environment variables and deploy,
5. check that the server answers,
6. connect your AI clients (Claude Desktop and Claude Code by default),
7. print your Discord invite link with all the permissions the tools need.

Your URL and key are saved to `.pulse.local.json` (git-ignored). Non-interactive use: `node scripts/pulse.mjs install --name my-pulse --discord TOKEN --apify TOKEN --clients desktop,cursor`.

## Deploy with the Vercel button

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2FDipeshpal%2Fpulse-mcp&env=MCP_API_KEY,DISCORD_BOT_TOKEN,APIFY_TOKEN,GMAIL_ADDRESS,GMAIL_APP_PASSWORD&envDescription=MCP_API_KEY%20is%20any%20long%20random%20string%20you%20make%20up.%20All%20the%20others%20are%20optional.&envLink=https%3A%2F%2Fgithub.com%2FDipeshpal%2Fpulse-mcp%23prerequisites&project-name=pulse-mcp&repository-name=pulse-mcp)

1. Click the button and sign in to Vercel. It copies the repo to your GitHub and asks for three variables:
   - `MCP_API_KEY`: any long random string. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"` or `node -e "console.log(require('crypto').randomBytes(32).toString('base64url'))"`.
   - `DISCORD_BOT_TOKEN`, `APIFY_TOKEN`, `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD`: leave blank to skip a service.
2. Deploy. Your server is at `https://<project>.vercel.app`, with the MCP endpoint at `/mcp`.
3. Connect your client with the URL and your `MCP_API_KEY` (next section).

Manual CLI deploy, if you prefer:

```bash
npm i -g vercel && vercel login && vercel link --yes
printf '%s' 'YOUR_API_KEY'       | vercel env add MCP_API_KEY production
printf '%s' 'YOUR_DISCORD_TOKEN' | vercel env add DISCORD_BOT_TOKEN production
printf '%s' 'YOUR_APIFY_TOKEN'   | vercel env add APIFY_TOKEN production
printf '%s' 'you@gmail.com'      | vercel env add GMAIL_ADDRESS production
printf '%s' 'YOUR_APP_PASSWORD'  | vercel env add GMAIL_APP_PASSWORD production
vercel deploy --prod
```

Check it: `curl https://<project>.vercel.app/` should return `"status":"online"`.

## Connect your AI client

The server speaks MCP over HTTP at `https://<project>.vercel.app/mcp` and needs the header `Authorization: Bearer <MCP_API_KEY>`.

**Fastest:** `node scripts/pulse.mjs connect` (uses the saved install, or asks for URL and key). Flags: `--clients desktop,claude-code,cursor,codex`.

Or do it by hand. Replace `URL` and `KEY`.

**Claude Code**

```bash
claude mcp add --scope user --transport http pulse URL/mcp --header "Authorization: Bearer KEY"
```

**Claude Desktop** (Desktop only launches local commands, so [`mcp-remote`](https://www.npmjs.com/package/mcp-remote) bridges to your URL). Edit `claude_desktop_config.json` (`%APPDATA%\Claude\` on Windows, `~/Library/Application Support/Claude/` on macOS), then fully quit and reopen Claude Desktop:

```json
{
  "mcpServers": {
    "pulse": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "URL/mcp", "--header", "Authorization:${AUTH_HEADER}"],
      "env": { "AUTH_HEADER": "Bearer KEY" }
    }
  }
}
```

**Cursor** (`~/.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "pulse": { "url": "URL/mcp", "headers": { "Authorization": "Bearer KEY" } }
  }
}
```

**Codex**

```bash
codex mcp add pulse --url URL/mcp --bearer-token-env-var PULSE_MCP_API_KEY
```

then set `PULSE_MCP_API_KEY=KEY` in your environment (`setx PULSE_MCP_API_KEY KEY` on Windows, or `export` in your shell profile).

**Any other MCP client** that supports streamable HTTP: point it at `URL/mcp` with the Bearer header. Clients that only support local commands can use `npx -y mcp-remote URL/mcp --header "Authorization:${AUTH_HEADER}"`.

Then ask: *"List my Discord channels"*, *"Post 'standup in 5' in #general"*, or *"Search X for MCP servers"*.

## Discord setup and permissions

A bot token does not carry permissions by itself. What the bot may do is decided by the permissions it was invited with and by its role in each server. To use every tool:

1. **Create the bot**: [Developer Portal](https://discord.com/developers/applications) > New Application > Bot > Reset Token (this is your `DISCORD_BOT_TOKEN`).
2. **Turn on intents** (Bot tab > Privileged Gateway Intents): *Message Content Intent* (to read message text) and *Server Members Intent* (to list members).
3. **Turn off Public Bot** (Bot tab), so nobody else can add your bot to their servers.
4. **Invite it with the full permission set.** Open this link as the server owner (replace `CLIENT_ID` with your Application ID; the installer prints the finished link for you):

   ```
   https://discord.com/oauth2/authorize?client_id=CLIENT_ID&scope=bot&permissions=1494917442647
   ```

   That set is: View Channels, Send Messages (and in threads), Embed Links, Attach Files, Read Message History, Add Reactions, Use External Emojis, Manage Messages, Manage Channels, Manage Roles, Manage Threads, Create Public/Private Threads, Create Invites, Kick Members, Ban Members, Timeout Members. Re-running the link on a server the bot is already in updates its permissions.
5. **Mind the role order.** The bot can only manage roles and members positioned *below* its own role. In Server Settings > Roles, drag the bot's role above the roles you want it to manage.

Limits set by Discord, not by this project:

- Bots cannot create servers (Discord removed that endpoint for bots). Create the server yourself and invite the bot; it can then create channels, roles and threads.
- Bots can only edit their own messages. They can delete others' messages with Manage Messages.
- Bulk delete works only on messages younger than 14 days.
- A bot cannot grant a permission it does not hold itself.

Safety defaults: messages ping users only (`@everyone`, `@here` and role pings are blocked unless the caller asks with `mentions: "all"`); destructive tools are flagged so clients ask before running them; every write is tagged "via pulse-mcp" in the server's audit log.

## Gmail setup

Gmail runs over IMAP/SMTP with a Google **app password**. It is free, needs no Google Cloud project and no OAuth consent screen, and gives the server full control of the mailbox.

1. Turn on 2-Step Verification for the Google account (myaccount.google.com > Security).
2. Create an app password at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) (name it "pulse-mcp"). Google shows 16 letters; spaces are ignored.
3. Set two variables on Vercel (or answer the installer's prompts): `GMAIL_ADDRESS` (your address) and `GMAIL_APP_PASSWORD`. Redeploy.

Good to know:

- An app password grants full mailbox access. Anyone with your `MCP_API_KEY` can read and send your email through this server, so keep that key secret. Revoke the app password at any time from the same Google page.
- `gmail_send_email`, `gmail_reply`, `gmail_forward` and `gmail_send_draft` send immediately and cannot be unsent. Ask your assistant to create a draft first if you want to review.
- Message ids are stable ids in Gmail's All Mail. Search does not cover Trash and Spam.
- Search uses Gmail's own syntax: `from:alice is:unread newer_than:7d has:attachment label:work`.
- Attachments: up to about 4 MB when sending, about 2 MB when downloading (base64 in the tool result).
- One Gmail account per deployment. Google Workspace accounts work only if the admin allows app passwords and IMAP.
- Not supported: scheduled send, editing an existing draft in place (delete it and create a new one), and reading Trash/Spam.

## Tools

**Gmail**: `gmail_search`, `gmail_get_message`, `gmail_get_thread`, `gmail_get_attachment`, `gmail_list_labels`, `gmail_send_email` (HTML, cc/bcc, attachments), `gmail_reply` (reply-all, quoted original), `gmail_forward`, `gmail_create_draft`, `gmail_list_drafts`, `gmail_send_draft`, `gmail_delete_draft`, `gmail_modify` (read/unread, star, archive, labels), `gmail_trash`, `gmail_mark_spam`, `gmail_create_label`, `gmail_delete_label`

**Discord read**: `discord_list_guilds`, `discord_get_guild`, `discord_list_channels`, `discord_get_channel` (with permission overwrites), `discord_read_channel`, `discord_list_pins`, `discord_list_members` (search too), `discord_list_roles`, `discord_list_threads`

**Discord messages**: `discord_send_message` (text, embeds, replies), `discord_edit_message`, `discord_delete_message`, `discord_bulk_delete_messages`, `discord_pin_message`, `discord_add_reaction`, `discord_remove_reaction`

**Discord channels and threads**: `discord_create_channel` (text, voice, category, announcement, stage, forum, private), `discord_edit_channel` (also renames, archives and locks threads), `discord_delete_channel`, `discord_set_channel_permission`, `discord_delete_channel_permission`, `discord_create_invite`, `discord_create_thread` (from a message, standalone, private, or forum post), `discord_thread_member`

**Discord roles and moderation**: `discord_create_role`, `discord_edit_role`, `discord_delete_role`, `discord_member_role`, `discord_moderate_member` (kick, ban, unban, timeout)

**X/Twitter**: `twitter_search`

Channel and thread IDs are interchangeable wherever a `channel_id` is asked for.

## Add your own tool

Tools live in [`pulse/`](pulse). Create a file, register an async function, import it in [`api/index.py`](api/index.py):

```python
# pulse/hello.py
from .registry import tool

@tool("hello", "Say hello", {"name": {"type": "string"}}, ["name"], hint="read")
async def hello(args: dict):
    return {"message": f"Hello {args['name']}"}
```

`hint` is `read`, `write` or `destructive`; clients use it to decide when to ask for confirmation. Raise `ToolError("...")` for expected failures. Redeploy and the tool appears in every connected client.

Run locally:

```bash
cp .env.example .env    # fill in values
uv run --with fastapi --with aiohttp --with python-dotenv --with uvicorn python api/index.py
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `401` from the server, or a Vercel login page | Turn off Deployment Protection for production (Vercel project > Settings > Deployment Protection) |
| `403 Invalid API key` | The key in your client differs from `MCP_API_KEY` on Vercel. Redeploy after changing it. |
| `Missing Permissions` (Discord 50013) | Re-authorize the bot with the link above, and move its role higher in Server Settings > Roles |
| `Missing Access` (50001) | The bot is not in that server or cannot see that channel |
| `discord_list_members` fails | Enable *Server Members Intent* in the Developer Portal |
| Messages come back with empty `content` | Enable *Message Content Intent* in the Developer Portal |
| `Gmail login failed` | Use a 16-character app password (not your Google password), with 2-Step Verification on. Recreate it if unsure. |
| `GMAIL_ADDRESS and GMAIL_APP_PASSWORD are not set` | Add both on Vercel and redeploy |
| Gmail search misses a message | Search covers All Mail only. Trash and Spam are excluded. |
| Claude Desktop shows the server as failed | Fully quit Claude Desktop (tray icon too) and reopen. Check its logs (`%LOCALAPPDATA%\Claude\Logs\mcp-server-pulse.log` on Windows). Needs Node.js on PATH. |

## Security notes

- Never commit `.env*` or `.pulse.local.json` (git-ignored). Only `.env.example` is tracked.
- Your `MCP_API_KEY` is the only thing between the internet and your bot. Keep it secret. To rotate it, set a new value on Vercel, redeploy, and update your clients.
- If a token leaks, rotate it at the provider (Discord: Reset Token; Apify: regenerate) and update Vercel.
- Grant the bot only what you need. The permission link above is generous by design; drop what you do not use.
