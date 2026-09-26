# Release checklist

Use this before making the repository public, and before tagging a release. Each item says how to check it.

## Before going public

- [x] **License:** MIT (`LICENSE`), chosen 2026-09-27.
- [ ] **Rotate every credential that ever touched a private repo or old deployment** (Discord bot token, Apify token, Gmail app password if used in tests, `MCP_API_KEY`), then update Vercel and redeploy.
- [ ] **Delete old repositories that held leaked history** (`gh repo delete <owner>/<name>`). GitHub keeps orphaned commits reachable by SHA, so a repo that ever contained a secret must be deleted, not just rewritten.
- [ ] **Full-history secret scan is clean:** `bash .claude/skills/security-audit/scan.sh --strict` with your real values exported in the shell (it prints counts only).
- [ ] **Turn on GitHub protections** for the default branch: require a pull request, require review from Code Owners (`.github/CODEOWNERS`), require the CI checks (`lint`, `test`, `guard`), block force pushes. Private repositories need a paid plan for branch protection; public ones get it free.
- [ ] **Enable GitHub secret scanning and push protection** (Settings > Code security).
- [ ] **Enable private vulnerability reporting** (Settings > Code security) so [SECURITY.md](../SECURITY.md) works.
- [ ] **Discord bot is private** (Developer Portal > Bot > Public Bot off) and its permissions are what you want.
- [ ] **Vercel Deployment Protection** and the dashboard sign-in work on the production address ([guide](vercel.md#deployment-protection)).
- [ ] **Docs read cleanly** from a stranger's point of view: follow the README on a fresh Vercel account and note every place you hesitated.
- [ ] **The Deploy button URL points at the public repository** and creates a working project.

## Every release

- [ ] All checks pass locally and in CI: protocol, dashboard, Gmail offline, assistant-configuration guard, docs links, generated tool reference, lint and format.
- [ ] `python scripts/gen_tools_doc.py` was run and `docs/tools.md` is committed; the README tool count matches.
- [ ] After any change to `.claude/` or `.github/` scripts, a maintainer reviewed the diff and re-pinned with `python scripts/check_claude_config.py --update`.
- [ ] Deployed with `vercel deploy --prod` and smoke-tested: `/health`, dashboard sign-in, `tools/list`, one read call per connector.
- [ ] `pip-audit` (or Dependabot) shows no known vulnerabilities in `requirements.txt`.
- [ ] Restarted the AI clients to refresh their tool lists.

## Known gaps to accept or close

- Discord write tools are verified against a fake Discord REST server (`tests/discord_offline.py`: exact endpoint, method, payload and headers) and live read-only calls, but never against a real server that they can change; run `tests/discord_e2e.py MODE=full` on a disposable server before advertising them as verified.
- Redis-backed features are tested against a fake server and locally; test them on a real Upstash database after adding the integration.
- There are no per-client keys; anyone with `MCP_API_KEY` has full access to the connected services.
