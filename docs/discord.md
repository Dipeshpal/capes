# Discord setup (bot token and permissions)

You need a Discord **bot**. Its token goes into `DISCORD_BOT_TOKEN`. What the bot may do in a server is decided by the permissions it is invited with, not by the token, so the invite step matters as much as the token.

**Time:** about 10 minutes. **Cost:** free.

## 1. Create the application and bot

1. Open the [Discord Developer Portal](https://discord.com/developers/applications) and sign in.
2. Click **New Application**, name it (for example "pulse"), accept the terms, **Create**.
3. Open the **Bot** tab on the left.
4. Click **Reset Token**, confirm, and **copy the token**. Discord shows it only once. This is your `DISCORD_BOT_TOKEN`. Treat it like a password.

## 2. Turn on the intents you need

Still on the **Bot** tab, under **Privileged Gateway Intents**:

| Intent | Turn on if you want to | Symptom if it is off |
|--------|------------------------|----------------------|
| **Message Content Intent** | Read message text | Messages come back with empty `content` |
| **Server Members Intent** | List or search members (`discord_list_members`) | That tool fails |
| Presence Intent | Not needed | |

Click **Save Changes**.

## 3. Make the bot private

On the **Bot** tab, switch **Public Bot** off. Otherwise anyone who knows your application ID can add your bot to their servers. Leave **Requires OAuth2 Code Grant** off.

## 4. Invite the bot with the right permissions

Open this link while signed in as the owner (or an admin) of the server. Replace `CLIENT_ID` with your **Application ID** (Developer Portal > **General Information** > Application ID). The installer prints the finished link for you, and so does the dashboard: **Connectors > Discord > Get invite link** (no Application ID needed).

```
https://discord.com/oauth2/authorize?client_id=CLIENT_ID&scope=bot&permissions=1495454313687
```

Choose the server, click **Authorize**. Opening the same link again for a server the bot is already in **updates** its permissions.

The number `1495454313687` grants exactly these permissions:

| Area | Permissions |
|------|-------------|
| Read and write messages | View Channels, Send Messages, Send Messages in Threads, Embed Links, Attach Files, Read Message History, Add Reactions, Use External Emojis |
| Threads | Create Public Threads, Create Private Threads, Manage Threads |
| Manage the server | Manage Channels, Manage Roles, Manage Messages, Manage Webhooks, View Audit Log, Create Invite |
| Moderation | Kick Members, Ban Members, Timeout Members |

It does not include Administrator, and it does not include **Manage Server**. Only `discord_list_invites` and `discord_delete_invite` need Manage Server; add that permission to the bot's role in Server Settings > Roles if you want them. If you do not need moderation or role tools, you can choose a smaller set in the Developer Portal under **OAuth2 > URL Generator** (scope `bot`, tick the permissions, copy the generated link).

## 5. Put the bot's role high enough

The bot can only manage roles and members that sit **below** its own role. In Discord: **Server Settings > Roles**, drag the bot's role (named after your application) above the roles you want it to manage.

## 6. Give the token to your server

- With the installer: paste the token when asked.
- Manually: `printf '%s' 'YOUR_TOKEN' | vercel env add DISCORD_BOT_TOKEN production`, then `vercel deploy --prod` ([Vercel guide](vercel.md#environment-variables)).

## 7. Check that it works

Ask your AI assistant: "List my Discord channels." You should see your server and its channels. Then: "Read the last 3 messages in #general."

To find IDs yourself: Discord **User Settings > Advanced > Developer Mode** on, then right-click a server, channel, user or role and choose **Copy ... ID**.

## Direct messages, files, polls, forums, webhooks, audit log

Beyond channels and roles, the toolkit covers:

| Feature | Tools | Notes |
|---------|-------|-------|
| Direct messages | `discord_send_dm`, `discord_read_dm` | The user must share a server with the bot and allow DMs from server members (Discord error 50007 otherwise). DMs never ping anyone. |
| File upload | `discord_send_file` | Base64 content, up to 3 MB, with an optional message. Files are never fetched from URLs. |
| Polls | `discord_create_poll` | 2 to 10 answers (55 characters each), 1 to 768 hours, optional multi-select. |
| Forums | `discord_list_forum_tags`, `discord_manage_forum_tag`, `discord_create_thread` with `tag_ids` | Add, rename and remove tags; post to a forum with tags applied. Managing tags needs Manage Channels. |
| Webhooks | `discord_list_webhooks`, `discord_create_webhook`, `discord_send_webhook_message`, `discord_delete_webhook` | Needs Manage Webhooks (included in the invite link). The webhook token stays on the server and is never returned. |
| Audit log | `discord_get_audit_log` | Needs View Audit Log (included in the invite link). |
| Invites | `discord_list_invites`, `discord_delete_invite` | Need Manage Server, which the invite link does not grant; add it to the bot's role if you want these. |
| Reading one message, who reacted | `discord_get_message`, `discord_list_reactions` | |

## What the bot cannot do

These are Discord's rules, not limits of this project:

- **Create servers.** Discord removed that for bots. Create the server yourself and invite the bot; it can then create channels, roles and threads.
- **Edit other people's messages.** Bots can edit only their own. With Manage Messages they can delete others' messages.
- **Bulk delete** messages older than 14 days.
- **Grant a permission it does not have**, or manage a role at or above its own.
- Read channels it cannot see. Use a channel permission overwrite or a role that can view it.

## Safety defaults in this project

- Messages ping users only. `@everyone`, `@here` and role pings are blocked unless the request sets `mentions` to `all`.
- Destructive tools (delete, bulk delete, remove reactions, moderation) are marked so clients ask before running them.
- Changes are tagged "via pulse-mcp" in the server's **Audit Log**.

## Rotating or revoking

- **Rotate the token:** Developer Portal > Bot > **Reset Token**, then update `DISCORD_BOT_TOKEN` on Vercel and redeploy.
- **Remove the bot from a server:** Server Settings > Integrations, or kick it.
- **Trim permissions:** edit the bot's role in Server Settings > Roles.

## Common problems

| Error | Meaning and fix |
|-------|-----------------|
| `Missing Permissions` (50013) | The bot lacks that permission or its role is too low. Re-authorize with the link above and move its role up. |
| `Missing Access` (50001) | The bot is not in that server or cannot see that channel. |
| Empty message text | Turn on Message Content Intent (step 2). |
| `discord_list_members` fails | Turn on Server Members Intent (step 2). |
| `401 Unauthorized` from Discord | The token is wrong or was reset. Copy the new one. |
