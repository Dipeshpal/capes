# Capes documentation

Start with the [main README](../README.md) for what Capes is and how to deploy it. Everything else is here, grouped by what you are trying to do.

## Set it up (`setup/`)

| Guide | Use it to |
|-------|-----------|
| [Vercel](setup/vercel.md) | Deploy your server, create your `MCP_API_KEY`, restrict what assistants can do |
| [Discord](setup/discord.md) | Create the bot and invite it with the right permissions |
| [Gmail](setup/gmail.md) | Create an app password and connect your mailbox |
| [Apify](setup/apify.md) | Get the token for X/Twitter search |
| [Connect your client](setup/clients.md) | Add the server to Claude Desktop, Claude Code, Cursor, Codex or any MCP client |

## Use it (`usage/`)

| Guide | Use it to |
|-------|-----------|
| [Using Capes](usage/usage.md) | Ideas, prompts and safety habits |
| [Dashboard](usage/dashboard.md) | Test connections, switch tools off, watch activity |
| [Tool reference](usage/tools.md) | Every tool with its kind and arguments (generated, do not edit) |
| [Troubleshooting](usage/troubleshooting.md) | Match an error message to its fix |

## Understand it and contribute (`project/`)

| Page | Read it to |
|------|-----------|
| [What Capes is for](project/architecture.md) | See the goals, the design, the security model and the comparison with alternatives |
| [Contributing](project/contributing.md) | Set up, run the checks, add a tool or a service |
| [Governance](project/governance.md) | Learn who can merge what, and why nobody pushes to `main` directly |
| [Release checklist](project/release-checklist.md) | Check what must be true before a release |

## Diagrams and images

- [`diagrams/`](diagrams/README.md): the architecture, tool-call and contribution diagrams, as PNG for reading and interactive HTML for exploring.
- `assets/`: the logo, the social preview image and dashboard screenshots.

Security reports go through [SECURITY.md](../SECURITY.md), not public issues.
