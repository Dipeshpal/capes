# research-tools-mcp

A personal [MCP](https://modelcontextprotocol.io) server you deploy to your own Vercel account and connect to Claude Desktop, Claude Code, Cursor or Codex. Your tokens live only in your Vercel environment variables. Nothing is shared.

**Tools**

| Tool | What it does | Needs |
|------|--------------|-------|
| `discord_list_channels` | Lists servers and text channels your bot can see | `DISCORD_BOT_TOKEN` |
| `discord_read_channel` | Reads recent messages from a channel | `DISCORD_BOT_TOKEN` |
| `twitter_search` | Searches tweets on X (via Apify) | `APIFY_TOKEN` |

The server speaks MCP over HTTP at `POST /mcp` and requires `Authorization: Bearer <RESEARCH_API_KEY>`.

## 1. Get your credentials

- **Discord bot token**: [Developer Portal](https://discord.com/developers/applications) > New Application > Bot > Reset Token. Turn on **Message Content Intent**, then invite the bot to your server (OAuth2 > URL Generator > `bot`, permissions *View Channels* + *Read Message History*).
- **Apify token**: [apify.com](https://apify.com) > Settings > API & Integrations. The free plan works.
- **Your API key** (protects your server; make one up):
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(32))"
  ```

Both Discord and Apify are optional. A tool without its token returns a clear error.

## 2. Deploy to Vercel

Fork or clone this repo, then:

```bash
npm i -g vercel
vercel login
vercel link --yes            # run inside the repo

printf '%s' 'YOUR_DISCORD_BOT_TOKEN' | vercel env add DISCORD_BOT_TOKEN production
printf '%s' 'YOUR_APIFY_TOKEN'       | vercel env add APIFY_TOKEN production
printf '%s' 'YOUR_API_KEY'           | vercel env add RESEARCH_API_KEY production

vercel deploy --prod
```

(Or import the repo in the Vercel dashboard and add the three variables under Settings > Environment Variables.)

Check it:

```bash
curl https://YOUR-PROJECT.vercel.app/
```

Disable Vercel "Deployment Protection" for production (Settings > Deployment Protection) or the endpoint will answer with a login page instead of MCP.

## 3. Connect a client

Replace `https://YOUR-PROJECT.vercel.app` and `YOUR_API_KEY` below.

**Claude Code**

```bash
claude mcp add --transport http research https://YOUR-PROJECT.vercel.app/mcp \
  --header "Authorization: Bearer YOUR_API_KEY"
```

**Cursor** (`~/.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "research": {
      "url": "https://YOUR-PROJECT.vercel.app/mcp",
      "headers": { "Authorization": "Bearer YOUR_API_KEY" }
    }
  }
}
```

**Claude Desktop** (`claude_desktop_config.json`; Desktop only launches local commands, so [`mcp-remote`](https://www.npmjs.com/package/mcp-remote) bridges to the URL. Needs Node.js.)

```json
{
  "mcpServers": {
    "research": {
      "command": "npx",
      "args": [
        "-y", "mcp-remote",
        "https://YOUR-PROJECT.vercel.app/mcp",
        "--header", "Authorization:${AUTH_HEADER}"
      ],
      "env": { "AUTH_HEADER": "Bearer YOUR_API_KEY" }
    }
  }
}
```

Fully quit and reopen Claude Desktop afterwards. The config file is at `%APPDATA%\Claude\` on Windows and `~/Library/Application Support/Claude/` on macOS.

**Codex** (`~/.codex/config.toml`)

```toml
[mcp_servers.research]
url = "https://YOUR-PROJECT.vercel.app/mcp"
bearer_token_env_var = "RESEARCH_API_KEY"
```

Then try: *"List my Discord channels"* or *"Search Twitter for MCP servers"*.

## Add your own tool

Everything is in [`api/index.py`](api/index.py). Register an async function:

```python
@tool(
    "my_tool",
    "What it does",
    {"query": {"type": "string", "description": "Search text"}},
    ["query"],
)
async def my_tool(args: dict):
    return {"echo": args["query"]}
```

Redeploy and it shows up in every connected client.

## Run locally

```bash
cp .env.example .env         # fill in values
uv run --with fastapi --with aiohttp --with python-dotenv --with uvicorn python api/index.py
```

## Security notes

- Never commit `.env*` files (they are git-ignored; only `.env.example` is tracked).
- If a token leaks, rotate it at the provider and update the Vercel variable. Rotate `RESEARCH_API_KEY` by setting a new value and redeploying.
- The Discord bot can read every channel it has been given access to, so grant it only what you need.
