# Vercel setup (hosting, required)

Vercel hosts your server and its dashboard. The free Hobby plan is enough. You also create your own server password here, `MCP_API_KEY`. It is the only thing protecting your server from the internet.

**Time:** about 10 minutes. **Cost:** free.

## 1. Create a Vercel account

Go to [vercel.com/signup](https://vercel.com/signup) and sign up (GitHub login is easiest). Choose the **Hobby** plan. Nothing to install for the recommended path below.

## 2. Create your `MCP_API_KEY` and `ENCRYPTION_KEY`

You need **two different** long random strings you make up. `MCP_API_KEY` is anything that connects to your server, and the dashboard login. `ENCRYPTION_KEY` encrypts connector credentials and extra API keys once you store them in the database (step 3) -- losing it makes those unrecoverable, so save both alongside each other. Each must be **at least 24 characters**; the server refuses shorter keys. Generate 32 random bytes (44 characters) twice:

| Where | Command |
|-------|---------|
| Windows PowerShell | `$b = New-Object byte[] 32; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); [Convert]::ToBase64String($b)` |
| macOS, Linux, Git Bash | `openssl rand -base64 32` |
| Node.js | `node -e "console.log(require('crypto').randomBytes(32).toString('base64url'))"` |
| No terminal | a password manager's generator: 32+ random characters |

Copy both results into a password manager. You will paste `MCP_API_KEY` into Vercel, into your AI client, and use it to sign in to the dashboard (unless you also set up `DASHBOARD_USER`/`DASHBOARD_PASSWORD` below, in which case those sign in to the dashboard instead). `ENCRYPTION_KEY` only goes into Vercel. Do not commit or share either.

**Optional: a separate dashboard login.** By default the dashboard login is `MCP_API_KEY` itself. To use a real username and password instead -- so the API key and the dashboard login are two different secrets -- also set `DASHBOARD_USER` (any name) and `DASHBOARD_PASSWORD` (8+ characters) in step 4. Skip this if you're fine signing in with `MCP_API_KEY`.

## 3. Get a database (`DATABASE_URL`)

Capes needs a Postgres database for connector credentials, extra API keys, and (later) Gmail OAuth. Any Postgres works; the fastest free option:

1. Go to [supabase.com](https://supabase.com), sign up, and create a new project (pick any region, set a project password).
2. Once it's ready: **Project Settings > Database > Connection string**, choose **Session pooler**, and copy the URI. Replace `[YOUR-PASSWORD]` in it with the password you set.
3. That full string is your `DATABASE_URL`.

**Use the Session pooler, not Direct connection.** Supabase shows both on the same screen. Direct connection (host like `db.<ref>.supabase.co`, port 5432) is IPv6-only, and Vercel functions cannot reach it -- the dashboard will show "configured but not reachable" if you use it. Session pooler (host like `aws-0-<region>.pooler.supabase.com`) works over IPv4 and is what you want.

Already running Postgres elsewhere (Neon, Railway, your own server)? Any standard `postgres://` connection string works the same way, as long as it's reachable over IPv4.

## 4. Deploy

### Option A: deploy on Vercel (recommended)

No install and no terminal. Everything happens in your browser.

1. Open the deploy link: [Deploy with Vercel](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2FDipeshpal%2Fcapes&env=MCP_API_KEY%2CDATABASE_URL%2CENCRYPTION_KEY&envDescription=MCP_API_KEY%20and%20ENCRYPTION_KEY%20are%20two%20different%20long%20random%20strings%20you%20make%20up%20%2824%2B%20characters%20each%29.%20DATABASE_URL%20is%20a%20Postgres%20connection%20string%2C%20for%20example%20from%20a%20free%20Supabase%20project.%20Add%20service%20credentials%20%28Discord%2C%20Gmail%2C%20etc%29%20on%20this%20same%20screen%20or%20afterward.&envLink=https%3A%2F%2Fgithub.com%2FDipeshpal%2Fcapes%2Fblob%2Fmain%2Fdocs%2Fsetup%2Fvercel.md&project-name=capes&repository-name=capes). Vercel copies the repository into your own GitHub account. It asks for `MCP_API_KEY`, `DATABASE_URL` and `ENCRYPTION_KEY`; a service credential you already have can be added on the same screen with **Add More**, or afterward.
2. Paste your three values from steps 2 and 3 above. If you already have credentials for a service ([Discord](discord.md), [Gmail](gmail.md), [Apify](apify.md), [Telegram](telegram.md)), click **Add More** on the same screen and add them now.

   Otherwise, deploy first and add service credentials afterward, one of two ways: one at a time in **Settings > Environment Variables**, or all at once with `node scripts/capes.mjs env --name <your-project-name>` from a clone of the repo — it prompts for each service once, sets every variable and redeploys, without touching `MCP_API_KEY` or any client you've already connected.
3. Click **Deploy** and wait for the build (about a minute).
4. Open `https://<project>.vercel.app/dashboard` and sign in with your `MCP_API_KEY`.

The link works for anyone once the repository is public. Until then, or if you work from your own fork, use **Vercel > Add New > Project > Import Git Repository** and pick the repo, then add the same environment variables on the setup screen.

### Option B: one command from your computer

Needs [Node.js 18+](https://nodejs.org) and a clone of the repository. It logs you in, generates a strong key for you, sets the variables, deploys and configures your AI clients:

```bash
git clone https://github.com/Dipeshpal/capes.git
cd capes
node scripts/capes.mjs install
```

### Option C: Vercel CLI by hand

```bash
npm i -g vercel
vercel login
vercel link --yes                       # inside the repo; creates the project
printf '%s' 'YOUR_MCP_API_KEY' | vercel env add MCP_API_KEY production
printf '%s' 'YOUR_ENCRYPTION_KEY' | vercel env add ENCRYPTION_KEY production
printf '%s' 'YOUR_DATABASE_URL' | vercel env add DATABASE_URL production
vercel deploy --prod
```

Add other variables the same way ([table below](#environment-variables)).

When the deploy finishes, your address is `https://<project>.vercel.app`. If that name was taken, Vercel adds a suffix; the project's **Domains** page in the dashboard shows the real one.

## 5. Check that it works

- Open `https://<project>.vercel.app/dashboard`, sign in, and look at **Overview**: your tool count and which connectors are configured.
- Or from a terminal: `curl https://<project>.vercel.app/health` should answer `"status":"online"`.
- Then connect an AI client ([guide](clients.md)) and ask "List my Discord channels".

## 6. Optional and advanced: dashboard switches (needs Redis)

Read-only mode and per-tool/per-connector switches always work from environment variables alone: set `PULSE_READ_ONLY`, `PULSE_DISABLED_CONNECTORS` or `PULSE_DISABLED_TOOLS` (table below) and redeploy. This is separate from the `DATABASE_URL` Postgres database (which stores credentials and API keys, not these switches).

Only if you want to flip these switches from the dashboard *without redeploying* (and keep a durable activity log), also add a free Redis database:

```bash
vercel integration add upstash
vercel deploy --prod
```

Or in the Vercel dashboard: **your project > Storage > Create > Upstash for Redis** (free plan). The integration sets `KV_REST_API_URL` and `KV_REST_API_TOKEN` for you. Details and what the switches do: [Dashboard guide](../usage/dashboard.md). Adding Redis means accepting Upstash's terms in Vercel; it is optional.

## Environment variables

Set these under **Project > Settings > Environment Variables** (Production), or with `vercel env add NAME production`.

`DATABASE_URL` and `ENCRYPTION_KEY` are required for new deployments (steps above). If you deployed Capes before this was added, your server keeps running fine without them -- everything falls back to environment variables exactly as before; add a database later only if you want dashboard-managed credentials, multiple API keys, or (eventually) Gmail OAuth.

| Variable | Required | Where it comes from |
|----------|----------|---------------------|
| `MCP_API_KEY` | Yes | You generate it (step 2). At least 24 characters. Protects `/mcp`; also the dashboard login unless `DASHBOARD_USER`/`DASHBOARD_PASSWORD` (below) are set. |
| `DATABASE_URL` | Yes | Any Postgres connection string (step 3: Supabase, Neon, etc). Stores connector credentials and extra MCP API keys, managed from the dashboard. |
| `ENCRYPTION_KEY` | Yes | You generate it (step 2), different from `MCP_API_KEY`. Encrypts anything stored in the database; losing it makes stored credentials unrecoverable. |
| `DASHBOARD_USER`, `DASHBOARD_PASSWORD` | No | Set both to sign in to `/dashboard` with a real username and password instead of `MCP_API_KEY`, so the API key and the dashboard login are separate secrets. `DASHBOARD_PASSWORD` must be at least 8 characters. |
| `DISCORD_BOT_TOKEN` | For Discord | [Discord guide](discord.md) (or set from the dashboard's Connectors tab once `DATABASE_URL` is set) |
| `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` | For Gmail | [Gmail guide](gmail.md) |
| `APIFY_TOKEN` | For X/Twitter search | [Apify guide](apify.md) (or set from the dashboard's Connectors tab) |
| `TELEGRAM_BOT_TOKEN` | For Telegram | [Telegram guide](telegram.md) (or set from the dashboard's Connectors tab) |
| `KV_REST_API_URL`, `KV_REST_API_TOKEN` | For dashboard switches | Set by `vercel integration add upstash` (`UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN` also work). Separate from `DATABASE_URL`, see step 6. |
| `PULSE_SESSION_HOURS` | No | How long a dashboard sign-in lasts, 1 to 168 hours (default 8). Then you sign in again with your key. |
| `PULSE_READ_ONLY` | No | `1` hides every tool that changes anything. Cannot be undone from the dashboard. |
| `PULSE_DISABLED_CONNECTORS` | No | Comma list, for example `discord,apify`. Always applies. |
| `PULSE_DISABLED_TOOLS` | No | Comma list, for example `gmail_trash,discord_delete_channel`. Always applies. |
| `APIFY_TWEET_ACTOR` | No | Different Apify actor for X search, see the [Apify guide](apify.md) |
| `PULSE_REPO_URL` | No | Where the dashboard "Guide" links point (set it if you forked the repo) |

Environment variable changes only apply to **new** deployments. After changing one, run `vercel deploy --prod` (or **Redeploy** in the Vercel dashboard).

## Deployment Protection

If your address shows a Vercel login page or answers `401`, Vercel Authentication is protecting it. MCP clients cannot log in there. Use the short project address (`https://<project>.vercel.app`), not the long per-deployment address. If the short address is also protected, open **Project > Settings > Deployment Protection** and turn **Vercel Authentication** off for production. Your `MCP_API_KEY` still protects the server and the dashboard.

## Rotating the key

1. Generate a new key (step 2).
2. Change `MCP_API_KEY` in **Settings > Environment Variables** (or `vercel env rm MCP_API_KEY production --yes`, then add the new one), then redeploy.
3. Update the key in every client (`node scripts/capes.mjs connect --key NEW_KEY`, or edit each config, see [Connect your client](clients.md)).

You never need to rotate the key on a schedule (it is not tied to the dashboard session length). Rotate it only if you think it leaked. Doing so also signs out every dashboard session, because sessions are signed with a key derived from `MCP_API_KEY`.

**Do not rotate `ENCRYPTION_KEY` the same casual way.** It decrypts whatever is already stored in `DATABASE_URL`; changing it makes existing stored credentials unreadable (you'd need to re-enter them from the dashboard afterward). Only change it if you believe it leaked, and expect to re-enter connector credentials and re-issue API keys after.

## Limits to know (Hobby plan)

- Each request may run for up to 60 seconds (configured in `vercel.json`). Long Apify searches are capped below that.
- Vercel usage limits apply. Personal use is far below them.
