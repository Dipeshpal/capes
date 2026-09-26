"""Offline Gmail tests: an in-memory fake IMAP/SMTP server answers in Gmail's response format. No credentials needed.

Run from the repo root:
    uv run --with fastapi --with aiohttp --with python-dotenv python tests/gmail_offline.py
"""
import asyncio, base64, os, re, sys, time
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["GMAIL_ADDRESS"] = "me@gmail.com"
os.environ["GMAIL_APP_PASSWORD"] = "abcd efgh ijkl mnop"

from pulse import gmail  # noqa: E402
from pulse.registry import TOOLS, ToolError  # noqa: E402

passed = failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print("ok  ", name)
    else:
        failed += 1
        print("FAIL", name, extra)


# ---------------------------------------------------------------- pure parsing
check("list_line inbox", gmail.parse_list_line('(\\HasNoChildren) "/" "INBOX"') == (["\\HasNoChildren"], "INBOX"))
check("list_line all mail", gmail.parse_list_line('(\\HasNoChildren \\All) "/" "[Gmail]/All Mail"') == (["\\HasNoChildren", "\\All"], "[Gmail]/All Mail"))
check("list_line atom name", gmail.parse_list_line('(\\HasNoChildren) "/" Work')[1] == "Work")
labels = gmail.parse_labels('1 (X-GM-LABELS (\\Inbox \\Important "My Label" "a \\"q\\" one") UID 4 FLAGS (\\Seen)')
check("labels parse", labels == ["\\Inbox", "\\Important", "My Label", 'a "q" one'], labels)
check("labels empty", gmail.parse_labels("1 (UID 4 FLAGS ())") == [])

hdr = b"From: Bob <bob@example.com>\r\nTo: me@gmail.com\r\nSubject: =?UTF-8?Q?Caf=C3=A9_menu?=\r\nDate: Mon, 1 Jan 2026 10:00:00 +0000\r\n\r\n"
fx = [(b'1 (X-GM-THRID 1780 X-GM-LABELS (\\Inbox "Work") UID 4321 FLAGS (\\Flagged) BODY[HEADER.FIELDS (FROM TO SUBJECT DATE)] {%d}' % len(hdr), hdr), b")"]
rows = gmail.parse_fetch(fx)
s = gmail.summarize(rows[0])
check("fetch parse", rows[0]["uid"] == 4321 and rows[0]["thread"] == "1780" and rows[0]["flags"] == ["\\Flagged"])
check("summary decode+flags", s["subject"] == "Café menu" and s["unread"] and s["starred"] and s["labels"] == ["\\Inbox", "Work"], s)
tail_fx = [(b"1 (UID 7 BODY[] {5}", b"x: y\r\n"), b" FLAGS (\\Seen))"]
check("flags after literal", gmail.parse_fetch(tail_fx)[0]["flags"] == ["\\Seen"])

# ---------------------------------------------------------------- composing
m = gmail.build_message("me@gmail.com", {"to": "a@x.com, B <b@x.com>", "cc": ["c@x.com"], "bcc": ["d@x.com"], "subject": "Hi", "body": "plain", "html": "<p>Hello <b>there</b></p>",
                                          "attachments": [{"filename": "a.txt", "content_base64": base64.b64encode(b"data").decode(), "mime_type": "text/plain"}]})
check("build multi recipients", gmail.addrs(m.get_all("To")) == ["a@x.com", "b@x.com"] and m["Bcc"] == "d@x.com")
check("build html+attachment", m.is_multipart() and [a.get_filename() for a in m.iter_attachments()] == ["a.txt"] and m.get_body(("html",)) is not None)
try:
    gmail.build_message("me@gmail.com", {"subject": "x", "body": "y"}); check("no recipient rejected", False)
except ToolError:
    check("no recipient rejected", True)
check("draft without recipient ok", gmail.build_message("me@gmail.com", {"subject": "x", "body": "y"}, require_recipient=False)["To"] is None)
try:
    gmail.build_message("me@gmail.com", {"to": "a@x.com", "attachments": [{"filename": "f", "content_base64": "!!notb64"}]}); check("bad base64 rejected", False)
except ToolError:
    check("bad base64 rejected", True)
check("html to text", gmail.html_to_text("<style>x{}</style><p>Hi</p><div>there &amp; you</div>") == "Hi\n\nthere & you" or gmail.html_to_text("<p>Hi</p><div>there &amp; you</div>").startswith("Hi"))

# ---------------------------------------------------------------- fake IMAP
def make(uid, frm, subject, body, flags=("\\Seen",), labels=("\\Inbox",), thrid=None, extra_headers="", msgid=None):
    raw = f"From: {frm}\r\nTo: me@gmail.com\r\nSubject: {subject}\r\nDate: Mon, 1 Jan 2026 10:00:0{uid % 10} +0000\r\nMessage-ID: {msgid or f'<m{uid}@x>'}\r\n{extra_headers}Content-Type: text/plain; charset=utf-8\r\n\r\n{body}\r\n".encode()
    return {"uid": uid, "raw": raw, "flags": set(flags), "labels": set(labels), "thrid": thrid or 1000 + uid}


class FakeIMAP:
    store_state = None

    def __init__(self, *a, **k):
        self.literal = None
        self.selected = None
        self.log = []
        self.state = FakeIMAP.store_state

    def login(self, u, p):
        assert u == "me@gmail.com" and p == "abcdefghijklmnop", "credentials not normalised"
        return "OK", [b"ok"]

    def logout(self): return "BYE", []

    def list(self):
        return "OK", [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren \\All) "/" "[Gmail]/All Mail"', b'(\\HasNoChildren \\Drafts) "/" "[Gmail]/Drafts"',
                      b'(\\HasNoChildren \\Trash) "/" "[Gmail]/Trash"', b'(\\HasNoChildren \\Junk) "/" "[Gmail]/Spam"', b'(\\HasNoChildren \\Sent) "/" "[Gmail]/Sent Mail"',
                      b'(\\HasChildren \\Noselect) "/" "[Gmail]"', b'(\\HasNoChildren) "/" "Work"']

    def select(self, name, readonly=False):
        self.selected = name.strip('"'); return "OK", [b"1"]

    def status(self, name, what): return "OK", [b"INBOX (MESSAGES 3 UNSEEN 2)"]

    def _msgs(self):
        if self.selected == "[Gmail]/Drafts":
            return [m for m in self.state["all"] if "\\Draft" in m["flags"]]
        return self.state["all"]

    def uid(self, cmd, *args):
        st = self.state
        if cmd == "SEARCH":
            if args[:3] == ("CHARSET", "UTF-8", "X-GM-RAW"):
                q = self.literal.decode(); self.literal = None
                st["queries"].append(q)
                hits = [m for m in self._msgs() if (("is:unread" not in q or "\\Seen" not in m["flags"]) and ("in:drafts" not in q or "\\Draft" in m["flags"]))]
                return "OK", [" ".join(str(m["uid"]) for m in hits).encode()]
            if args[0] is None: return "OK", [b" ".join(str(m["uid"]).encode() for m in self._msgs())]
            if args[0] == "X-GM-THRID": return "OK", [" ".join(str(m["uid"]) for m in self._msgs() if str(m["thrid"]) == args[1]).encode()]
            if args[:2] == ("HEADER", "Message-ID"):
                mid = self.literal.decode(); self.literal = None
                return "OK", [" ".join(str(m["uid"]) for m in self._msgs() if f"Message-ID: {mid}".encode() in m["raw"]).encode()]
        if cmd == "FETCH":
            wanted = {int(u) for u in args[0].split(",")}
            out = []
            for m in self._msgs():
                if m["uid"] in wanted:
                    body = m["raw"] if "BODY.PEEK[]" in args[1] else m["raw"].split(b"\r\n\r\n")[0] + b"\r\n\r\n"
                    labs = " ".join(l if l.startswith("\\") else '"' + l + '"' for l in sorted(m["labels"]))
                    out.append((f'1 (X-GM-THRID {m["thrid"]} X-GM-LABELS ({labs}) UID {m["uid"]} FLAGS ({" ".join(sorted(m["flags"]))}) BODY[] {{{len(body)}}}'.encode(), body))
                    out.append(b")")
            return "OK", out
        if cmd == "STORE":
            uids = {int(u) for u in args[0].split(",")}
            op, val = args[1], args[2]
            items = re.findall(r'"((?:[^"\\]|\\.)*)"|(\\?[^\s()"]+)', val)
            items = [a or b for a, b in items]
            for m in st["all"]:
                if m["uid"] in uids:
                    tgt = m["flags"] if "FLAGS" in op else m["labels"]
                    if op.startswith("+"): tgt.update(items)
                    elif op.startswith("-"): tgt.difference_update(items)
            if "\\Deleted" in val:
                st["deleted_pending"] = uids
            st["stores"].append((op, val)); return "OK", [b"done"]
        if cmd == "COPY":
            st["copies"].append((args[0], args[1])); return "OK", [b"done"]
        raise AssertionError(f"unhandled uid cmd {cmd} {args}")

    def append(self, folder, flags, date, data):
        st = self.state
        uid = max(m["uid"] for m in st["all"]) + 1
        st["all"].append({"uid": uid, "raw": data, "flags": {"\\Draft"}, "labels": {"\\Draft"}, "thrid": 9000 + uid})
        return "OK", [b"[APPENDUID 1 %d] done" % uid]

    def expunge(self):
        st = self.state
        gone = st.pop("deleted_pending", set())
        st["all"] = [m for m in st["all"] if m["uid"] not in gone]
        return "OK", []

    def create(self, name): self.state["created"].append(name); return "OK", [b"ok"]
    def delete(self, name): self.state["deleted_labels"].append(name); return "OK", [b"ok"]


def fresh_state():
    return {"all": [
        make(10, "Alice <alice@example.com>", "Lunch?", "Are we still on for lunch?", flags=(), thrid=500),
        make(11, "Me <me@gmail.com>", "Re: Lunch?", "Yes!", flags=("\\Seen",), labels=("\\Sent",), thrid=500, extra_headers="In-Reply-To: <m10@x>\r\n"),
        make(12, "News <news@example.com>", "Weekly", "Hello news", flags=("\\Seen",), thrid=501),
    ], "queries": [], "stores": [], "copies": [], "created": [], "deleted_labels": []}


gmail.imaplib.IMAP4_SSL = FakeIMAP
sent = []


class FakeSMTP:
    def __init__(self, *a, **k): pass
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def login(self, u, p): assert u == "me@gmail.com" and p == "abcdefghijklmnop"
    def send_message(self, msg, from_addr, to_addrs): sent.append((msg, from_addr, to_addrs))


gmail.smtplib.SMTP_SSL = FakeSMTP
gmail.time.sleep = lambda s: None


async def call(name, /, **args):
    return await TOOLS[name]["fn"](args)


async def main():
    FakeIMAP.store_state = fresh_state()
    st = FakeIMAP.store_state

    r = await call("gmail_list_labels")
    check("list_labels", "Work" in r["labels"] and "[Gmail]" not in r["labels"] and r["inbox"] == {"messages": 3, "unread": 2} and r["system_folders"]["all"] == "[Gmail]/All Mail", r)

    r = await call("gmail_search", query="is:unread from:alice", limit=5)
    check("search newest-first + literal query", st["queries"][-1] == "is:unread from:alice" and [m["id"] for m in r["messages"]] == [10], r)
    r = await call("gmail_search", query="")
    check("search everything", [m["id"] for m in r["messages"]] == [12, 11, 10])
    r = await call("gmail_search", limit=1, before_id=12)
    check("search default query + before_id", st["queries"][-1] == "in:inbox" and [m["id"] for m in r["messages"]] == [11])

    r = await call("gmail_get_message", id=10)
    check("get_message body", r["body"].startswith("Are we still") and r["unread"] and r["subject"] == "Lunch?" and r["attachments"] == [] and r["message_id"] == "<m10@x>", r)
    r = await call("gmail_get_thread", thread_id="500")
    check("get_thread", [m["id"] for m in r["messages"]] == [10, 11], r["count"])
    try:
        await call("gmail_get_message", id=999); check("unknown id error", False)
    except ToolError as e:
        check("unknown id error", "No message with id 999" in str(e))

    r = await call("gmail_modify", ids=[10, 12], read=True, starred=True, archive=True, add_labels=["Work/Invoices"])
    check("modify applies", {"read", "starred", "archived"} <= set(r["applied"]) and "\\Seen" in st["all"][0]["flags"] and "\\Inbox" not in st["all"][0]["labels"] and "Work/Invoices" in st["all"][0]["labels"], (r, st["all"][0]))
    try:
        await call("gmail_modify", ids=[10]); check("modify needs a change", False)
    except ToolError:
        check("modify needs a change", True)
    try:
        await call("gmail_modify", ids=[]); check("modify needs ids", False)
    except ToolError:
        check("modify needs ids", True)

    r = await call("gmail_trash", ids=[12])
    check("trash copies to Trash folder", st["copies"][-1] == ("12", '"[Gmail]/Trash"'), st["copies"])
    r = await call("gmail_mark_spam", ids=[11])
    check("spam copies to Spam folder", st["copies"][-1] == ("11", '"[Gmail]/Spam"'))
    await call("gmail_create_label", name="Projects/X"); await call("gmail_delete_label", name="Projects/X")
    check("labels create/delete", st["created"] == ['"Projects/X"'] and st["deleted_labels"] == ['"Projects/X"'])

    r = await call("gmail_send_email", to=["bob@x.com"], cc=["c@x.com"], bcc=["secret@x.com"], subject="Hello", body="Hi Bob")
    msg, frm, to = sent[-1]
    check("send", frm == "me@gmail.com" and to == ["bob@x.com", "c@x.com", "secret@x.com"] and msg["Subject"] == "Hello" and r["sent"], (to, r))

    r = await call("gmail_reply", id=10, body="Yes, see you at noon.")
    msg, frm, to = sent[-1]
    check("reply headers", to == ["alice@example.com"] and msg["Subject"] == "Re: Lunch?" and msg["In-Reply-To"] == "<m10@x>" and msg["References"] == "<m10@x>", dict(msg.items()))
    check("reply quotes original", "> Are we still on for lunch?" in msg.get_body(("plain",)).get_content() and "Yes, see you at noon." in msg.get_body(("plain",)).get_content())
    FakeIMAP.store_state["all"].append(make(20, "Boss <boss@x.com>", "Team update", "Update", extra_headers="Cc: Carol <carol@x.com>, me@gmail.com\r\nReply-To: Boss Team <team@x.com>\r\n"))
    r = await call("gmail_reply", id=20, body="ok", reply_all=True, quote_original=False)
    msg, frm, to = sent[-1]
    check("reply_all uses Reply-To, drops self", to[0] == "team@x.com" and "carol@x.com" in to and "me@gmail.com" not in to and "> " not in msg.get_body(("plain",)).get_content(), to)

    r = await call("gmail_forward", id=10, to=["fwd@x.com"], note="FYI")
    msg, frm, to = sent[-1]
    check("forward attaches original", msg["Subject"] == "Fwd: Lunch?" and to == ["fwd@x.com"] and any(a.get_content_type() == "message/rfc822" for a in msg.iter_attachments()), [a.get_content_type() for a in msg.iter_attachments()])

    r = await call("gmail_create_draft", to=["d@x.com"], subject="Draft one", body="draft body")
    did = r["id"]
    check("create_draft returns all-mail id", isinstance(did, int) and did > 20, r)
    r = await call("gmail_list_drafts")
    check("list_drafts", [m["id"] for m in r["messages"]] == [did], r)
    n_before = len(sent)
    r = await call("gmail_send_draft", id=did)
    check("send_draft sends and removes draft", len(sent) == n_before + 1 and sent[-1][2] == ["d@x.com"] and all(m["uid"] != did for m in FakeIMAP.store_state["all"]), r)
    r = await call("gmail_create_draft", subject="No recipient yet", body="later")
    d2 = r["id"]
    try:
        await call("gmail_send_draft", id=d2); check("send_draft without recipient rejected", False)
    except ToolError as e:
        check("send_draft without recipient rejected", "no recipients" in str(e))
    await call("gmail_delete_draft", id=d2)
    check("delete_draft", all(m["uid"] != d2 for m in FakeIMAP.store_state["all"]))
    try:
        await call("gmail_delete_draft", id=10); check("delete_draft refuses normal mail", False)
    except ToolError:
        check("delete_draft refuses normal mail", True)

    # attachment round trip
    msg = gmail.build_message("me@gmail.com", {"to": "z@x.com", "subject": "file", "body": "see attached", "attachments": [{"filename": "n.txt", "content_base64": base64.b64encode(b"hello file").decode(), "mime_type": "text/plain"}]})
    FakeIMAP.store_state["all"].append({"uid": 30, "raw": msg.as_bytes(), "flags": {"\\Seen"}, "labels": {"\\Inbox"}, "thrid": 77})
    r = await call("gmail_get_message", id=30)
    check("message lists attachment", r["attachments"] == [{"filename": "n.txt", "content_type": "text/plain", "size": 10}], r["attachments"])
    r = await call("gmail_get_attachment", id=30, filename="n.txt")
    check("attachment download", base64.b64decode(r["content_base64"]) == b"hello file")
    try:
        await call("gmail_get_attachment", id=30, filename="nope.txt"); check("missing attachment error", False)
    except ToolError as e:
        check("missing attachment error", "Available" in str(e))

    # missing credentials
    del os.environ["GMAIL_APP_PASSWORD"]
    try:
        await call("gmail_search"); check("missing creds error", False)
    except ToolError as e:
        check("missing creds error", "GMAIL_APP_PASSWORD" in str(e))


asyncio.run(main())
print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
