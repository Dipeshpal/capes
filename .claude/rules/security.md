# Security rules (always on)

- Never write a real token, key, app password, chat/server ID belonging to a person, or email address into any tracked file, test, doc, commit message or example. Use placeholders (`YOUR_API_KEY`, `you@gmail.com`).
- Never read or print `.env*`, `.pulse.local.json` or Vercel env values into the conversation. To check that a variable exists, use `vercel env ls production` (values are hidden).
- Tool error messages must not echo secrets. Report the upstream service's message and status code only.
- Do not put tokens in URLs or query strings when a header works (Apify and Discord calls use `Authorization` headers).
- Compare secrets with `secrets.compare_digest`, never `==`.
- Anything that sends, deletes or changes data outside the user's own machine must be a `write` or `destructive` tool with an accurate `hint`.
- If a secret reaches git history: stop, rotate the secret, then delete and recreate the GitHub repository (GitHub keeps orphaned commits reachable by SHA). Run `/security-audit` afterwards.
- Tests that need real credentials must read them from environment variables and default to read-only behaviour.
