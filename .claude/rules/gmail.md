---
paths:
  - "pulse/gmail.py"
  - "docs/gmail.md"
  - "tests/gmail_offline.py"
---

# Gmail module rules

- Transport is IMAP (`imap.gmail.com:993`) and SMTP (`smtp.gmail.com:465`) with an app password. There is deliberately no Google Cloud/OAuth dependency.
- One `Mailbox` context manager per tool call. Do not cache connections across calls (serverless).
- Message ids are IMAP UIDs in the All Mail folder. Trash and Spam are not in All Mail, so they are not searchable. Find special folders through IMAP special-use flags (`\All`, `\Drafts`, `\Trash`, `\Junk`), never by English names, so localized accounts work.
- Search uses `X-GM-RAW` with the query sent as an IMAP literal (`m.literal`) and `CHARSET UTF-8`, so any Gmail search syntax and non-ASCII text works.
- Always pass mailbox names through `quote()`; `imaplib` does not.
- Read with `BODY.PEEK[...]` so reading does not mark mail as read.
- Drafts: `APPEND` to the Drafts folder with `\Draft`, then locate the new message by its own `Message-ID` header (`find_by_message_id`). Sending a draft = SMTP send, then expunge it from Drafts.
- Sending goes through `smtp_send`; `Bcc` recipients are delivered but never appear in headers (smtplib strips the header).
- Labels must be ASCII (modified UTF-7 is not implemented). Say so in errors rather than failing silently.
- Every new behaviour needs a case in `tests/gmail_offline.py`. Extend the fake IMAP class there instead of mocking individual functions, so parsing is exercised.
- Real inbox tests: use a throwaway Gmail account or send only to yourself. Never commit message content.
