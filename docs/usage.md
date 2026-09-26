# Using pulse-mcp

Once your server is deployed and your AI client is connected ([setup steps](../README.md#set-up-in-6-steps)), you just talk to your assistant. It picks the right tools. This page shows what to ask, how to stay safe, and how to test without an AI client.

The exact tools and arguments are in the [tool reference](tools.md).

## Things to ask

**Gmail**

- "How many unread emails do I have, and what are the five most recent?"
- "Find emails from my landlord in the last 3 months and summarize them."
- "Search for messages with attachments from this week, then download the invoice PDF."
- "Draft a reply to the last email from Sam saying I can meet on Friday. Show me the draft before sending."
- "Archive all newsletters older than a week and label them `reading`."
- "Forward the latest receipt from Amazon to my accountant."

**Discord**

- "List my Discord servers and channels."
- "Read the last 50 messages in #support and list the open questions."
- "Post this announcement in #announcements and pin it."
- "Create a private channel `mods-only` that only the Moderator role can see."
- "Create a role `Contributor` with permission to manage messages, and give it to user 123."
- "Time out that user for 10 minutes." (a destructive action; your client should ask first)

**X/Twitter**

- "Search X for people talking about MCP servers and summarize the themes."
- "Find recent tweets mentioning my product name and tell me the sentiment."

**Combined**

- "Read #support, and for every unanswered question, draft an email to me summarizing them."
- "Every morning: unread email highlights plus new Discord questions." (pair with your client's scheduling features)

## Staying safe

- **Draft first.** Sending email and Discord messages cannot be undone. Ask the assistant to create a draft (`gmail_create_draft`) or to show you the text before it sends.
- **Read the confirmation prompts.** Tools that delete, ban or bulk-change are flagged, and good clients ask before running them. Do not switch that off for tools you have not used before.
- **Be specific about targets.** Name the channel, sender or date range. Mail and channel IDs come from search and list calls; let the assistant look them up.
- **Start read-only.** If you are unsure, give your Discord bot fewer permissions or use a test server first ([Discord guide](discord.md)).
- **Check the record.** Discord changes made by the bot appear in the server **Audit Log** tagged "via pulse-mcp". Sent mail appears in Gmail's Sent folder.
- **Keep the key private.** Anyone with your `MCP_API_KEY` can act on your accounts.

## Good to know

- **IDs:** Gmail ids come from `gmail_search`. Discord IDs are copyable in Discord with Developer Mode on ([how](discord.md#7-check-that-it-works)). Threads use their own channel ID.
- **Limits:** search results are capped (100 for Gmail, 500 for Discord messages and tweets). Ask for a narrower range instead of "everything".
- **Speed:** most calls take a few seconds (Gmail logs in on every call). X search takes 10 to 40 seconds.
- **Restart after changes:** clients read the tool list at start-up. Restart your client after you redeploy or add a service.

## Calling the server without an AI client

Useful for debugging. Replace `URL` and `KEY`.

```bash
# list tools
curl -s -X POST URL/mcp -H "Authorization: Bearer KEY" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

# call one
curl -s -X POST URL/mcp -H "Authorization: Bearer KEY" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"gmail_search","arguments":{"query":"is:unread","limit":3}}}'
```

A tool failure comes back as a normal result with `"isError": true` and a message that says how to fix it. Common causes are in [Troubleshooting](troubleshooting.md).
