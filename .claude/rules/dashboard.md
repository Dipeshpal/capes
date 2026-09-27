---
paths:
  - "dashboard/**"
  - "pulse/dashboard.py"
  - "pulse/security.py"
  - "pulse/store.py"
  - "pulse/connectors.py"
  - "pulse/db.py"
  - "pulse/creds.py"
  - "pulse/apikeys.py"
  - "migrations/**"
  - "tests/dashboard.py"
  - "tests/db_offline.py"
---

# Dashboard and authentication rules

The dashboard signs the owner in and can change what assistants may do, so it is the most sensitive code in the repo.

## Server side
- Authentication and session code lives only in `pulse/security.py`. Compare secrets with `secrets.compare_digest` -- compute both sides of a multi-part check unconditionally (no short-circuit `and` between two `compare_digest` calls), so which part was wrong can't leak through timing. Never log or return a key, token, cookie or password value.
- Every state-changing dashboard route must call `security.require_session` and `security.require_csrf`. New routes default to requiring a session.
- The dashboard API returns whether a variable is set, never its value. Do not add fields that echo environment variables, headers or exception text from credentials.
- Only read-only tools may run from the dashboard. Do not add a way to run write or destructive tools from it.
- Settings come from environment variables plus optional Redis, merged so the stricter answer wins. If Redis is configured but unreachable, use the last known settings, and with none fail closed (read-only). Do not fail open.
- Any new connector is registered in `pulse/connectors.py` with a read-only connection test that never raises and never echoes secrets, and reads its token through `creds.get(name)` (checks the database, then falls back to the env var of the same name) rather than `os.getenv` directly -- otherwise a DB-stored credential is silently ignored.
- Dashboard login is `MCP_API_KEY` by default, or a separate `DASHBOARD_USER`/`DASHBOARD_PASSWORD` if both are set (`security.login_mode()`/`dashboard_credentials()`) -- decoupled on purpose, so the API key and the dashboard login are different secrets once someone opts in. The session-signing key (`security._signing_key()`) follows whichever secret is the actual login credential, so rotating it (and only it) invalidates sessions.

## Database (`pulse/db.py`, `pulse/creds.py`, `pulse/apikeys.py`)

Optional (`DATABASE_URL`), bring-your-own Postgres for connector credentials and extra MCP API keys. Required for new deployments since #40, but every deployment from before that keeps working with zero DB: every credential and key lookup falls back to the environment when there is no database, or when it's unreachable.

- `db.fetch`/`fetchrow`/`execute` are the only things that touch the pool; catch both `OSError` (a lazy pool's connection attempt happens on first use, so a refused connection surfaces as a plain `OSError`, not `asyncpg.PostgresError`) and Postgres errors, and re-raise as `db.DatabaseUnavailable`. Never let a raw asyncpg/OSError escape to a route.
- Every route that can hit the database must handle `db.DatabaseUnavailable` explicitly: a write endpoint returns `409`, a read endpoint degrades (empty result + a `degraded: true`/similar flag), never a raw `500`. Distinguish "the input was bad" (e.g. a malformed id) from "the database is unreachable" -- validate the input in Python *before* the query, so a genuine connectivity failure isn't swallowed and misreported as "not found."
- Secrets are AES-256-GCM encrypted (`security.encrypt`/`decrypt`, key from `ENCRYPTION_KEY`) before they ever reach `db.execute`. Never insert plaintext into the `secrets` or `api_keys` tables.
- `api_keys.key_hash` stores a SHA-256 hash, never the key. The plaintext is returned to the caller exactly once, at creation, and is not retrievable again.
- New tables/columns are a new file in `migrations/`, applied automatically by `db._migrate` in id order. Never edit a migration that has shipped; add a new one.
- `ENCRYPTION_KEY` rotation makes existing stored credentials unreadable (it's not like rotating `MCP_API_KEY`). Don't add a casual "rotate" affordance without a loud warning.

## Front end (`dashboard/`)
- Plain HTML, CSS and JavaScript. No build step, no framework, no dependencies, no CDN.
- No inline scripts, no inline event handler attributes, no `style` attributes. The Content-Security-Policy forbids them, and `tests/dashboard.py` checks.
- Insert data as text only (`textContent` through the `h()` helper). Never build markup from data. Do not use dynamic code execution.
- Do not store anything in cookies, `localStorage` or `sessionStorage`. The session cookie is HttpOnly and set by the server.
- Load nothing from other origins: no fonts, images, scripts or analytics.
- Keep it working on a phone-width screen, in light and dark mode, and by keyboard. Check with a real browser before finishing (see `tests/dashboard.py` for the automated part).

## Changing security-relevant behaviour
- Add or update a test in `tests/dashboard.py` in the same change. A security fix without a test that fails without it is incomplete.
- Update `docs/usage/dashboard.md` and the security model in `docs/project/architecture.md` when a defence is added, changed or removed.
- These files are routed to the maintainer by `CODEOWNERS`. Say in the pull request what the change does to the threat model.
