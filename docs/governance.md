# Who can change what

Capes is open to everyone, but only the maintainer decides what goes into the default branch (`main`). This page states the rules, what GitHub enforces, and how you can earn more trust.

## The short version

- **Anyone** can fork the repo, open an issue, and send a pull request.
- **Nobody can push directly** to `main`, not even people with write access.
- **Every change reaches `main` through a pull request** that is approved by a **code owner** and passes all checks (`lint`, `test`, `guard`).
- **Only the maintainer merges.** Contributors never merge their own pull requests.

## Roles

| Role | Who | What they can do |
|------|-----|------------------|
| **Contributor** | Anyone with a GitHub account | Fork, open issues, open pull requests from their fork, comment on and review pull requests. Cannot push to this repo. |
| **Triager** (GitHub "Triage") | Trusted regulars, invited by the maintainer | Label and close issues, request reviews, manage pull request state. Cannot push code. |
| **Collaborator** (GitHub "Write") | Invited after several good merged contributions | Create branches in this repo and open pull requests from them. Still cannot push to or merge into `main`. |
| **Maintainer / code owner** | [@Dipeshpal](https://github.com/Dipeshpal) | Approves and merges pull requests, changes settings, publishes releases. Listed in [`.github/CODEOWNERS`](../.github/CODEOWNERS). |

To become a triager or collaborator, contribute a few useful pull requests and ask in an issue. More maintainers can be added to `CODEOWNERS` later; two maintainers is the healthy target.

## What every pull request must pass

1. **All CI checks are green:** `lint`, `test` and `guard` (see [Contributing](contributing.md#checks)).
2. **The branch is up to date** with `main` before it merges.
3. **One approving review from a code owner.** The approval is dismissed if you push again, and the last push must be approved.
4. **Every review conversation is resolved.**
5. **Squash merge only,** which keeps `main` history linear: one pull request, one commit.

Changes to anything that steers assistants, CI, deployment or authentication (`.claude/`, `.github/`, `scripts/`, `api/`, the security modules, `requirements.txt`, `vercel.json`) also change file hashes pinned by the guard. The maintainer reviews those line by line and re-pins them; a pull request cannot approve its own change. See [The guard](contributing.md#the-guard-for-assistant-and-ci-configuration).

## Pull requests from forks

- **Workflows from first-time contributors need approval.** GitHub holds CI until the maintainer clicks "Approve and run". This stops a stranger's pull request from running arbitrary code with the repo's permissions.
- **CI runs with a read-only token and no secrets.** The workflow declares `contents: read` and never uses `pull_request_target`, so a fork's code cannot write to the repo or read Vercel or service credentials.
- **The guard runs from `main`,** not from the pull request, so a change cannot weaken its own check.

## How the rules are enforced

The rules live in [`.github/rulesets/protect-default-branch.json`](../.github/rulesets/protect-default-branch.json) and are applied to GitHub as a **repository ruleset**. They block deleting `main`, force pushes, merge commits and any merge without an approved review and green checks.

The repository owner has one exception: they can merge their own pull requests without a second reviewer (there is only one maintainer), but only **through a pull request**, never by pushing straight to `main`. Add a second maintainer to `CODEOWNERS` and remove the bypass in the ruleset to require two people.

### Apply the rules (maintainer, once the repository is public)

Rulesets and branch protection need a public repository or a paid plan. Then:

```bash
gh api -X POST repos/OWNER/REPO/rulesets --input .github/rulesets/protect-default-branch.json
```

Then in **Settings** switch on:

| Setting | Where | Value |
|---------|-------|-------|
| Approval for outside contributors' workflows | Actions > General > Fork pull request workflows | **Require approval for all outside collaborators** |
| Workflow token permissions | Actions > General > Workflow permissions | **Read repository contents** only; leave "Allow GitHub Actions to create and approve pull requests" **off** |
| Merge methods | General > Pull Requests | **Squash merging** only; **Automatically delete head branches** on |
| Secret scanning and push protection | Code security | On |
| Private vulnerability reporting | Code security | On (so [SECURITY.md](../SECURITY.md) works) |
| Dependabot alerts and security updates | Code security | On |
| Default branch | General | `main` |

Check it worked: open a pull request from a fork, confirm the merge button is blocked until a code owner approves and the three checks pass, and confirm `git push origin main` is rejected.

## When a rule gets in the way

Rules exist to protect the maintainer's credentials and everyone who deploys this server. If a rule blocks a legitimate change, open an issue that explains why. Do not ask the maintainer to disable a rule for one pull request; change the rule in the open instead.
