---
paths:
  - "README.md"
  - "docs/**"
  - "CLAUDE.md"
---

# Documentation rules

- `README.md` is the front door: setup steps, a services table linking to `docs/`, connect instructions, tool list, contributing. Per-service detail (where to click, permissions, limits) lives in `docs/<service>.md`.
- Adding a service means: a new `docs/<service>.md`, a row in the README services table, its env vars in `.env.example`, the installer prompt, and a line in `docs/troubleshooting.md`.
- Instructions must be verifiable steps a stranger can follow: exact menu names, exact URLs, exact commands. State what they should see when it worked.
- Use placeholders for secrets and IDs (`YOUR_API_KEY`, `CLIENT_ID`). Never paste real values.
- Relative links only between repo docs. After editing, run `python tests/check_docs.py` (checks that every relative link and `#anchor` resolves).
- Keep the tool list in README exactly equal to what `tools/list` returns; `tests/protocol.py` compares them.
- Plain, direct prose. No emojis, no marketing language, no claims that were not tested.
