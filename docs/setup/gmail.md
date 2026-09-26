# Gmail setup (app password)

Gmail works through IMAP and SMTP with a Google **app password**: a 16-letter password that lets one app use your mailbox without your real password. It is free and needs no Google Cloud project or OAuth screens.

**Time:** about 3 minutes. **Cost:** free.

You need two values: `GMAIL_ADDRESS` (your address) and `GMAIL_APP_PASSWORD`.

## 1. Turn on 2-Step Verification

App passwords exist only for accounts with 2-Step Verification.

1. Open [myaccount.google.com/security](https://myaccount.google.com/security).
2. Under **How you sign in to Google**, open **2-Step Verification** and finish the setup.

## 2. Create the app password

1. Open [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords). If the page says the option is not available, see [When app passwords are missing](#when-app-passwords-are-missing).
2. Name it `capes` and click **Create**.
3. Google shows 16 letters in groups of four. **Copy them now**; you cannot view them again. Spaces do not matter.

## 3. Give both values to your server

- With the installer: enter your address and the app password when asked.
- Manually:

  ```bash
  printf '%s' 'you@gmail.com'      | vercel env add GMAIL_ADDRESS production
  printf '%s' 'YOUR_APP_PASSWORD'  | vercel env add GMAIL_APP_PASSWORD production
  vercel deploy --prod
  ```

  See [Vercel setup](vercel.md#environment-variables).

## 4. Check that it works

Ask your AI assistant: "How many unread emails do I have?" (uses `gmail_list_labels`), then "Show my 5 newest emails." To test sending safely, ask it to send a test email **to yourself**.

## What it can do

Search with Gmail syntax (`from:alice is:unread newer_than:7d has:attachment label:work`), read messages, threads and attachments, send, reply and reply-all, forward, create, list, send and delete drafts, mark read/unread, star, archive, add and remove labels, create and delete labels, move to Trash or Spam. The full list is in the [README](../../README.md#tools).

## Limits

- One Gmail account per deployment.
- Message ids are stable ids from Gmail's **All Mail**. Search does not look inside Trash or Spam.
- Attachments: about 4 MB when sending and about 2 MB when downloading.
- Sending is immediate and cannot be undone. Ask for a draft first if you want to review.
- Label names must use plain ASCII characters.
- Editing a draft in place is not supported; delete it and create a new one.
- Google throttles very heavy IMAP use; normal assistant use is far below it.

## Security

An app password gives full access to the mailbox, including sending as you. Anyone who has your `MCP_API_KEY` can use this server to read and send your email, so keep the key private. Revoke access any time at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) (delete the `capes` entry); the server then loses access immediately.

## When app passwords are missing

Google does not offer app passwords if 2-Step Verification is off, if the account is enrolled in the Advanced Protection Program, or if an administrator disabled them for a work or school account. In those cases use a personal Gmail account, or ask the administrator to allow app passwords and IMAP.

## Common problems

| Error | Fix |
|-------|-----|
| `Gmail login failed` | Use the 16-letter app password, not your Google password. Check the address. Create a fresh app password if unsure. |
| `GMAIL_ADDRESS and GMAIL_APP_PASSWORD are not set` | Add both on Vercel and redeploy. |
| Login works locally but not on the server | The variables were added after the last deploy. Redeploy. |
| A message cannot be found by id | It may be in Trash or Spam, which search does not cover. |
| IMAP errors mentioning too many connections | Wait a minute and retry; Google limits simultaneous IMAP connections. |
| IMAP disabled | In Gmail: **Settings > See all settings > Forwarding and POP/IMAP**, set IMAP access to **Enable IMAP**. |
