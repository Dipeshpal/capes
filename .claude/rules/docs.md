---
paths:
  - "README.md"
  - "docs/**"
  - "CLAUDE.md"
---

# Documentation rules

- `README.md` is the front door: setup steps, a services table linking to `docs/`, connect instructions, tool list, contributing. Per-service detail (where to click, permissions, limits) lives in `docs/setup/<service>.md`.
- Adding a service means: a new `docs/setup/<service>.md`, a row in the README services table, its env vars in `.env.example`, the installer prompt, and a line in `docs/usage/troubleshooting.md`.
- Instructions must be verifiable steps a stranger can follow: exact menu names, exact URLs, exact commands. State what they should see when it worked.
- Use placeholders for secrets and IDs (`YOUR_API_KEY`, `CLIENT_ID`). Never paste real values.
- Relative links only between repo docs. After editing, run `python tests/check_docs.py` (checks that every relative link and `#anchor` resolves).
- `docs/usage/tools.md` is generated: run `python scripts/gen_tools_doc.py` after any tool change and never edit it by hand.
- Keep the tool list in README exactly equal to what `tools/list` returns; `tests/protocol.py` compares them.
- Plain, direct prose. No emojis, no marketing language, no claims that were not tested.

- Docs layout: `docs/setup/` (getting a service or client working), `docs/usage/` (using and troubleshooting), `docs/project/` (architecture, contributing, governance, release), `docs/diagrams/`, `docs/assets/`. Add every new page to `docs/README.md` and, if it is a guide, to the README's "All guides" list. Link with relative paths; `tests/check_docs.py` fails on a broken link or anchor.
- Diagrams live in `docs/diagrams/src/*.json` (Archify). When a diagram's facts change (tool count, a connector, the merge rules), edit the JSON, regenerate, and replace the PNG. Do not hand-edit the delivered HTML.
