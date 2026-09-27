# Troubleshooting

Find your symptom, apply the fix, retry. Service-specific problems also have a table at the end of each guide: [Vercel](../setup/vercel.md), [Discord](../setup/discord.md), [Gmail](../setup/gmail.md), [Apify](../setup/apify.md), [Telegram](../setup/telegram.md).

## Connecting

| Symptom | Cause and fix |
|---------|---------------|
| Server address shows a Vercel login page, or requests return `401` | Vercel Authentication is on. Use `https://<project>.vercel.app` (not the long per-deployment address) or turn it off for production. See [Vercel setup](../setup/vercel.md#deployment-protection). |
| `403 Invalid API key` | The key in your client differs from `MCP_API_KEY` on Vercel. Fix one, redeploy if you changed Vercel. |
| `500 MCP_API_KEY is not set on the server` | Add `MCP_API_KEY` on Vercel and redeploy. |
| `404` on `/mcp` | Use `URL/mcp`. If it is still 404, check that `vercel.json` has no `rewrites` entry. |
| Client shows the server as failed, Claude Desktop | Fully quit and reopen it. Check `node -v` works in a terminal. Read the log path in [Connect your client](../setup/clients.md#claude-desktop). |
| `ENOTFOUND` in the Claude Desktop log right after you deployed | A brand-new address was not resolvable yet. Restart Claude Desktop. |
| New tools do not appear | Redeploy, then restart the client. Clients read the tool list when they start. |

## Dashboard

| Symptom | Fix |
|---------|-----|
| "That key is not correct" | Use the current value of `MCP_API_KEY` from Vercel; check for stray spaces. |
| "Too many attempts" | Sign-in is blocked for 15 minutes after 10 wrong tries. |
| Server error mentioning "at least 24 characters" | Your `MCP_API_KEY` is too short. Set a longer one ([how](../setup/vercel.md#2-create-your-mcp_api_key-and-encryption_key)) and redeploy. |
| `500 ENCRYPTION_KEY is not set on the server` | `DATABASE_URL` is set but `ENCRYPTION_KEY` is not. Add it (a *different* long random string from `MCP_API_KEY`, [how](../setup/vercel.md#2-create-your-mcp_api_key-and-encryption_key)) and redeploy. |
| "Add DATABASE_URL to..." on API keys or connector credentials | Those features need a Postgres database. Add `DATABASE_URL` and `ENCRYPTION_KEY` ([Vercel setup](../setup/vercel.md#3-get-a-database-database_url)) and redeploy; everything else keeps working without it. |
| Settings/Connectors tab says the database is "configured but not reachable" | `DATABASE_URL` is set but the connection failed (wrong password, DB paused, network issue). Check the connection string on Vercel; `MCP_API_KEY` and everything env-var-based still works. |
| Switches are greyed out | Normal without Redis (a separate, optional integration from `DATABASE_URL`): set `PULSE_READ_ONLY`, `PULSE_DISABLED_CONNECTORS` or `PULSE_DISABLED_TOOLS` on Vercel and redeploy ([details](dashboard.md#switches-read-only-mode-and-where-settings-are-stored)). |
| Banner says settings storage is unreachable | The server is using the last known settings, or read-only mode if none. Check the Redis integration in Vercel **Storage**. |
| A client still sees a tool you switched off | Wait about 10 seconds and restart the client. |
| Signed out again | Sessions last 8 hours by default (`PULSE_SESSION_HOURS`). Sign in again; the key does not need rotating. |
| Test connection fails | The message comes from the service. See that service's guide. |

More in the [Dashboard guide](dashboard.md#troubleshooting).

## Tools

| Symptom | Fix |
|---------|-----|
| `... is not set on the server` | The service's variable is missing. Add it on Vercel and redeploy. Variables only apply to new deployments. |
| `Missing required argument(s): ...` | The client sent a call without a required argument. Rephrase the request or provide the value. |
| `'channel_id' has an invalid format` | Discord IDs are 5 to 25 digits. Copy the ID with Developer Mode on ([how](../setup/discord.md#7-check-that-it-works)). |
| `This tool is disabled by the server owner` or `...read-only mode...` | You (or environment variables) switched it off. Change it in the [dashboard](dashboard.md) or your `PULSE_*` variables. |
| `Discord ... Missing Permissions` | Re-authorize the bot and raise its role ([Discord guide](../setup/discord.md#5-put-the-bots-role-high-enough)). |
| `Gmail login failed` | Use the app password ([Gmail guide](../setup/gmail.md#2-create-the-app-password)). |
| `Apify API ...` | See the table in the [Apify guide](../setup/apify.md#common-problems). |
| `Telegram API ...` | See the table in the [Telegram guide](../setup/telegram.md#common-problems). |
| A request takes very long and times out | Vercel stops requests after 60 seconds. Ask for fewer results. |

## Installer

| Symptom | Fix |
|---------|-----|
| `vercel link failed` | Run `vercel login` first, and check you are in the repo folder. |
| `Server did not become healthy in time` | Run `vercel logs` for the error. Confirm `MCP_API_KEY` exists with `vercel env ls production`. |
| `Got 401: turn off Vercel Deployment Protection` | See [Vercel setup](../setup/vercel.md#deployment-protection). |
| It configured a client you did not want | Choose clients explicitly with `--clients desktop,cursor` (or `--clients none`). Remove the `capes` entry by hand ([clients](../setup/clients.md)). |

## Still stuck

Run the local checks from the repo root (`python tests/protocol.py`) to confirm the code itself works, then compare with what your deployment returns for `tools/list`. Open an issue with the exact error text and never include tokens, keys or app passwords.
