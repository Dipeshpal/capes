# Apify setup (X/Twitter search token)

The `twitter_search` tool searches public tweets through [Apify](https://apify.com), a scraping platform. Apify runs the scraper for you; your server only needs your Apify API token in `APIFY_TOKEN`.

**Time:** about 3 minutes. **Cost:** the free plan includes a monthly usage credit that is enough for occasional searches. Heavy use is billed per result by Apify, so check the current price on the actor page linked below.

## 1. Create an Apify account

Sign up at [console.apify.com/sign-up](https://console.apify.com/sign-up). The free plan needs no card.

## 2. Copy your API token

1. Open [Settings > API & Integrations](https://console.apify.com/settings/integrations).
2. Under **Personal API tokens**, copy the **Default** token (or create one named `capes`). It starts with `apify_api_`.

## 3. Give it to your server

- With the installer: paste it when asked.
- Manually: `printf '%s' 'YOUR_TOKEN' | vercel env add APIFY_TOKEN production`, then `vercel deploy --prod` ([Vercel guide](vercel.md#environment-variables)).

## 4. Check that it works

Ask your AI assistant: "Search X for MCP servers, 5 results." You should get tweets with author, text, date and counts. A search takes roughly 10 to 40 seconds.

## Which scraper is used

By default the server runs the Apify actor [`apidojo/tweet-scraper`](https://apify.com/apidojo/tweet-scraper), which worked on the free plan when this project was tested. To use another actor that accepts `searchTerms`, `maxItems` and `sort`, set the environment variable `APIFY_TWEET_ACTOR` (for example `apidojo~tweet-scraper`; use `~` instead of `/`) and redeploy. Different actors may return different fields, so check the result.

## Limits

- Results are capped at 500 per call.
- The call must finish within 45 seconds (Vercel allows 60). Very large searches may return an Apify timeout error; ask for fewer results.
- X/Twitter content is public data only. Follow Apify's and X's terms of use.

## Rotating or revoking

Delete or regenerate the token under **Settings > API & Integrations**, then update `APIFY_TOKEN` on Vercel and redeploy.

## Common problems

| Error | Fix |
|-------|-----|
| `APIFY_TOKEN is not set on the server` | Add it on Vercel and redeploy. |
| `Apify API 401` | The token is wrong or was regenerated. |
| `Apify API 402`, or a message about credit or limits | Your Apify usage credit may be used up. Check your usage in the Apify console, wait for the reset, or upgrade. |
| `Actor was not found` (404) | The actor name in `APIFY_TWEET_ACTOR` is wrong. Use `owner~name`. |
| Timeout | Ask for fewer results (`limit`). |
