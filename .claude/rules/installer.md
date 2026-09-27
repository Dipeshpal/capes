---
paths:
  - "scripts/**"
---

# Installer (`scripts/capes.mjs`) rules

- Zero dependencies, Node 18+, ES modules. Only `node:` built-ins.
- It must work on Windows, macOS and Linux. On Windows child processes run with `shell: true`, which does not escape arguments: quote any argument containing spaces with the `q()` helper.
- Never print secrets except the ones generated once, at install time (`MCP_API_KEY`, and `ENCRYPTION_KEY` when a database is set up), and store URL, key and encryption key only in `.capes.local.json` (git-ignored). `DASHBOARD_PASSWORD` is user-supplied, not generated -- never echo it back.
- Client config files are merged, never overwritten: read JSON (strip a BOM), change only the `capes` entry, write it back. Claude Desktop uses the `mcp-remote` bridge with the key in `env`, referenced as `${AUTH_HEADER}`, because `args` containing a space break on Windows.
- Every flag must have a non-interactive equivalent so the script can run in CI (`--name --database --encryption-key --dashboard-user --dashboard-password --discord --apify --gmail --gmail-password --telegram --url --key --clients`).
- The `update` command (pull upstream changes into a fork, redeploy) shells out to `git` directly -- keep its error paths informative (a merge conflict must name the files and say how to resolve or back out, never just fail silently) since it runs against a contributor's own local git state, which this repo's tests can't simulate.
- Test client wiring without touching real config: run `connect` with `--desktop-config <temp file>` and a temporary `USERPROFILE`/`HOME`.
- Run `node --check scripts/capes.mjs` after every edit.
