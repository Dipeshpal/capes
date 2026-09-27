# Telegram setup (bot token)

Telegram bots use plain HTTPS, so nothing to install: your server calls the [Telegram Bot API](https://core.telegram.org/bots/api) directly with `TELEGRAM_BOT_TOKEN`. No OAuth, no app review.

**Time:** about 3 minutes. **Cost:** free.

## 1. Create a bot with @BotFather

1. Open a chat with [@BotFather](https://t.me/BotFather) in Telegram.
2. Send `/newbot`, pick a display name and a username ending in `bot` (for example `MyCapesBot`).
3. BotFather replies with a token like `123456789:AA...`. Copy it.

## 2. Give it to your server

- With the installer: paste it when asked for a Telegram bot token.
- Manually: `printf '%s' 'YOUR_TOKEN' | vercel env add TELEGRAM_BOT_TOKEN production`, then `vercel deploy --prod` ([Vercel guide](vercel.md#environment-variables)).

## 3. Add the bot to a chat

- **Direct messages:** message your bot first; a bot cannot start a conversation with a user who has never messaged it.
- **Groups:** add the bot to the group like any member. For it to read messages (not just be mentioned), turn off **Group Privacy** for the bot in @BotFather (`/mybots` > your bot > **Bot Settings** > **Group Privacy** > **Turn off**).
- **Channels:** add the bot as an administrator of the channel to post there.

## 4. Check that it works

Ask your AI assistant: "Get updates from Telegram" after messaging your bot once. You should see your message back with your username and text. To send: "Send 'hello' to Telegram chat `<id>`" (find a chat's ID from a message returned by `telegram_get_updates`, or your own numeric Telegram user ID from a bot like [@userinfobot](https://t.me/userinfobot)).

## Limits

- `telegram_get_updates` only works while the bot has no webhook configured (the default; this project never sets one). Each update is returned once, then marked read by Telegram.
- Message text is capped at 4096 characters by Telegram.
- Standard Telegram Bot API rate limits apply (roughly 30 messages per second across all chats, 20 per minute per group).

## Rotating or revoking

In @BotFather: `/mybots` > your bot > **API Token** > **Revoke current token**, then update `TELEGRAM_BOT_TOKEN` on Vercel and redeploy.

## Common problems

| Error | Fix |
|-------|-----|
| `TELEGRAM_BOT_TOKEN is not set on the server` | Add it on Vercel and redeploy. |
| `Telegram API 401` | The token is wrong or was revoked. |
| `Telegram API 403 (Forbidden: bot was blocked by the user)` | The user blocked the bot, or never started a conversation with it. |
| `Telegram API 400 (Bad Request: chat not found)` | Check the chat ID, or that the bot is actually a member of that chat/group. |
| `telegram_get_updates` returns nothing | The bot has no pending updates, or Group Privacy is still on for a group (see step 3). |
