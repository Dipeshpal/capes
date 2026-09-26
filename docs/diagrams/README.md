# Diagrams

| Diagram | Shows | PNG | Interactive |
|---------|-------|-----|-------------|
| Architecture | How clients, the dashboard, the guard, the tools and the three services connect | [architecture.png](architecture.png) | [architecture.html](architecture.html) |
| Life of a tool call | What happens between an assistant's request and its answer | [request-lifecycle.png](request-lifecycle.png) | [request-lifecycle.html](request-lifecycle.html) |
| How a change reaches main | Fork, pull request, checks, review, squash merge | [contribution-flow.png](contribution-flow.png) | [contribution-flow.html](contribution-flow.html) |

The `.html` files are self-contained: download one and open it in a browser to pan, zoom, search and trace paths. GitHub shows the source of an HTML file rather than running it, so the PNGs are what the docs embed.

## Editing a diagram

The sources are small JSON files in [`src/`](src). They are written for the Archify diagram skill (a Claude Code skill; `node bin/archify.mjs` is its command line). Edit the JSON, then validate and render.

```bash
node bin/archify.mjs validate architecture docs/diagrams/src/architecture.json --quality showcase
node bin/archify.mjs deliver architecture docs/diagrams/src/architecture.json docs/diagrams/architecture.html --quality showcase
node bin/archify.mjs visual-check docs/diagrams/architecture.html
```

The PNG is a crop of the light-theme browser capture that `visual-check` writes. Keep the diagrams truthful: when the tool count, a connector or the merge rules change, update the JSON, regenerate, and replace the PNG.
