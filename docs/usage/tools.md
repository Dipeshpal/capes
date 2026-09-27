# Tool reference

64 tools.

Generated from the code by `python scripts/gen_tools_doc.py`. Do not edit by hand; change the tool's description or schema in `pulse/` and regenerate.

**Kind** tells clients how careful to be: `read` has no side effects, `write` creates or changes things (sending mail or messages cannot be undone), `destructive` deletes or is hard to reverse, so clients should ask first. An asterisk marks a required argument.

## Gmail

Needs `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD`. Setup: [Gmail guide](../setup/gmail.md).

| Tool | Kind | What it does | Arguments |
|------|------|--------------|-----------|
| `gmail_list_labels` | read | List Gmail labels/folders and the unread count of the inbox. | none |
| `gmail_search` | read | Search email with Gmail search syntax (from:, to:, subject:, is:unread, has:attachment, label:, newer_than:2d, after:2026/01/01...). Covers All Mail (not Trash/Spam). Newest first. | `query`, `limit`, `before_id` |
| `gmail_get_message` | read | Read one email: headers, text body and attachment list. Does not mark it as read unless mark_read is true. | `id*`, `mark_read`, `max_chars` |
| `gmail_get_thread` | read | Read a whole conversation (oldest first). Bodies are truncated to 4000 characters each; up to 30 messages. | `thread_id*` |
| `gmail_get_attachment` | read | Download one attachment as base64 (max about 2 MB). | `id*`, `filename*` |
| `gmail_send_email` | write | Send an email immediately from the connected account. It cannot be unsent; use gmail_create_draft to let the user review first. | `to*`, `cc`, `bcc`, `subject*`, `body*`, `html`, `attachments` |
| `gmail_reply` | write | Reply to an email in its thread (sends immediately). reply_all also replies to everyone on To/Cc. The original text is quoted below your reply. | `id*`, `body*`, `html`, `reply_all`, `quote_original`, `attachments` |
| `gmail_forward` | write | Forward an email (the original is attached as .eml). Sends immediately. | `id*`, `to*`, `cc`, `note` |
| `gmail_create_draft` | write | Save a draft in Gmail (does not send). It shows up in Gmail's Drafts. | `to`, `cc`, `bcc`, `subject*`, `body*`, `html`, `attachments` |
| `gmail_list_drafts` | read | List drafts, newest first. | `limit` |
| `gmail_send_draft` | write | Send an existing draft, then remove it from Drafts. Sends immediately. | `id*` |
| `gmail_delete_draft` | destructive | Permanently delete a draft. | `id*` |
| `gmail_modify` | write | Change messages: mark read/unread, star/unstar, archive (remove from inbox), add or remove labels. New labels are created automatically. | `ids*`, `read`, `starred`, `archive`, `add_labels`, `remove_labels` |
| `gmail_trash` | destructive | Move messages to Trash (Gmail deletes them after 30 days; recover them in Gmail). | `ids*` |
| `gmail_mark_spam` | destructive | Move messages to Spam. | `ids*` |
| `gmail_create_label` | write | Create a label. Use '/' for nested labels (Work/Invoices). | `name*` |
| `gmail_delete_label` | destructive | Delete a label. Messages that had it are kept. | `name*` |

## Discord

Needs `DISCORD_BOT_TOKEN` and a bot invited with the right permissions. Setup: [Discord guide](../setup/discord.md).

| Tool | Kind | What it does | Arguments |
|------|------|--------------|-----------|
| `discord_list_guilds` | read | List the Discord servers the bot is in. | none |
| `discord_get_guild` | read | Get details about a Discord server. | `guild_id*` |
| `discord_list_channels` | read | List channels (all types, including categories, voice and forums). Omit guild_id to list every server the bot is in. | `guild_id` |
| `discord_get_channel` | read | Get a channel or thread, including its permission overwrites (translated to permission names). | `channel_id*` |
| `discord_read_channel` | read | Read recent messages from a channel or thread (newest first). | `channel_id*`, `limit`, `before` |
| `discord_list_pins` | read | List pinned messages in a channel. | `channel_id*` |
| `discord_list_members` | read | List server members, or search by name with `query`. Needs the 'Server Members Intent' enabled in the Discord Developer Portal (Bot tab). | `guild_id*`, `query`, `limit` |
| `discord_list_emojis` | read | List a server's custom emojis, including the name:id value used by discord_add_reaction. The bot must have access to the server. | `guild_id*` |
| `discord_list_scheduled_events` | read | List a server's scheduled events with times, channel or external location, status and interested user count. The bot must have access to the server. | `guild_id*` |
| `discord_list_roles` | read | List a server's roles with their permissions. | `guild_id*` |
| `discord_list_threads` | read | List active threads in a server, or archived public threads of one channel when channel_id is given. | `guild_id`, `channel_id` |
| `discord_send_message` | write | Send a message to a channel or thread. Provide content and/or an embed. | `channel_id*`, `content`, `embed`, `reply_to_message_id`, `mentions` |
| `discord_edit_message` | write | Edit a message. Discord only lets the bot edit its own messages. | `channel_id*`, `message_id*`, `content`, `embed`, `mentions` |
| `discord_delete_message` | destructive | Delete a message. Needs Manage Messages to delete other people's messages. | `channel_id*`, `message_id*`, `reason` |
| `discord_bulk_delete_messages` | destructive | Delete 2-100 messages at once (must be newer than 14 days). Needs Manage Messages. | `channel_id*`, `message_ids*`, `reason` |
| `discord_pin_message` | write | Pin (default) or unpin a message. Needs the Pin Messages permission (Discord split it from Manage Messages). | `channel_id*`, `message_id*`, `unpin` |
| `discord_add_reaction` | write | React to a message. emoji is a unicode emoji (👍) or a custom emoji as name:id. | `channel_id*`, `message_id*`, `emoji*` |
| `discord_remove_reaction` | destructive | Remove the bot's reaction, another user's reaction (user_id), or all reactions on the message (clear_all). Removing others' reactions needs Manage Messages. | `channel_id*`, `message_id*`, `emoji`, `user_id`, `clear_all` |
| `discord_create_channel` | write | Create a channel in a server. Needs Manage Channels. | `guild_id*`, `name*`, `type`, `topic`, `parent_id`, `nsfw`, `slowmode_seconds`, `private` |
| `discord_edit_channel` | write | Edit a channel or a thread (rename, topic, move, slowmode; for threads also archive/lock). Needs Manage Channels (Manage Threads for threads). | `channel_id*`, `name`, `topic`, `parent_id`, `nsfw`, `slowmode_seconds`, `position`, `archived`, `locked`, `auto_archive_minutes` |
| `discord_delete_channel` | destructive | Permanently delete a channel or thread. This cannot be undone. | `channel_id*`, `reason` |
| `discord_set_channel_permission` | write | Set (replace) the permission overwrite for a role or member on a channel. Permissions in neither allow nor deny inherit. Needs Manage Roles. | `channel_id*`, `target_id*`, `target_type*`, `allow`, `deny` |
| `discord_delete_channel_permission` | destructive | Remove a role's or member's permission overwrite from a channel. | `channel_id*`, `target_id*` |
| `discord_create_invite` | write | Create an invite link for a channel. | `channel_id*`, `max_age_seconds`, `max_uses`, `temporary` |
| `discord_create_thread` | write | Create a thread: from an existing message (message_id), as a standalone thread, or as a forum post (content). Edit/archive/delete threads with discord_edit_channel / discord_delete_channel. | `channel_id*`, `name*`, `message_id`, `content`, `tag_ids`, `private`, `auto_archive_minutes` |
| `discord_thread_member` | write | Manage thread membership: join/leave (the bot), add/remove a user, or list members. | `thread_id*`, `action*`, `user_id` |
| `discord_create_role` | write | Create a role. Needs Manage Roles; the bot can only grant permissions it has itself. | `guild_id*`, `name*`, `permissions`, `color`, `hoist`, `mentionable` |
| `discord_edit_role` | write | Edit a role. Passing permissions replaces the role's whole permission set. | `guild_id*`, `role_id*`, `name`, `permissions`, `color`, `hoist`, `mentionable` |
| `discord_delete_role` | destructive | Delete a role permanently. | `guild_id*`, `role_id*`, `reason` |
| `discord_member_role` | write | Give a role to a member, or take it away. The role must be below the bot's highest role. | `guild_id*`, `user_id*`, `role_id*`, `action*` |
| `discord_moderate_member` | destructive | Moderate a member: kick, ban, unban, timeout (mute for N minutes) or untimeout. Needs Kick/Ban/Moderate Members. Destructive: confirm with the user first. | `guild_id*`, `user_id*`, `action*`, `timeout_minutes`, `delete_message_seconds`, `reason` |
| `discord_get_message` | read | Read one message by ID. | `channel_id*`, `message_id*` |
| `discord_list_reactions` | read | List the users who reacted to a message with one emoji (unicode or name:id). | `channel_id*`, `message_id*`, `emoji*`, `limit` |
| `discord_send_dm` | write | Send a direct message to a user. They must share a server with the bot and allow DMs from server members. Never pings anyone. | `user_id*`, `content`, `embed` |
| `discord_read_dm` | read | Read recent direct messages between the bot and a user (newest first). | `user_id*`, `limit` |
| `discord_send_file` | write | Upload a file (base64, up to 3 MB) to a channel or thread, with an optional message. | `channel_id*`, `filename*`, `content_base64*`, `mime_type`, `content` |
| `discord_create_poll` | write | Post a native Discord poll (2 to 10 answers) in a channel. | `channel_id*`, `question*`, `answers*`, `duration_hours`, `allow_multiselect` |
| `discord_list_forum_tags` | read | List the tags of a forum channel. | `channel_id*` |
| `discord_manage_forum_tag` | destructive | Add, rename or remove a tag on a forum channel. Needs Manage Channels. Removing a tag removes it from posts that use it. | `channel_id*`, `action*`, `name`, `tag_id`, `emoji`, `moderated` |
| `discord_list_webhooks` | read | List webhooks of a channel or of a whole server. Tokens are never shown. Needs Manage Webhooks. | `channel_id`, `guild_id` |
| `discord_create_webhook` | write | Create a webhook in a channel. Returns its ID only; use discord_send_webhook_message to post through it. Needs Manage Webhooks. | `channel_id*`, `name*` |
| `discord_send_webhook_message` | write | Post a message through a webhook, optionally under a custom display name. The server looks up the webhook token itself. | `webhook_id*`, `content`, `username`, `embed` |
| `discord_delete_webhook` | destructive | Delete a webhook permanently. Needs Manage Webhooks. | `webhook_id*`, `reason` |
| `discord_list_invites` | read | List a server's active invites. Needs Manage Server. | `guild_id*` |
| `discord_delete_invite` | destructive | Revoke an invite link. Needs Manage Server (or Manage Channels for that channel). | `code*`, `reason` |
| `discord_get_audit_log` | read | Read a server's audit log (who changed what, newest first). Needs View Audit Log. | `guild_id*`, `limit`, `user_id`, `action_type` |

## X/Twitter

Needs `APIFY_TOKEN`. Setup: [Apify guide](../setup/apify.md).

| Tool | Kind | What it does | Arguments |
|------|------|--------------|-----------|
| `twitter_search` | read | Search tweets on X/Twitter via Apify (needs APIFY_TOKEN). | `query*`, `limit` |
