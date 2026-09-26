"""Gmail tools over IMAP/SMTP using a Google app password (free, no Google Cloud project).

Message ids returned by these tools are IMAP UIDs in Gmail's "All Mail" folder. Trash and Spam are not part of
All Mail, so search does not cover them.
"""

import asyncio
import base64
import email
import imaplib
import os
import re
import smtplib
import ssl
import time
from email import policy
from email.message import EmailMessage
from email.utils import formatdate, getaddresses, make_msgid
from html.parser import HTMLParser
from typing import Optional

from .registry import ToolError, tool

IMAP_HOST = "imap.gmail.com"
SMTP_HOST = "smtp.gmail.com"
MAX_ATTACHMENT_BYTES = 2_000_000


# --------------------------------------------------------------------------
# Connection
# --------------------------------------------------------------------------

def credentials() -> tuple[str, str]:
    address, password = os.getenv("GMAIL_ADDRESS"), os.getenv("GMAIL_APP_PASSWORD")
    if not address or not password:
        raise ToolError("GMAIL_ADDRESS and GMAIL_APP_PASSWORD are not set on the server (see docs/gmail.md)")
    return address.strip().strip("\"'"), password.strip().strip("\"'").replace(" ", "")


def quote(name: str) -> str:
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def parse_list_line(line: str) -> Optional[tuple[list[str], str]]:
    m = re.match(r'\((?P<attrs>[^)]*)\)\s+(?:"(?P<sep>[^"]*)"|NIL)\s+(?P<name>.+)$', line)
    if not m:
        return None
    name = m["name"].strip()
    if name.startswith('"') and name.endswith('"'):
        name = name[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return m["attrs"].split(), name


class Mailbox:
    """IMAP session. Use as a context manager."""

    def __enter__(self):
        address, password = credentials()
        self.address = address
        self.m = imaplib.IMAP4_SSL(IMAP_HOST, timeout=25)
        try:
            self.m.login(address, password)
        except imaplib.IMAP4.error as e:
            if "AUTHENTICATIONFAILED" in str(e) or "Invalid credentials" in str(e):
                raise ToolError(
                    "Gmail login failed. Use a 16-character app password (Google Account > Security > 2-Step Verification > App passwords), not your normal password."
                ) from e
            raise
        self._folders: Optional[dict] = None
        return self

    def __exit__(self, *exc):
        try:
            self.m.logout()
        except Exception:  # noqa: BLE001
            pass

    @property
    def folders(self) -> dict:
        """Special-use folders by role (all, drafts, sent, trash, junk), found via IMAP special-use flags so it works in any language."""
        if self._folders is None:
            typ, data = self.m.list()
            found = {}
            roles = {"\\All": "all", "\\Drafts": "drafts", "\\Sent": "sent", "\\Trash": "trash", "\\Junk": "junk", "\\Flagged": "starred"}
            for raw in data or []:
                parsed = parse_list_line(raw.decode("utf-8", "replace")) if isinstance(raw, bytes) else None
                if parsed:
                    attrs, name = parsed
                    for a in attrs:
                        if a in roles:
                            found[roles[a]] = name
            self._folders = found
        return self._folders

    def select(self, role: str = "all", readonly: bool = True):
        name = "INBOX" if role == "inbox" else self.folders.get(role)
        if not name:
            raise ToolError(f"Could not find the Gmail '{role}' folder")
        typ, data = self.m.select(quote(name), readonly=readonly)
        if typ != "OK":
            raise ToolError(f"Cannot open folder {name}: {data}")


# --------------------------------------------------------------------------
# IMAP parsing helpers
# --------------------------------------------------------------------------

def parse_labels(prefix: str) -> list[str]:
    start = prefix.find("X-GM-LABELS (")
    if start < 0:
        return []
    i, out = start + len("X-GM-LABELS ("), []
    while i < len(prefix) and prefix[i] != ")":
        if prefix[i] == " ":
            i += 1
        elif prefix[i] == '"':
            i += 1
            buf = []
            while i < len(prefix) and prefix[i] != '"':
                if prefix[i] == "\\" and i + 1 < len(prefix):
                    i += 1
                buf.append(prefix[i])
                i += 1
            i += 1
            out.append("".join(buf))
        else:
            j = i
            while j < len(prefix) and prefix[j] not in ' )"':
                j += 1
            out.append(prefix[i:j])
            i = j
    return out


def parse_fetch(data) -> list[dict]:
    items: list[dict] = []
    for part in data or []:
        if isinstance(part, tuple):
            items.append({"prefix": part[0].decode("utf-8", "replace"), "body": part[1]})
        elif isinstance(part, (bytes, bytearray)) and items:
            items[-1]["prefix"] += " " + part.decode("utf-8", "replace")
    out = []
    for it in items:
        p = it["prefix"]
        uid = re.search(r"\bUID (\d+)", p)
        if not uid:
            continue
        thread = re.search(r"X-GM-THRID (\d+)", p)
        flags = re.search(r"FLAGS \(([^)]*)\)", p)
        out.append(
            {
                "uid": int(uid[1]),
                "thread": thread[1] if thread else None,
                "flags": flags[1].split() if flags else [],
                "labels": parse_labels(p),
                "body": it["body"],
            }
        )
    return out


def gm_search(m: imaplib.IMAP4_SSL, query: str) -> list[int]:
    if query.strip():
        m.literal = query.encode("utf-8")
        typ, data = m.uid("SEARCH", "CHARSET", "UTF-8", "X-GM-RAW")
    else:
        typ, data = m.uid("SEARCH", None, "ALL")
    if typ != "OK":
        raise ToolError(f"Gmail search failed: {data}")
    return [int(x) for x in (data[0] or b"").split()]


def fetch(m, uids: list[int], what: str) -> list[dict]:
    out: list[dict] = []
    for i in range(0, len(uids), 40):
        chunk = ",".join(str(u) for u in uids[i : i + 40])
        typ, data = m.uid("FETCH", chunk, f"(FLAGS X-GM-THRID X-GM-LABELS {what})")
        if typ != "OK":
            raise ToolError(f"Gmail fetch failed: {data}")
        out.extend(parse_fetch(data))
    return out


def one_message(mb: Mailbox, uid: int) -> tuple[dict, EmailMessage]:
    mb.select("all")
    rows = fetch(mb.m, [uid], "BODY.PEEK[]")
    if not rows:
        raise ToolError(f"No message with id {uid} (ids come from gmail_search; trashed/spam messages are not searchable)")
    return rows[0], email.message_from_bytes(rows[0]["body"], policy=policy.default)


# --------------------------------------------------------------------------
# Message formatting
# --------------------------------------------------------------------------

def summarize(row: dict, msg: Optional[EmailMessage] = None) -> dict:
    h = msg if msg is not None else email.message_from_bytes(row["body"], policy=policy.default)
    return {
        "id": row["uid"],
        "thread_id": row["thread"],
        "from": str(h["from"] or ""),
        "to": str(h["to"] or ""),
        "subject": str(h["subject"] or ""),
        "date": str(h["date"] or ""),
        "unread": "\\Seen" not in row["flags"],
        "starred": "\\Flagged" in row["flags"],
        "labels": [l for l in row["labels"] if l not in ("\\Important",)],
    }


class _Strip(HTMLParser):
    BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "table"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    p = _Strip()
    p.feed(html)
    return re.sub(r"\n\s*\n+", "\n\n", "".join(p.parts)).strip()


def body_text(msg: EmailMessage) -> tuple[str, str]:
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return "", "none"
    content = part.get_content()
    if part.get_content_type() == "text/html":
        return html_to_text(content), "html-converted"
    return content, "plain"


def attachments_of(msg: EmailMessage) -> list[dict]:
    out = []
    for a in msg.iter_attachments():
        payload = a.get_payload(decode=True) if not a.is_multipart() else None
        out.append({"filename": a.get_filename(), "content_type": a.get_content_type(), "size": len(payload) if payload else None})
    return out


def full_view(row: dict, msg: EmailMessage, max_chars: int) -> dict:
    text, fmt = body_text(msg)
    return {
        **summarize(row, msg),
        "cc": str(msg["cc"] or ""),
        "reply_to": str(msg["reply-to"] or ""),
        "message_id": str(msg["message-id"] or ""),
        "body": text[:max_chars],
        "body_format": fmt,
        "truncated": len(text) > max_chars,
        "attachments": attachments_of(msg),
    }


# --------------------------------------------------------------------------
# Composing and sending
# --------------------------------------------------------------------------

def addrs(value) -> list[str]:
    if not value:
        return []
    items = value if isinstance(value, list) else [value]
    return [a for _, a in getaddresses([str(i) for i in items]) if a]


def build_message(sender: str, args: dict, *, in_reply_to: Optional[str] = None, references: Optional[str] = None, require_recipient: bool = True) -> EmailMessage:
    to, cc, bcc = addrs(args.get("to")), addrs(args.get("cc")), addrs(args.get("bcc"))
    if require_recipient and not (to or cc or bcc):
        raise ToolError("At least one recipient (to, cc or bcc) is required")
    msg = EmailMessage()
    msg["From"] = sender
    if to:
        msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    if bcc:
        msg["Bcc"] = ", ".join(bcc)
    msg["Subject"] = args.get("subject") or "(no subject)"
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=sender.split("@")[-1])
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = f"{references} {in_reply_to}".strip() if references else in_reply_to
    body, html = args.get("body") or "", args.get("html")
    if html:
        msg.set_content(body or html_to_text(html))
        msg.add_alternative(html, subtype="html")
    else:
        msg.set_content(body)
    for att in args.get("attachments") or []:
        try:
            data = base64.b64decode(att["content_base64"], validate=True)
        except Exception as e:  # noqa: BLE001
            raise ToolError(f"Attachment '{att.get('filename')}' has invalid base64 content") from e
        if len(data) > MAX_ATTACHMENT_BYTES * 2:
            raise ToolError("Attachment too large for this server (max ~4 MB)")
        mime = att.get("mime_type") or "application/octet-stream"
        main, _, sub = mime.partition("/")
        msg.add_attachment(data, maintype=main, subtype=sub or "octet-stream", filename=att["filename"])
    return msg


def smtp_send(msg: EmailMessage) -> list[str]:
    address, password = credentials()
    recipients = addrs(msg.get_all("To", []) + msg.get_all("Cc", []) + msg.get_all("Bcc", []))
    with smtplib.SMTP_SSL(SMTP_HOST, 465, timeout=30, context=ssl.create_default_context()) as s:
        try:
            s.login(address, password)
        except smtplib.SMTPAuthenticationError as e:
            raise ToolError("Gmail login failed. Use a 16-character app password, not your normal password.") from e
        s.send_message(msg, from_addr=address, to_addrs=recipients)
    return recipients


def find_by_message_id(mb: Mailbox, message_id: str, role: str = "all") -> Optional[int]:
    mb.select(role, readonly=True)
    for _ in range(4):
        mb.m.literal = message_id.encode()
        typ, data = mb.m.uid("SEARCH", "HEADER", "Message-ID")
        uids = [int(x) for x in (data[0] or b"").split()] if typ == "OK" else []
        if uids:
            return uids[-1]
        time.sleep(0.6)
    return None


def expunge_draft(mb: Mailbox, message_id: str) -> None:
    uid = find_by_message_id(mb, message_id, "drafts")
    if uid is None:
        return
    mb.select("drafts", readonly=False)
    mb.m.uid("STORE", str(uid), "+FLAGS.SILENT", "(\\Deleted)")
    mb.m.expunge()


def uid_set(ids) -> str:
    try:
        uids = sorted({int(i) for i in ids})
    except (TypeError, ValueError) as e:
        raise ToolError("ids must be a list of message ids from gmail_search") from e
    if not 1 <= len(uids) <= 100:
        raise ToolError("Provide 1-100 message ids")
    return ",".join(str(u) for u in uids)


async def run(fn, args):
    try:
        return await asyncio.to_thread(fn, args)
    except (imaplib.IMAP4.error, smtplib.SMTPException, OSError) as e:
        raise ToolError(f"Gmail error: {e}") from e


IDS = {"type": "array", "items": {"type": "integer"}, "description": "Message ids (from gmail_search), up to 100"}
MSG_ID = {"type": "integer", "description": "Message id from gmail_search / gmail_list_drafts"}
RECIPIENTS = {"type": "array", "items": {"type": "string"}, "description": "Email addresses"}
ATTACHMENTS = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {"filename": {"type": "string"}, "content_base64": {"type": "string"}, "mime_type": {"type": "string"}},
        "required": ["filename", "content_base64"],
    },
    "description": "Optional attachments (base64), up to about 4 MB in total",
}
COMPOSE = {
    "to": RECIPIENTS,
    "cc": RECIPIENTS,
    "bcc": RECIPIENTS,
    "subject": {"type": "string"},
    "body": {"type": "string", "description": "Plain-text body"},
    "html": {"type": "string", "description": "Optional HTML body (body is used as the plain-text alternative)"},
    "attachments": ATTACHMENTS,
}


# --------------------------------------------------------------------------
# Tools: read
# --------------------------------------------------------------------------

@tool(
    "gmail_list_labels",
    "List Gmail labels/folders and the unread count of the inbox.",
    {},
)
async def gmail_list_labels(args):
    def work(_):
        with Mailbox() as mb:
            typ, data = mb.m.list()
            labels = []
            for raw in data or []:
                parsed = parse_list_line(raw.decode("utf-8", "replace")) if isinstance(raw, bytes) else None
                if parsed and "\\Noselect" not in parsed[0]:
                    labels.append(parsed[1])
            typ, st = mb.m.status("INBOX", "(MESSAGES UNSEEN)")
            counts = re.search(r"MESSAGES (\d+) UNSEEN (\d+)", st[0].decode()) if typ == "OK" and st and st[0] else None
            return {
                "labels": labels,
                "system_folders": mb.folders,
                "inbox": {"messages": int(counts[1]), "unread": int(counts[2])} if counts else None,
                "account": mb.address,
            }

    return await run(work, args)


@tool(
    "gmail_search",
    "Search email with Gmail search syntax (from:, to:, subject:, is:unread, has:attachment, label:, newer_than:2d, after:2026/01/01...). Covers All Mail (not Trash/Spam). Newest first.",
    {
        "query": {"type": "string", "description": "Gmail search query. Default 'in:inbox'. Use '' for everything."},
        "limit": {"type": "integer", "description": "1-100 (default 20)"},
        "before_id": {"type": "integer", "description": "Only messages with id lower than this (pagination)"},
    },
)
async def gmail_search(args):
    def work(a):
        limit = max(1, min(int(a.get("limit", 20)), 100))
        query = a["query"] if "query" in a and a["query"] is not None else "in:inbox"
        with Mailbox() as mb:
            mb.select("all")
            uids = gm_search(mb.m, query)
            if a.get("before_id"):
                uids = [u for u in uids if u < int(a["before_id"])]
            uids = sorted(uids, reverse=True)[:limit]
            rows = fetch(mb.m, uids, "BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE)]") if uids else []
        rows.sort(key=lambda r: -r["uid"])
        return {"query": query, "count": len(rows), "messages": [summarize(r) for r in rows]}

    return await run(work, args)


@tool(
    "gmail_get_message",
    "Read one email: headers, text body and attachment list. Does not mark it as read unless mark_read is true.",
    {
        "id": MSG_ID,
        "mark_read": {"type": "boolean"},
        "max_chars": {"type": "integer", "description": "Truncate the body (default 20000)"},
    },
    ["id"],
)
async def gmail_get_message(args):
    def work(a):
        with Mailbox() as mb:
            row, msg = one_message(mb, int(a["id"]))
            if a.get("mark_read"):
                mb.select("all", readonly=False)
                mb.m.uid("STORE", str(row["uid"]), "+FLAGS.SILENT", "(\\Seen)")
                row["flags"].append("\\Seen")
        return full_view(row, msg, int(a.get("max_chars", 20000)))

    return await run(work, args)


@tool(
    "gmail_get_thread",
    "Read a whole conversation (oldest first). Bodies are truncated to 4000 characters each; up to 30 messages.",
    {"thread_id": {"type": "string", "description": "thread_id from gmail_search"}},
    ["thread_id"],
)
async def gmail_get_thread(args):
    def work(a):
        tid = str(a["thread_id"])
        if not tid.isdigit():
            raise ToolError("thread_id must be the numeric thread_id from gmail_search")
        with Mailbox() as mb:
            mb.select("all")
            typ, data = mb.m.uid("SEARCH", "X-GM-THRID", tid)
            uids = sorted(int(x) for x in (data[0] or b"").split())[:30] if typ == "OK" else []
            rows = fetch(mb.m, uids, "BODY.PEEK[]") if uids else []
        rows.sort(key=lambda r: r["uid"])
        return {"thread_id": tid, "count": len(rows), "messages": [full_view(r, email.message_from_bytes(r["body"], policy=policy.default), 4000) for r in rows]}

    return await run(work, args)


@tool(
    "gmail_get_attachment",
    "Download one attachment as base64 (max about 2 MB).",
    {"id": MSG_ID, "filename": {"type": "string"}},
    ["id", "filename"],
)
async def gmail_get_attachment(args):
    def work(a):
        with Mailbox() as mb:
            _, msg = one_message(mb, int(a["id"]))
        for att in msg.iter_attachments():
            if att.get_filename() == a["filename"]:
                data = att.get_payload(decode=True) or b""
                if len(data) > MAX_ATTACHMENT_BYTES:
                    raise ToolError(f"Attachment is {len(data)} bytes; limit is {MAX_ATTACHMENT_BYTES}")
                return {"filename": a["filename"], "content_type": att.get_content_type(), "size": len(data), "content_base64": base64.b64encode(data).decode()}
        raise ToolError(f"No attachment named '{a['filename']}'. Available: {[x['filename'] for x in attachments_of(msg)]}")

    return await run(work, args)


# --------------------------------------------------------------------------
# Tools: send and drafts
# --------------------------------------------------------------------------

@tool(
    "gmail_send_email",
    "Send an email immediately from the connected account. It cannot be unsent; use gmail_create_draft to let the user review first.",
    COMPOSE,
    ["to", "subject", "body"],
    hint="write",
)
async def gmail_send_email(args):
    def work(a):
        address, _ = credentials()
        msg = build_message(address, a)
        recipients = smtp_send(msg)
        return {"sent": True, "to": recipients, "subject": msg["Subject"], "message_id": msg["Message-ID"]}

    return await run(work, args)


def reply_headers(msg: EmailMessage) -> tuple[str, str, str]:
    subject = str(msg["subject"] or "")
    return (subject if subject.lower().startswith("re:") else f"Re: {subject}", str(msg["message-id"] or ""), str(msg["references"] or ""))


@tool(
    "gmail_reply",
    "Reply to an email in its thread (sends immediately). reply_all also replies to everyone on To/Cc. The original text is quoted below your reply.",
    {
        "id": MSG_ID,
        "body": {"type": "string"},
        "html": {"type": "string"},
        "reply_all": {"type": "boolean"},
        "quote_original": {"type": "boolean", "description": "Default true"},
        "attachments": ATTACHMENTS,
    },
    ["id", "body"],
    hint="write",
)
async def gmail_reply(args):
    def work(a):
        address, _ = credentials()
        with Mailbox() as mb:
            _, orig = one_message(mb, int(a["id"]))
        subject, msgid, refs = reply_headers(orig)
        to = addrs(orig["reply-to"] or orig["from"])
        cc = []
        if a.get("reply_all"):
            everyone = addrs([str(orig["to"] or ""), str(orig["cc"] or "")])
            cc = [x for x in everyone if x.lower() not in (address.lower(), *(t.lower() for t in to))]
        body = a["body"]
        if a.get("quote_original", True):
            text, _ = body_text(orig)
            quoted = "\n".join("> " + line for line in text.splitlines()[:200])
            body += f"\n\nOn {orig['date']}, {orig['from']} wrote:\n{quoted}"
        msg = build_message(address, {"to": to, "cc": cc, "subject": subject, "body": body, "html": a.get("html"), "attachments": a.get("attachments")}, in_reply_to=msgid, references=refs)
        recipients = smtp_send(msg)
        return {"sent": True, "to": recipients, "subject": subject}

    return await run(work, args)


@tool(
    "gmail_forward",
    "Forward an email (the original is attached as .eml). Sends immediately.",
    {"id": MSG_ID, "to": RECIPIENTS, "cc": RECIPIENTS, "note": {"type": "string", "description": "Text added above the forwarded message"}},
    ["id", "to"],
    hint="write",
)
async def gmail_forward(args):
    def work(a):
        address, _ = credentials()
        with Mailbox() as mb:
            _, orig = one_message(mb, int(a["id"]))
        subject = str(orig["subject"] or "")
        msg = build_message(address, {"to": a["to"], "cc": a.get("cc"), "subject": subject if subject.lower().startswith("fwd:") else f"Fwd: {subject}", "body": a.get("note") or "Forwarded message attached."})
        msg.add_attachment(orig, filename="forwarded-message.eml")
        recipients = smtp_send(msg)
        return {"sent": True, "to": recipients}

    return await run(work, args)


@tool("gmail_create_draft", "Save a draft in Gmail (does not send). It shows up in Gmail's Drafts.", COMPOSE, ["subject", "body"], hint="write")
async def gmail_create_draft(args):
    def work(a):
        address, _ = credentials()
        msg = build_message(address, a, require_recipient=False)
        with Mailbox() as mb:
            drafts = mb.folders.get("drafts")
            if not drafts:
                raise ToolError("Could not find the Gmail Drafts folder")
            typ, data = mb.m.append(quote(drafts), "(\\Draft)", imaplib.Time2Internaldate(time.time()), msg.as_bytes())
            if typ != "OK":
                raise ToolError(f"Could not save draft: {data}")
            uid = find_by_message_id(mb, msg["Message-ID"])
        return {"id": uid, "subject": msg["Subject"], "note": "Saved to Drafts. Send it with gmail_send_draft."}

    return await run(work, args)


@tool("gmail_list_drafts", "List drafts, newest first.", {"limit": {"type": "integer", "description": "1-100 (default 20)"}})
async def gmail_list_drafts(args):
    return await gmail_search({"query": "in:drafts", "limit": args.get("limit", 20)})


@tool("gmail_send_draft", "Send an existing draft, then remove it from Drafts. Sends immediately.", {"id": MSG_ID}, ["id"], hint="write")
async def gmail_send_draft(args):
    def work(a):
        with Mailbox() as mb:
            _, msg = one_message(mb, int(a["id"]))
            if not addrs(msg.get_all("To", []) + msg.get_all("Cc", []) + msg.get_all("Bcc", [])):
                raise ToolError("This draft has no recipients")
            if msg["Message-ID"] is None:
                msg["Message-ID"] = make_msgid(domain=mb.address.split("@")[-1])
            recipients = smtp_send(msg)
            expunge_draft(mb, str(msg["Message-ID"]))
        return {"sent": True, "to": recipients, "subject": str(msg["Subject"] or "")}

    return await run(work, args)


@tool("gmail_delete_draft", "Permanently delete a draft.", {"id": MSG_ID}, ["id"], hint="destructive")
async def gmail_delete_draft(args):
    def work(a):
        with Mailbox() as mb:
            row, msg = one_message(mb, int(a["id"]))
            if "\\Draft" not in row["flags"] and "\\Draft" not in row["labels"]:
                raise ToolError("That message is not a draft; use gmail_trash to delete regular mail")
            if not msg["Message-ID"]:
                raise ToolError("Draft has no Message-ID; delete it in Gmail")
            expunge_draft(mb, str(msg["Message-ID"]))
        return {"deleted": int(a["id"])}

    return await run(work, args)


# --------------------------------------------------------------------------
# Tools: organize
# --------------------------------------------------------------------------

@tool(
    "gmail_modify",
    "Change messages: mark read/unread, star/unstar, archive (remove from inbox), add or remove labels. New labels are created automatically.",
    {
        "ids": IDS,
        "read": {"type": "boolean", "description": "true = mark read, false = mark unread"},
        "starred": {"type": "boolean"},
        "archive": {"type": "boolean", "description": "true = remove from Inbox"},
        "add_labels": {"type": "array", "items": {"type": "string"}},
        "remove_labels": {"type": "array", "items": {"type": "string"}},
    },
    ["ids"],
    hint="write",
)
async def gmail_modify(args):
    def work(a):
        uids = uid_set(a["ids"])
        changes = []
        with Mailbox() as mb:
            mb.select("all", readonly=False)

            def store(op, item, value):
                typ, data = mb.m.uid("STORE", uids, op, value)
                if typ != "OK":
                    raise ToolError(f"Gmail refused the change: {data}")
                changes.append(item)

            if a.get("read") is not None:
                store("+FLAGS.SILENT" if a["read"] else "-FLAGS.SILENT", "read" if a["read"] else "unread", "(\\Seen)")
            if a.get("starred") is not None:
                store("+FLAGS.SILENT" if a["starred"] else "-FLAGS.SILENT", "starred" if a["starred"] else "unstarred", "(\\Flagged)")
            if a.get("archive"):
                store("-X-GM-LABELS", "archived", "(\\Inbox)")
            for op, key in (("+X-GM-LABELS", "add_labels"), ("-X-GM-LABELS", "remove_labels")):
                labels = a.get(key) or []
                if labels:
                    if not all(l.isascii() for l in labels):
                        raise ToolError("Label names must be ASCII")
                    store(op, f"{key}:{labels}", "(" + " ".join(quote(l) for l in labels) + ")")
        if not changes:
            raise ToolError("Nothing to change: pass read, starred, archive, add_labels or remove_labels")
        return {"ids": [int(u) for u in uids.split(",")], "applied": changes}

    return await run(work, args)


def copy_to(role: str, ids) -> dict:
    uids = uid_set(ids)
    with Mailbox() as mb:
        folder = mb.folders.get(role)
        if not folder:
            raise ToolError(f"Could not find the Gmail '{role}' folder")
        mb.select("all", readonly=False)
        typ, data = mb.m.uid("COPY", uids, quote(folder))
        if typ != "OK":
            raise ToolError(f"Gmail refused: {data}")
    return {"ids": [int(u) for u in uids.split(",")], "moved_to": role}


@tool("gmail_trash", "Move messages to Trash (Gmail deletes them after 30 days; recover them in Gmail).", {"ids": IDS}, ["ids"], hint="destructive")
async def gmail_trash(args):
    return await run(lambda a: copy_to("trash", a["ids"]), args)


@tool("gmail_mark_spam", "Move messages to Spam.", {"ids": IDS}, ["ids"], hint="destructive")
async def gmail_mark_spam(args):
    return await run(lambda a: copy_to("junk", a["ids"]), args)


@tool(
    "gmail_create_label",
    "Create a label. Use '/' for nested labels (Work/Invoices).",
    {"name": {"type": "string"}},
    ["name"],
    hint="write",
)
async def gmail_create_label(args):
    def work(a):
        if not a["name"].isascii():
            raise ToolError("Label names must be ASCII")
        with Mailbox() as mb:
            typ, data = mb.m.create(quote(a["name"]))
            if typ != "OK":
                raise ToolError(f"Could not create label: {data}")
        return {"created": a["name"]}

    return await run(work, args)


@tool(
    "gmail_delete_label",
    "Delete a label. Messages that had it are kept.",
    {"name": {"type": "string"}},
    ["name"],
    hint="destructive",
)
async def gmail_delete_label(args):
    def work(a):
        with Mailbox() as mb:
            typ, data = mb.m.delete(quote(a["name"]))
            if typ != "OK":
                raise ToolError(f"Could not delete label: {data}")
        return {"deleted": a["name"]}

    return await run(work, args)
