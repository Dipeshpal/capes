# Vercel setup (hosting, required)

Vercel hosts your server. The free Hobby plan is enough. You also create your own server password here, `MCP_API_KEY`, which is the only thing protecting your server from the internet.

**Time:** about 5 minutes. **Cost:** free.

## 1. Create a Vercel account

1. Go to [vercel.com/signup](https://vercel.com/signup) and sign up (GitHub login is easiest). Choose the **Hobby** plan.
2. Install [Node.js 18 or newer](https://nodejs.org) if you do not have it. Check with `node -v`.

## 2. Create your `MCP_API_KEY`

This is a long random string you make up. Anything that connects to your server must send it.

```bash
node -e "console.log(require('crypto').randomBytes(32).toString('base64url'))"
```

Copy the output somewhere safe (a password manager). You will paste it into Vercel and into your AI client. Do not commit it or share it.

## 3. Deploy

Pick one:

- **One command (recommended):** from a clone of this repo run `node scripts/pulse.mjs install`. It logs you in, generates the key for you, sets the environment variables, deploys and connects your clients.
- **Vercel button:** see the button in the [README](../README.md#option-b-deploy-with-the-vercel-button). Vercel copies the repo to your GitHub and asks for the environment variables.
- **Manual CLI:**

  ```bash
  npm i -g vercel
  vercel login
  vercel link --yes                       # run inside the repo; creates the project
  printf '%s' 'YOUR_MCP_API_KEY' | vercel env add MCP_API_KEY production
  vercel deploy --prod
  ```

  Add the other variables the same way (see [Environment variables](#environment-variables)).

When the deploy finishes, your server address is `https://<project>.vercel.app`. If that name was taken, Vercel adds a suffix; `vercel inspect <deployment-url>` lists the real alias, and so does the project's **Domains** page in the dashboard.

## 4. Check that it works

```bash
curl https://<project>.vercel.app/
```

You should see `{"status":"online","name":"pulse-mcp", ...}`. Then check the protected endpoint (replace `KEY`):

```bash
curl -s -X POST https://<project>.vercel.app/mcp \
  -H "Authorization: Bearer KEY" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

A JSON list of tools means it works. `401` or `403` means the key is missing or wrong (see [Troubleshooting](troubleshooting.md)).

## Environment variables

Set these under **Project > Settings > Environment Variables** (Production), or with `vercel env add NAME production`.

| Variable | Required | Where it comes from |
|----------|----------|---------------------|
| `MCP_API_KEY` | Yes | You generate it (step 2) |
| `DISCORD_BOT_TOKEN` | For Discord | [Discord guide](discord.md) |
| `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` | For Gmail | [Gmail guide](gmail.md) |
| `APIFY_TOKEN` | For X/Twitter search | [Apify guide](apify.md) |
| `APIFY_TWEET_ACTOR` | No | Overrides the default Apify actor, see the [Apify guide](apify.md) |

Environment variable changes only apply to **new** deployments. After changing one, run `vercel deploy --prod` (or **Redeploy** in the dashboard).

## Deployment Protection

If your server address shows a Vercel login page or answers `401`, Vercel Authentication is protecting it. MCP clients cannot log in. Use the short project address (`https://<project>.vercel.app`), not the long per-deployment address. If the short address is also protected, open **Project > Settings > Deployment Protection** and turn **Vercel Authentication** off for production. Your `MCP_API_KEY` still protects the server.

## Rotating the key

1. Generate a new key (step 2).
2. `vercel env rm MCP_API_KEY production --yes`, then add the new value, then `vercel deploy --prod`.
3. Update the key in every client (`node scripts/pulse.mjs connect --key NEW_KEY`, or edit each config, see [Connect your client](clients.md)).

## Limits to know (Hobby plan)

- Each request may run for up to 60 seconds (configured in `vercel.json`). Long Apify searches are capped below that.
- Vercel usage limits apply. Personal use is far below them.
