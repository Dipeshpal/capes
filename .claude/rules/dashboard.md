---
paths:
  - "dashboard/**"
  - "pulse/dashboard.py"
  - "pulse/security.py"
  - "pulse/store.py"
  - "pulse/connectors.py"
  - "tests/dashboard.py"
---

# Dashboard and authentication rules

The dashboard signs the owner in and can change what assistants may do, so it is the most sensitive code in the repo.

## Server side
- Authentication and session code lives only in `pulse/security.py`. Compare secrets with `secrets.compare_digest`. Never log or return a key, token or cookie value.
- Every state-changing dashboard route must call `security.require_session` and `security.require_csrf`. New routes default to requiring a session.
- The dashboard API returns whether a variable is set, never its value. Do not add fields that echo environment variables, headers or exception text from credentials.
- Only read-only tools may run from the dashboard. Do not add a way to run write or destructive tools from it.
- The activity log stores tool name, time, source, outcome and duration only. Never arguments or results.
- Settings come from environment variables plus optional Redis, merged so the stricter answer wins. If Redis is configured but unreachable, use the last known settings, and with none fail closed (read-only). Do not fail open.
- Any new connector is registered in `pulse/connectors.py` with a read-only connection test that never raises and never echoes secrets.

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
