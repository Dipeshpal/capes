"""Guards the files that steer AI assistants and CI against malicious or careless pull requests.

    python scripts/check_claude_config.py            # check the repo; exit 1 on any violation
    python scripts/check_claude_config.py --update   # re-pin file hashes after a reviewed change

Why: `.claude/`, `CLAUDE.md`, workflows, `vercel.json` and `requirements.txt` decide what an assistant may run, what CI
executes and what ships. A hook, a wildcard permission, a hidden instruction or a new dependency in a pull request would
run on every contributor's machine or in production. Anything this script blocks needs a maintainer to change the script
itself (which CODEOWNERS routes to the maintainer) after review. Standard library only.
"""

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else Path(__file__).resolve().parent.parent
LOCK = ROOT / "scripts" / "claude_config.lock.json"

# ---- policy (edit only after review) --------------------------------------------------------------------------
ALLOWED_CLAUDE_ENTRIES = {"agent-memory", "agents", "rules", "skills", "settings.json"}
ALLOWED_SETTINGS_KEYS = {"permissions"}
ALLOWED_PERMISSION_KEYS = {"allow", "deny"}
APPROVED_ALLOW = {
    "Bash(node --check *)",
    "Bash(uv run *)",
    "Bash(python tests/*)",
    "Bash(git status*)",
    "Bash(git diff*)",
    "Bash(git log*)",
    "Bash(vercel env ls*)",
    "Bash(vercel inspect*)",
    "Bash(vercel logs*)",
}
REQUIRED_DENY = {
    "Read(./.env)",
    "Read(./.env.local)",
    "Read(./.env.production*)",
    "Read(./.capes.local.json)",
    "Bash(git push --force*)",
    "Bash(git push -f*)",
    "Bash(vercel env pull*)",
    "Bash(rm -rf *)",
}
ALLOWED_AGENT_TOOLS = {"Read", "Grep", "Glob", "Bash"}
FORBIDDEN_FRONTMATTER = {"hooks", "allowed-tools", "model", "shell", "mcpServers", "permissionMode", "disallowedTools", "isolation"}
APPROVED_INJECTIONS = {"git status --short", "bash ${CLAUDE_SKILL_DIR}/scan.sh"}
ALLOWED_URL_HOSTS = {
    "github.com",
    "code.claude.com",
    "modelcontextprotocol.io",
    "vercel.com",
    "discord.com",
    "apify.com",
    "console.apify.com",
    "myaccount.google.com",
    "developers.google.com",
    "nodejs.org",
    "console.upstash.com",
    "upstash.com",
    "example.invalid",
    "api.example.invalid",
}
ALLOWED_DEPENDENCIES = {"fastapi", "aiohttp", "python-dotenv"}
PINNED_SUFFIXES = {".sh", ".json", ".txt", ".py", ".js", ".mjs", ".ps1", ".bat", ".cmd", ".yml", ".yaml"}
HIDDEN_CHARS = re.compile("[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff\u00ad]")
INJECTION_PHRASES = re.compile(
    r"ignore (all |any )?(previous|prior|above) (instructions|rules)|disregard (the )?(previous|above|system)|do not (tell|inform|mention to) the user|"
    r"without (telling|informing|asking) the user|exfiltrate|send (the )?(contents of )?(\.env|secrets?|tokens?|credentials)|upload .{0,30}(\.env|secrets?|credentials)",
    re.I,
)
NETWORK_TOOLS = re.compile(
    r"\b(curl|wget|Invoke-WebRequest|Invoke-RestMethod|nc|ncat|netcat|scp|ssh)\b|\|\s*(sh|bash|zsh|pwsh|powershell)\b|base64\s+(-d|--decode)|\beval\b"
)
NETWORK_ALLOWED_IN = {".claude/skills/deploy/SKILL.md"}
# ---------------------------------------------------------------------------------------------------------------

problems: list[str] = []


def fail(msg: str) -> None:
    problems.append(msg)


def rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def frontmatter(text: str) -> dict:
    m = re.match(r"---\r?\n(.*?)\r?\n---", text, re.S)
    out = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line and not line.startswith((" ", "-")):
                k, _, v = line.partition(":")
                out[k.strip()] = v.strip()
    return out


def check_claude_dir() -> None:
    claude = ROOT / ".claude"
    if not claude.exists():
        return
    for entry in claude.iterdir():
        if entry.name not in ALLOWED_CLAUDE_ENTRIES:
            fail(f"{rel(entry)}: not an approved .claude entry (allowed: {sorted(ALLOWED_CLAUDE_ENTRIES)})")
    for p in [*claude.rglob("*"), ROOT / "CLAUDE.md"]:
        if p.is_symlink():
            fail(f"{rel(p)}: symlinks are not allowed in assistant configuration")
    if (ROOT / ".mcp.json").exists():
        fail(".mcp.json: project MCP servers auto-start for every contributor; not allowed")
    if (claude / "settings.local.json").exists() and _tracked(".claude/settings.local.json"):
        fail(".claude/settings.local.json must never be committed")

    settings = claude / "settings.json"
    if settings.exists():
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
        except ValueError:
            fail(".claude/settings.json is not valid JSON")
            data = {}
        for key in set(data) - ALLOWED_SETTINGS_KEYS:
            fail(f".claude/settings.json: '{key}' is not allowed (hooks, env, MCP servers, model overrides and helpers run code or change behaviour)")
        perms = data.get("permissions", {})
        for key in set(perms) - ALLOWED_PERMISSION_KEYS:
            fail(f".claude/settings.json: permissions.{key} is not allowed")
        for rule in perms.get("allow", []):
            if rule not in APPROVED_ALLOW:
                fail(f".claude/settings.json: allow rule {rule!r} is not on the approved list in scripts/check_claude_config.py")
        missing = REQUIRED_DENY - set(perms.get("deny", []))
        if missing:
            fail(f".claude/settings.json: required deny rules were removed: {sorted(missing)}")


def check_markdown() -> None:
    files = [ROOT / "CLAUDE.md", *sorted((ROOT / ".claude").rglob("*.md")), *sorted((ROOT / ".claude").rglob("*.txt"))]
    for p in files:
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        name = rel(p)
        if HIDDEN_CHARS.search(text):
            fail(f"{name}: contains invisible or bidirectional Unicode characters (a known way to hide instructions)")
        if "<!--" in text:
            fail(f"{name}: HTML comments are invisible when rendered and can hide instructions; remove them")
        if INJECTION_PHRASES.search(text):
            fail(f"{name}: contains prompt-injection style wording")
        for m in re.finditer(r"!`([^`]+)`", text):
            if m.group(1) not in APPROVED_INJECTIONS:
                fail(f"{name}: shell injection !`{m.group(1)}` is not on the approved list")
        if name not in NETWORK_ALLOWED_IN and NETWORK_TOOLS.search(re.sub(r"```.*?```", "", text, flags=re.S)):
            fail(f"{name}: mentions network or remote-execution commands outside an approved file")
        for host in re.findall(r"https?://([A-Za-z0-9.\-]+)", text):
            if host.lower() not in ALLOWED_URL_HOSTS:
                fail(f"{name}: link to unapproved host {host}")
        fm = frontmatter(text)
        for key in set(fm) & FORBIDDEN_FRONTMATTER:
            fail(f"{name}: frontmatter key '{key}' is not allowed")
        if "/agents/" in name and name.endswith(".md"):
            tools = {t.strip() for t in fm.get("tools", "").split(",") if t.strip()}
            if not tools:
                fail(f"{name}: an agent must list its tools explicitly")
            elif not tools <= ALLOWED_AGENT_TOOLS:
                fail(f"{name}: agent tools {sorted(tools - ALLOWED_AGENT_TOOLS)} are not allowed (approved: {sorted(ALLOWED_AGENT_TOOLS)})")


SOURCE_SUFFIXES = {".py", ".js", ".mjs", ".sh", ".yml", ".yaml", ".json", ".md", ".html", ".css", ".toml", ".txt"}
SOURCE_NAMES = {"CODEOWNERS", ".gitignore", ".vercelignore", ".gitattributes", ".env.example"}
SKIP_DIRS = {".git", ".vercel", "node_modules", "__pycache__", ".ruff_cache", ".venv", ".playwright-mcp"}


def check_source_files() -> None:
    """Invisible or bidirectional characters in any source file can hide code from reviewers ("Trojan Source")."""
    for p in sorted(ROOT.rglob("*")):
        if not p.is_file() or set(p.relative_to(ROOT).parts) & SKIP_DIRS:
            continue
        if p.suffix not in SOURCE_SUFFIXES and p.name not in SOURCE_NAMES:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            fail(f"{rel(p)}: not valid UTF-8 text")
            continue
        if HIDDEN_CHARS.search(text):
            fail(f"{rel(p)}: contains invisible or bidirectional characters; write them as escape sequences instead (Trojan Source)")


def pin_targets() -> list[Path]:
    targets = []
    for base in (ROOT / ".claude", ROOT / ".github"):
        if base.exists():
            targets += [p for p in base.rglob("*") if p.is_file() and p.suffix in PINNED_SUFFIXES]
    return sorted(targets)


def digest(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def check_pins() -> None:
    current = {rel(p): digest(p) for p in pin_targets()}
    pinned = json.loads(LOCK.read_text(encoding="utf-8")) if LOCK.exists() else {}
    for name, h in current.items():
        if name not in pinned:
            fail(f"{name}: new executable/config file is not pinned. A maintainer must review it, then run: python scripts/check_claude_config.py --update")
        elif pinned[name] != h:
            fail(f"{name}: changed since it was reviewed and pinned. A maintainer must review it, then run: python scripts/check_claude_config.py --update")
    for name in set(pinned) - set(current):
        fail(f"{name}: pinned file was removed. Re-pin with --update after review")


def check_workflows() -> None:
    for p in sorted((ROOT / ".github" / "workflows").glob("*.y*ml")) if (ROOT / ".github" / "workflows").exists() else []:
        text = p.read_text(encoding="utf-8")
        name = rel(p)
        if re.search(r"pull_request_target|workflow_run", text):
            fail(f"{name}: pull_request_target/workflow_run give untrusted pull requests access to secrets and write tokens")
        if not re.search(r"^permissions:\s*\n\s+contents:\s*read\s*$", text, re.M):
            fail(f"{name}: must declare top-level `permissions: contents: read`")
        if re.search(r"permissions:\s*write-all|(contents|actions|packages|id-token):\s*write", text):
            fail(f"{name}: write permissions are not allowed")
        if re.search(r"secrets\.(?!GITHUB_TOKEN)", text):
            fail(f"{name}: workflows must not use repository secrets")
        for m in re.finditer(r"run:.*\$\{\{\s*github\.(event|head_ref)[^}]*\}\}", text):
            fail(f"{name}: untrusted event data interpolated into a shell command: {m.group(0)[:80]}")
        for m in re.finditer(r"uses:\s*([^\s@]+)@(\S+)", text):
            if not m.group(1).startswith(("actions/", "./")):
                fail(f"{name}: third-party action {m.group(1)} is not allowed without review")


def check_supply_chain() -> None:
    req = ROOT / "requirements.txt"
    if req.exists():
        for line in req.read_text(encoding="utf-8").splitlines():
            line = line.split("#")[0].strip()
            if line and re.split(r"[<>=!~\[ ]", line)[0].lower() not in ALLOWED_DEPENDENCIES:
                fail(f"requirements.txt: dependency '{line}' is not approved")
    vercel = ROOT / "vercel.json"
    if vercel.exists():
        extra = set(json.loads(vercel.read_text(encoding="utf-8"))) - {"functions"}
        if extra:
            fail(f"vercel.json: {sorted(extra)} not allowed (rewrites/redirects/headers can change what is served)")
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8") if (ROOT / ".gitignore").exists() else ""
    for entry in (".env", ".capes.local.json", ".claude/settings.local.json"):
        if entry not in ignore:
            fail(f".gitignore must contain {entry}")


def _tracked(path: str) -> bool:
    import subprocess

    r = subprocess.run(["git", "ls-files", "--error-unmatch", path], cwd=ROOT, capture_output=True, text=True, check=False)
    return r.returncode == 0


def main() -> int:
    if "--update" in sys.argv:
        LOCK.write_text(json.dumps({rel(p): digest(p) for p in pin_targets()}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"pinned {len(pin_targets())} files in {rel(LOCK)}")
        return 0
    check_claude_dir()
    check_markdown()
    check_source_files()
    check_workflows()
    check_supply_chain()
    check_pins()
    for p in problems:
        print("FAIL", p)
    print(f"assistant/CI configuration guard: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
