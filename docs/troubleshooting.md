# Troubleshooting

Find your symptom, apply the fix, retry. Service-specific problems also have a table at the end of each guide: [Vercel](vercel.md), [Discord](discord.md), [Gmail](gmail.md), [Apify](apify.md).

## Connecting

| Symptom | Cause and fix |
|---------|---------------|
| Server address shows a Vercel login page, or requests return `401` | Vercel Authentication is on. Use `https://<project>.vercel.app` (not the long per-deployment address) or turn it off for production. See [Vercel setup](vercel.md#deployment-protection). |
| `403 Invalid API key` | The key in your client differs from `MCP_API_KEY` on Vercel. Fix one, redeploy if you changed Vercel. |
| `500 MCP_API_KEY is not set on the server` | Add `MCP_API_KEY` on Vercel and redeploy. |
| `404` on `/mcp` | Use `URL/mcp`. If it is still 404, check that `vercel.json` has no `rewrites` entry. |
| Client shows the server as failed, Claude Desktop | Fully quit and reopen it. Check `node -v` works in a terminal. Read the log path in [Connect your client](clients.md#claude-desktop). |
| `ENOTFOUND` in the Claude Desktop log right after you deployed | A brand-new address was not resolvable yet. Restart Claude Desktop. |
| New tools do not appear | Redeploy, then restart the client. Clients read the tool list when they start. |

## Tools

| Symptom | Fix |
|---------|-----|
| `... is not set on the server` | The service's variable is missing. Add it on Vercel and redeploy. Variables only apply to new deployments. |
| `Missing required argument(s): ...` | The client sent a call without a required argument. Rephrase the request or provide the value. |
| `Discord ... Missing Permissions` | Re-authorize the bot and raise its role ([Discord guide](discord.md#5-put-the-bots-role-high-enough)). |
| `Gmail login failed` | Use the app password ([Gmail guide](gmail.md#2-create-the-app-password)). |
| `Apify API ...` | See the table in the [Apify guide](apify.md#common-problems). |
| A request takes very long and times out | Vercel stops requests after 60 seconds. Ask for fewer results. |

## Installer

| Symptom | Fix |
|---------|-----|
| `vercel link failed` | Run `vercel login` first, and check you are in the repo folder. |
| `Server did not become healthy in time` | Run `vercel logs` for the error. Confirm `MCP_API_KEY` exists with `vercel env ls production`. |
| `Got 401: turn off Vercel Deployment Protection` | See [Vercel setup](vercel.md#deployment-protection). |
| It configured a client you did not want | Choose clients explicitly with `--clients desktop,cursor` (or `--clients none`). Remove the `pulse` entry by hand ([clients](clients.md)). |

## Still stuck

Run the local checks from the repo root (`python tests/protocol.py`) to confirm the code itself works, then compare with what your deployment returns for `tools/list`. Open an issue with the exact error text and never include tokens, keys or app passwords.
