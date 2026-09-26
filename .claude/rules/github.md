---
paths:
  - ".github/**"
  - "docs/governance.md"
  - "docs/contributing.md"
  - "SECURITY.md"
---

# GitHub, CI and governance rules

- `main` is protected by the ruleset in `.github/rulesets/protect-default-branch.json`. Apply it with `gh api -X POST repos/OWNER/REPO/rulesets --input .github/rulesets/protect-default-branch.json`. Its required check names (`lint`, `test`, `guard`) must equal the job names in `.github/workflows/ci.yml`; renaming a job silently breaks the rule.
- The ruleset, `CODEOWNERS`, workflows and Dependabot config are hash-pinned by the guard. A change to any of them needs maintainer review and `python scripts/check_claude_config.py --update`; a PR never approves its own change (CI runs the base branch's guard).
- Workflows use `permissions: contents: read`, no secrets, and never `pull_request_target`. Actions are pinned to major versions the guard has seen.
- Keep `docs/governance.md` and the ruleset in sync: roles, required checks, squash-only, code-owner review, the owner's PR-only bypass.
- Repository settings that are not in the ruleset are listed in `docs/governance.md` (fork-PR approval for all outside contributors, read-only workflow token, secret scanning with push protection, private vulnerability reporting, Dependabot). Apply them with `gh api` after a visibility change.
