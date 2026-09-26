#!/usr/bin/env bash
# Scans every commit for secrets. Prints locations and counts, never secret values.
# Usage: scan.sh [--strict]   (--strict exits 1 when anything suspicious is found; used by CI)
set -u
cd "$(git rev-parse --show-toplevel)" || exit 1
revs=$(git rev-list --all)
bad=0
echo "commits scanned: $(echo "$revs" | grep -c .)"

echo
echo "== files ever tracked"
git log --all --name-only --pretty=format: | sort -u | grep -v '^$'

echo
echo "== risky file names in history (expect none)"
risky=$(git log --all --name-only --pretty=format: | sort -u \
  | grep -E '(^|/)\.env($|\.)|\.local\.json$|\.pem$|\.key$|id_rsa' | grep -v '\.env\.example$' || true)
if [ -n "$risky" ]; then echo "$risky"; bad=1; else echo "none"; fi

echo
echo "== secret patterns in history (file locations only)"
PATTERN='[MNO][A-Za-z0-9_-]{23,25}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}|apify_api_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9]{32,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY|xox[baprs]-[A-Za-z0-9-]{10,}'
# shellcheck disable=SC2086
hits=$(git grep -I -l -E "$PATTERN" $revs 2>/dev/null | sort -u | head -20 || true)
if [ -n "$hits" ]; then echo "$hits"; bad=1; else echo "none"; fi

echo
echo "== long values assigned to *_KEY/*_TOKEN/*_SECRET/*_PASSWORD (locations only, .example excluded)"
# shellcheck disable=SC2086
hits=$(git grep -I -l -E '(KEY|TOKEN|SECRET|PASSWORD)[A-Z_]*[[:space:]]*[=:][[:space:]]*["'"'"']?[A-Za-z0-9_-]{24,}' $revs -- . ':!*.example' 2>/dev/null | sort -u | head -20 || true)
if [ -n "$hits" ]; then echo "$hits"; bad=1; else echo "none"; fi

echo
echo "== known secrets from the current environment (counts only)"
for var in MCP_API_KEY DISCORD_BOT_TOKEN APIFY_TOKEN GMAIL_APP_PASSWORD; do
  val="${!var:-}"
  if [ -n "$val" ]; then
    # shellcheck disable=SC2086
    n=$(git grep -I -l -F -e "$val" $revs 2>/dev/null | wc -l | tr -d ' ')
    echo "$var: $n file(s) contain it"
    [ "$n" != "0" ] && bad=1
  else
    echo "$var: not set in this shell (export it to include it in the audit)"
  fi
done

echo
echo "== working tree"
git status --short | head -20
[ -z "$(git status --short)" ] && echo "clean"

if [ "${1:-}" = "--strict" ] && [ "$bad" -ne 0 ]; then
  echo
  echo "STRICT: suspicious findings above"
  exit 1
fi
exit 0
