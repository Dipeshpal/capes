# Connect your AI client

Every client needs two things: your server address `https://<project>.vercel.app/mcp` (note the `/mcp`) and your `MCP_API_KEY`, sent as the header `Authorization: Bearer <MCP_API_KEY>`. Below, `URL` means `https://<project>.vercel.app` and `KEY` means your `MCP_API_KEY`.

## Easiest: copy from the dashboard

Sign in to `https://<project>.vercel.app/dashboard` and open **Connect a client**. It shows ready-to-copy config for Claude Code, Claude Desktop, Cursor and Codex, already filled in with your address. Replace `YOUR_MCP_API_KEY` with your key (the dashboard never displays it).

## Or: the connect script

From a clone of this repo (Node 18+):

```bash
node scripts/capes.mjs connect
```

It reads `.capes.local.json` if you used the installer, or asks for the URL and key, then configures the clients you choose. Non-interactive: `node scripts/capes.mjs connect --url URL --key KEY --clients desktop,claude-code,cursor,codex`.

## Claude Desktop

Claude Desktop starts local commands only, so it reaches your server through the [`mcp-remote`](https://www.npmjs.com/package/mcp-remote) bridge (needs Node.js on your PATH).

1. Open the config file:
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Linux: `~/.config/Claude/claude_desktop_config.json`

   Or in Claude Desktop: **Settings > Developer > Edit Config**.
2. Add the server, keeping any other entries you already have:

   ```json
   {
     "mcpServers": {
       "capes": {
         "command": "npx",
         "args": ["-y", "mcp-remote", "URL/mcp", "--header", "Authorization:${AUTH_HEADER}"],
         "env": { "AUTH_HEADER": "Bearer KEY" }
       }
     }
   }
   ```

   The key goes in `env` and is referenced as `${AUTH_HEADER}` because a space inside an argument breaks on Windows.
3. **Fully quit** Claude Desktop (system tray icon too) and open it again.
4. Check: **Settings > Developer** shows `capes` as running. Ask "List my Discord channels."

If it fails, open the log: Windows `%LOCALAPPDATA%\Claude\Logs\mcp-server-pulse.log` (Microsoft Store install) or `%APPDATA%\Claude\logs\`; macOS `~/Library/Logs/Claude/mcp-server-pulse.log`.

## Claude Code

```bash
claude mcp add --scope user --transport http capes URL/mcp --header "Authorization: Bearer KEY"
claude mcp list
```

`--scope user` makes it available in every project. Remove it with `claude mcp remove capes --scope user`.

## Cursor

Edit `~/.cursor/mcp.json` (or **Settings > MCP**), then reload Cursor:

```json
{
  "mcpServers": {
    "capes": { "url": "URL/mcp", "headers": { "Authorization": "Bearer KEY" } }
  }
}
```

## Codex

```bash
codex mcp add capes --url URL/mcp --bearer-token-env-var CAPES_MCP_API_KEY
```

Then define the variable so Codex can read the key:

- Windows: `setx CAPES_MCP_API_KEY KEY`, then open a new terminal.
- macOS/Linux: add `export CAPES_MCP_API_KEY=KEY` to your shell profile.

## Any other MCP client

Use the streamable HTTP transport with URL `URL/mcp` and the Bearer header. If the client only supports local commands, use `npx -y mcp-remote URL/mcp --header "Authorization:${AUTH_HEADER}"` with `AUTH_HEADER` set to `Bearer KEY`.

## Try it

- "List my Discord channels."
- "Search my Gmail for unread messages from the last 2 days."
- "Search X for MCP servers."

After you add services or redeploy with new tools, restart the client so it refreshes its tool list.
