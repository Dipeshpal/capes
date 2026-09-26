"""X/Twitter search via Apify."""

import os

import aiohttp

from .registry import ToolError, tool

ACTOR = os.getenv("APIFY_TWEET_ACTOR", "apidojo~tweet-scraper")


@tool(
    "twitter_search",
    "Search tweets on X/Twitter via Apify (needs APIFY_TOKEN).",
    {
        "query": {"type": "string", "description": "Search query", "maxLength": 500},
        "limit": {"type": "integer", "description": "Max tweets, 1-500 (default 50)"},
    },
    ["query"],
)
async def twitter_search(args: dict):
    token = os.getenv("APIFY_TOKEN")
    if not token:
        raise ToolError("APIFY_TOKEN is not set on the server")
    limit = max(1, min(int(args.get("limit", 50)), 500))
    payload = {"searchTerms": [args["query"]], "maxItems": limit, "sort": "Latest"}
    async with (
        aiohttp.ClientSession() as session,
        session.post(
            f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items",
            params={"timeout": 45},
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=aiohttp.ClientTimeout(total=55),
        ) as resp,
    ):
        body = await resp.json(content_type=None)
        if resp.status not in (200, 201):
            raise ToolError(f"Apify API {resp.status}: {body}")
    tweets = [
        {
            "url": t.get("url"),
            "author": (t.get("author") or {}).get("userName"),
            "text": t.get("fullText") or t.get("text"),
            "created_at": t.get("createdAt"),
            "likes": t.get("likeCount"),
            "retweets": t.get("retweetCount"),
            "replies": t.get("replyCount"),
            "views": t.get("viewCount"),
        }
        for t in body
        if t.get("type") == "tweet"
    ][:limit]
    return {"query": args["query"], "count": len(tweets), "tweets": tweets}
