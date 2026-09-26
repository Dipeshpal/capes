---
paths:
  - "scripts/**"
---

# Installer (`scripts/capes.mjs`) rules

- Zero dependencies, Node 18+, ES modules. Only `node:` built-ins.
- It must work on Windows, macOS and Linux. On Windows child processes run with `shell: true`, which does not escape arguments: quote any argument containing spaces with the `q()` helper.
- Never print secrets except the generated `MCP_API_KEY` once at install time, and store URL and key only in `.capes.local.json` (git-ignored).
- Client config files are merged, never overwritten: read JSON (strip a BOM), change only the `capes` entry, write it back. Claude Desktop uses the `mcp-remote` bridge with the key in `env`, referenced as `${AUTH_HEADER}`, because `args` containing a space break on Windows.
- Every flag must have a non-interactive equivalent so the script can run in CI (`--name --discord --apify --gmail --gmail-password --url --key --clients`).
- Test client wiring without touching real config: run `connect` with `--desktop-config <temp file>` and a temporary `USERPROFILE`/`HOME`.
- Run `node --check scripts/capes.mjs` after every edit.
