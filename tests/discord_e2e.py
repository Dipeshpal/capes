"""Discord end-to-end test against a RUNNING server (local or deployed).

  URL    server base URL (default http://localhost:8000)
  KEY    the server's MCP_API_KEY (default localtestkey)
  GUILD  Discord server id to test in
  MODE   read: read-only tools, safe on any server
         full: also runs every mutating tool. ONLY use a disposable test server: it posts messages,
               creates and deletes channels/roles/threads.
  BOT_ID optional bot user id, enables the member-role checks in full mode

Example:  GUILD=123 MODE=read python tests/discord_e2e.py
"""

import json
import os
import urllib.request

URL = os.environ.get("URL", "http://localhost:8000") + "/mcp"
KEY = os.environ.get("KEY", "localtestkey")
G = os.environ["GUILD"]
FULL = os.environ.get("MODE") == "full"
BOT_ID = os.environ.get("BOT_ID")
n = 0
results = []


def call(name, /, **args):
    global n
    n += 1
    req = urllib.request.Request(
        URL,
        data=json.dumps({"jsonrpc": "2.0", "id": n, "method": "tools/call", "params": {"name": name, "arguments": args}}).encode(),
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    )
    r = json.load(urllib.request.urlopen(req, timeout=90))["result"]
    text = r["content"][0]["text"]
    ok = not r["isError"]
    results.append((name, ok))
    print(("OK   " if ok else "FAIL ") + name + ("" if ok else "  -> " + text.replace("\n", " ")[:260]))
    return json.loads(text) if ok and text[:1] in "[{" else text


def expect_fail(name, /, **args):
    out = call(name, **args)
    results[-1] = (name + " (expected error)", results[-1][1] is False)
    return out


print("== read-only tools on", G)
call("discord_list_guilds")
call("discord_get_guild", guild_id=G)
chans = call("discord_list_channels", guild_id=G)[0]["channels"]
print("     channels:", [(c["name"], c["type"]) for c in chans])
text = next(c for c in chans if c["type"] == "text")["id"]
call("discord_get_channel", channel_id=text)
r = call("discord_read_channel", channel_id=text, limit=5)
print("     last msgs:", [(m["author"], m["content"][:25]) for m in r["messages"]][:3])
call("discord_list_pins", channel_id=text)
roles = call("discord_list_roles", guild_id=G)
print("     roles:", [(x["name"], len(x["permissions"])) for x in roles])
call("discord_list_threads", guild_id=G)
call("discord_list_members", guild_id=G, limit=5)
expect_fail("discord_send_message", channel_id=text)
expect_fail("discord_edit_channel", channel_id=text)
expect_fail("discord_read_channel")

if FULL:
    print("== mutating tools (test server only)")
    made = []
    general = text
    m1 = call("discord_send_message", channel_id=general, content="hello from capes e2e")
    m2 = call("discord_send_message", channel_id=general, content="embed test", embed={"title": "Capes", "description": "embed body", "color": 5793266})
    call("discord_send_message", channel_id=general, content="a reply", reply_to_message_id=m1["id"])
    call("discord_edit_message", channel_id=general, message_id=m1["id"], content="hello (edited)")
    call("discord_add_reaction", channel_id=general, message_id=m1["id"], emoji="👍")
    call("discord_add_reaction", channel_id=general, message_id=m1["id"], emoji="🔥")
    call("discord_pin_message", channel_id=general, message_id=m1["id"])
    print("     pins:", [p["content"] for p in call("discord_list_pins", channel_id=general)])
    call("discord_pin_message", channel_id=general, message_id=m1["id"], unpin=True)
    rd = call("discord_read_channel", channel_id=general, limit=10)
    print("     reactions seen:", [m.get("reactions") for m in rd["messages"] if m.get("reactions")])
    call("discord_remove_reaction", channel_id=general, message_id=m1["id"], emoji="🔥")
    call("discord_remove_reaction", channel_id=general, message_id=m1["id"], clear_all=True)
    extra = [call("discord_send_message", channel_id=general, content=f"bulk {i}")["id"] for i in range(3)]
    call("discord_bulk_delete_messages", channel_id=general, message_ids=extra)
    call("discord_delete_message", channel_id=general, message_id=m2["id"])

    cat = call("discord_create_channel", guild_id=G, name="pulse-category", type="category")
    made.append(cat["id"])
    ch = call("discord_create_channel", guild_id=G, name="pulse-text", topic="made by e2e", parent_id=cat["id"], slowmode_seconds=5)
    made.append(ch["id"])
    made.append(call("discord_create_channel", guild_id=G, name="pulse-voice", type="voice", parent_id=cat["id"])["id"])
    made.append(call("discord_create_channel", guild_id=G, name="pulse-forum", type="forum")["id"])
    priv = call("discord_create_channel", guild_id=G, name="pulse-private", private=True)
    made.append(priv["id"])
    call("discord_edit_channel", channel_id=ch["id"], name="pulse-text-renamed", topic="edited topic")
    role = call(
        "discord_create_role", guild_id=G, name="pulse-mod", permissions=["MANAGE_MESSAGES", "KICK_MEMBERS"], color="#ff8800", hoist=True, mentionable=True
    )
    call(
        "discord_set_channel_permission",
        channel_id=priv["id"],
        target_id=role["id"],
        target_type="role",
        allow=["VIEW_CHANNEL", "SEND_MESSAGES"],
        deny=["ADD_REACTIONS"],
    )
    got = call("discord_get_channel", channel_id=priv["id"])
    print("     overwrites:", [(o["type"], o["allow"], o["deny"]) for o in got["permission_overwrites"]])
    call("discord_delete_channel_permission", channel_id=priv["id"], target_id=role["id"])
    call("discord_create_invite", channel_id=general, max_age_seconds=3600, max_uses=1)
    call("discord_edit_role", guild_id=G, role_id=role["id"], name="pulse-moderator", permissions=["MANAGE_MESSAGES"])
    if BOT_ID:
        call("discord_member_role", guild_id=G, user_id=BOT_ID, role_id=role["id"], action="add")
        call("discord_member_role", guild_id=G, user_id=BOT_ID, role_id=role["id"], action="remove")
    call("discord_delete_role", guild_id=G, role_id=role["id"])

    t1 = call("discord_create_thread", channel_id=general, name="from-message", message_id=m1["id"])
    t2 = call("discord_create_thread", channel_id=general, name="standalone")
    call("discord_create_thread", channel_id=general, name="private-thread", private=True)
    call("discord_send_message", channel_id=t1["id"], content="message inside thread")
    call("discord_thread_member", thread_id=t2["id"], action="join")
    call("discord_thread_member", thread_id=t2["id"], action="list")
    call("discord_edit_channel", channel_id=t2["id"], name="standalone-renamed", locked=True)
    call("discord_list_threads", guild_id=G)
    call("discord_edit_channel", channel_id=t2["id"], archived=True)
    call("discord_delete_channel", channel_id=t1["id"])
    expect_fail("discord_moderate_member", guild_id=G, user_id="1", action="unban")
    for cid in made:
        call("discord_delete_channel", channel_id=cid)

bad = [r for r in results if not r[1]]
print(f"\n{len(results) - len(bad)}/{len(results)} passed")
for name, _ in bad:
    print("  failed:", name)
