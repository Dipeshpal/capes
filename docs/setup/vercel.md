# Vercel setup (hosting, required)

Vercel hosts your server and its dashboard. The free Hobby plan is enough. You also create your own server password here, `MCP_API_KEY`. It is the only thing protecting your server from the internet.

**Time:** about 5 minutes. **Cost:** free.

## 1. Create a Vercel account

Go to [vercel.com/signup](https://vercel.com/signup) and sign up (GitHub login is easiest). Choose the **Hobby** plan. Nothing to install for the recommended path below.

## 2. Create your `MCP_API_KEY`

This is a long random string you make up. Anything that connects to your server, and the dashboard login, uses it. It must be **at least 24 characters**; the server refuses shorter keys. Generate 32 random bytes (44 characters):

| Where | Command |
|-------|---------|
| Windows PowerShell | `$b = New-Object byte[] 32; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); [Convert]::ToBase64String($b)` |
| macOS, Linux, Git Bash | `openssl rand -base64 32` |
| Node.js | `node -e "console.log(require('crypto').randomBytes(32).toString('base64url'))"` |
| No terminal | a password manager's generator: 32+ random characters |

Copy the result into a password manager. You will paste it into Vercel and into your AI client, and use it to sign in to the dashboard. Do not commit it or share it.

## 3. Deploy

### Option A: deploy on Vercel (recommended)

No install and no terminal. Everything happens in your browser.

1. Open the deploy link: [Deploy with Vercel](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2FDipeshpal%2Fcapes&env=MCP_API_KEY&envDescription=MCP_API_KEY%20is%20any%20long%20random%20string%20you%20make%20up%20(24%2B%20characters).%20It%20is%20the%20only%20required%20variable%3B%20add%20service%20credentials%20on%20this%20same%20screen%20or%20afterward.&envLink=https%3A%2F%2Fgithub.com%2FDipeshpal%2Fcapes%2Fblob%2Fmain%2Fdocs%2Fsetup%2Fvercel.md&project-name=capes&repository-name=capes). Vercel copies the repository into your own GitHub account. It asks for `MCP_API_KEY` only; a service credential you already have can be added on the same screen with **Add More**, or afterward.
2. Paste `MCP_API_KEY`. It's the only variable this screen requires. If you already have credentials for a service ([Discord](discord.md), [Gmail](gmail.md), [Apify](apify.md), [Telegram](telegram.md)), click **Add More** on the same screen and add them now.

   Otherwise, deploy first and add credentials afterward, one of two ways: one at a time in **Settings > Environment Variables**, or all at once with `node scripts/capes.mjs env --name <your-project-name>` from a clone of the repo — it prompts for each service once, sets every variable and redeploys, without touching `MCP_API_KEY` or any client you've already connected. (The button only marks `MCP_API_KEY` as required on purpose — Vercel forces every variable it lists to be filled in, and the others are optional.)
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
vercel deploy --prod
```

Add other variables the same way ([table below](#environment-variables)).

When the deploy finishes, your address is `https://<project>.vercel.app`. If that name was taken, Vercel adds a suffix; the project's **Domains** page in the dashboard shows the real one.

## 4. Check that it works

- Open `https://<project>.vercel.app/dashboard`, sign in, and look at **Overview**: your tool count and which connectors are configured.
- Or from a terminal: `curl https://<project>.vercel.app/health` should answer `"status":"online"`.
- Then connect an AI client ([guide](clients.md)) and ask "List my Discord channels".

## 5. Optional and advanced: dashboard switches (needs Redis)

**You do not need a database.** Capes stores nothing on the server: your credentials and limits are environment variables, and the dashboard shows the result. To restrict what assistants can do without any database, set `PULSE_READ_ONLY`, `PULSE_DISABLED_CONNECTORS` or `PULSE_DISABLED_TOOLS` (table below) and redeploy.

Only if you want to flip switches on the dashboard *without redeploying* (and keep a durable activity log), add a free Redis database:

```bash
vercel integration add upstash
vercel deploy --prod
```

Or in the Vercel dashboard: **your project > Storage > Create > Upstash for Redis** (free plan). The integration sets `KV_REST_API_URL` and `KV_REST_API_TOKEN` for you. Details and what the switches do: [Dashboard guide](../usage/dashboard.md). Adding Redis means accepting Upstash's terms in Vercel; it is optional.

## Environment variables

Set these under **Project > Settings > Environment Variables** (Production), or with `vercel env add NAME production`.

| Variable | Required | Where it comes from |
|----------|----------|---------------------|
| `MCP_API_KEY` | Yes | You generate it (step 2). At least 24 characters. |
| `DISCORD_BOT_TOKEN` | For Discord | [Discord guide](discord.md) |
| `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` | For Gmail | [Gmail guide](gmail.md) |
| `APIFY_TOKEN` | For X/Twitter search | [Apify guide](apify.md) |
| `TELEGRAM_BOT_TOKEN` | For Telegram | [Telegram guide](telegram.md) |
| `KV_REST_API_URL`, `KV_REST_API_TOKEN` | For dashboard switches | Set by `vercel integration add upstash` (`UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN` also work) |
| `DATABASE_URL` | No | Any Postgres connection string (Supabase, Neon, etc). Lets connector tokens and extra MCP API keys live in the database instead of env vars, managed from the dashboard. See issue #36. |
| `ENCRYPTION_KEY` | Only if `DATABASE_URL` is set | Generate it the same way as `MCP_API_KEY` (step 2). Encrypts anything stored in the database; losing it makes stored credentials unrecoverable. |
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

## Limits to know (Hobby plan)

- Each request may run for up to 60 seconds (configured in `vercel.json`). Long Apify searches are capped below that.
- Vercel usage limits apply. Personal use is far below them.
