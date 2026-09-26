# Security policy

pulse-mcp holds real credentials for your email, Discord bot and Apify account, so security reports are taken seriously.

## Reporting a vulnerability

Do not open a public issue. Report privately through GitHub: **Security > Report a vulnerability** on this repository. Include what you found, how to reproduce it, and what an attacker could do. Never include real tokens, keys or message content.

You can expect an acknowledgement within a few days. Please give the maintainer reasonable time to fix the issue before sharing details.

## What is in scope

- Bypassing the `MCP_API_KEY` check on `/mcp` or the dashboard login.
- Session, cookie or CSRF weaknesses in the dashboard.
- Reading secrets through the dashboard, tool results, error messages or logs.
- Calling tools that the owner disabled, or writing while read-only mode is on.
- Injection through tool arguments (for example a value that changes which Discord or IMAP command runs).
- Anything in `.claude/`, workflows, `vercel.json` or dependencies that lets a contributor run code or change behaviour without maintainer review.

## How the project protects itself

- One secret guards the server: a key of at least 24 characters, checked in constant time. The dashboard uses a signed, HttpOnly, SameSite=Strict session cookie and a per-session CSRF token. See [docs/architecture.md](docs/architecture.md#security-model) and [docs/dashboard.md](docs/dashboard.md).
- Tool arguments are validated against each tool's schema before any call, and IDs must match a strict pattern.
- Every push and pull request runs a secret scan over the whole history and a guard (`scripts/check_claude_config.py`) that blocks hooks, wildcard permissions, hidden text, unapproved dependencies and risky workflows. Files that can execute code under `.claude/` and `.github/` are hash-pinned, so any change needs a maintainer to review it and re-pin.
- `CODEOWNERS` routes security-sensitive paths to the maintainer.

## If you suspect a secret leaked

Rotate it at the provider first (Discord: Reset Token; Apify: regenerate; Google: delete the app password; `MCP_API_KEY`: set a new value on Vercel and redeploy). If it reached git history, deleting it is not enough: GitHub keeps orphaned commits reachable by SHA, so recreate the repository. The `/security-audit` skill scans history for leaks.
