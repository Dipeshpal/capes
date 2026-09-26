---
description: Add a new MCP tool, or a whole new service integration, to Capes following the project conventions
argument-hint: <service> <tool_name> (for example: slack slack_send_message)
disable-model-invocation: true
---

Add the tool described by `$ARGUMENTS` to this repository.

1. Read `.claude/rules/tools.md` and the module closest to the new service (`pulse/discord.py` for REST APIs, `pulse/gmail.py` for blocking libraries).
2. If the service is new, create `pulse/<service>.py` from `${CLAUDE_SKILL_DIR}/template.py.txt` and import it in `api/index.py`. If it exists, add the function to its module.
3. Pick the honest `hint` (`read`, `write`, `destructive`). Write a description a language model can act on, with argument descriptions and enums.
4. Read secrets with `os.getenv` inside the function. Raise `ToolError` with a fix-it message when a token or permission is missing.
5. Add the env vars to `.env.example`, and to the installer prompts in `scripts/capes.mjs` if the service needs credentials.
6. Add tests: offline where possible (see `tests/gmail_offline.py`, which fakes the remote server), otherwise an opt-in end-to-end script that never runs against real user data by default.
7. Documentation: run `python scripts/gen_tools_doc.py` to regenerate `docs/usage/tools.md` (never hand-edit it), then `docs/setup/<service>.md` (how to get the credentials and permissions), a row in the README services table, the tool names in the README tool list, and a line in `docs/usage/troubleshooting.md`.
8. Verify: run `/run-tests`, then `python tests/check_docs.py`, then confirm `tools/list` contains the new tool.
9. Report what you added, what you tested, and anything you could not test.

Do not put real credentials, IDs or personal data anywhere in the repository.
