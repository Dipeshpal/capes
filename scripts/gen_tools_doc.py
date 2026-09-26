"""Generates docs/usage/tools.md from the tool registry so the reference can never drift from the code.

    python scripts/gen_tools_doc.py           # rewrite docs/usage/tools.md
    python scripts/gen_tools_doc.py --check   # exit 1 if docs/usage/tools.md is out of date (used by tests and CI)

Needs only aiohttp (the tool modules import it).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pulse import discord, gmail, twitter  # noqa: E402,F401  (importing registers the tools)
from pulse.registry import TOOLS  # noqa: E402

TARGET = ROOT / "docs" / "usage" / "tools.md"
SERVICES = [
    ("gmail", "Gmail", "Needs `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD`. Setup: [Gmail guide](../setup/gmail.md)."),
    ("discord", "Discord", "Needs `DISCORD_BOT_TOKEN` and a bot invited with the right permissions. Setup: [Discord guide](../setup/discord.md)."),
    ("twitter", "X/Twitter", "Needs `APIFY_TOKEN`. Setup: [Apify guide](../setup/apify.md)."),
]


def kind(spec: dict) -> str:
    a = spec["annotations"]
    return "read" if a.get("readOnlyHint") else ("destructive" if a.get("destructiveHint") else "write")


def render() -> str:
    lines = [
        "# Tool reference",
        "",
        "Generated from the code by `python scripts/gen_tools_doc.py`. Do not edit by hand; change the tool's description or schema in `pulse/` and regenerate.",
        "",
        "**Kind** tells clients how careful to be: `read` has no side effects, `write` creates or changes things (sending mail or messages cannot be undone), `destructive` deletes or is hard to reverse, so clients should ask first. An asterisk marks a required argument.",
        "",
    ]
    total = 0
    for prefix, title, note in SERVICES:
        specs = [t["spec"] for t in TOOLS.values() if t["spec"]["name"].startswith(prefix + "_")]
        total += len(specs)
        lines += [f"## {title}", "", note, "", "| Tool | Kind | What it does | Arguments |", "|------|------|--------------|-----------|"]
        for s in specs:
            req = set(s["inputSchema"]["required"])
            args = ", ".join(f"`{k}{'*' if k in req else ''}`" for k in s["inputSchema"]["properties"]) or "none"
            desc = s["description"].replace("|", "\\|").replace("\n", " ")
            lines.append(f"| `{s['name']}` | {kind(s)} | {desc} | {args} |")
        lines.append("")
    lines.insert(2, f"{total} tools.")
    lines.insert(3, "")
    return "\n".join(lines).rstrip() + "\n"


if __name__ == "__main__":
    text = render()
    if "--check" in sys.argv:
        current = TARGET.read_text(encoding="utf-8").replace("\r\n", "\n") if TARGET.exists() else ""
        if current != text:
            print("docs/usage/tools.md is out of date. Run: python scripts/gen_tools_doc.py")
            sys.exit(1)
        print("docs/usage/tools.md is up to date")
    else:
        TARGET.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {TARGET.relative_to(ROOT)} ({text.count(chr(10))} lines)")
