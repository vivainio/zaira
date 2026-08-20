---
icon: lucide/ticket
hide:
  - toc
---

# Zaira

> **Pronunciation:** *ZAY-rah* /ˈzeɪ.rə/ — named after Jira (*JEE-rah* /ˈdʒiː.rə/), though it works with Confluence too.

A CLI tool for Jira and Confluence management. Export tickets to markdown,
generate reports, and keep everything in sync — designed so AI agents and
coding assistants can read project context as plain files instead of calling
the Jira API directly.

<div class="guide-grid" markdown>

[:lucide-download: **Install it**  
`uv tool install zaira`, then `zaira init` to store your Jira credentials.](https://github.com/vivainio/zaira#installation)

[:lucide-file-down: **Export tickets**  
Pull tickets to markdown by key, JQL, board, or sprint with `zaira get`.](https://github.com/vivainio/zaira#get)

[:lucide-upload: **Round-trip changes**  
Edit exported markdown and push it back with `zaira put`, `zaira edit`, or `zaira comment`.](https://github.com/vivainio/zaira#put)

[:lucide-bar-chart-3: **Generate reports**  
Turn JQL or named queries into grouped markdown, JSON, or CSV reports.](https://github.com/vivainio/zaira#report)

[:lucide-book-open: **Sync Confluence**  
Mirror local markdown to wiki pages with `zaira wiki put`, images and all.](https://github.com/vivainio/zaira#wiki-put-with-sync)

[:lucide-shield-check: **Validate with rules**  
Check tickets against `rules.yaml` before transitioning them with `zaira check`.](https://github.com/vivainio/zaira#check-experimental)

</div>

## What it's good at

- Exporting tickets and Confluence pages to plain markdown for AI agents to read.
- Round-tripping ticket fields, descriptions, and wiki pages without leaving the terminal.
- Generating recurring reports from named JQL queries in `zproject.toml`.
- Tracking work with `zaira log` / `zaira hours` and validating transitions with `rules.yaml`.
- Mirroring a local docs tree onto Confluence spaces and folders.

## Get started

```bash
uv tool install zaira
zaira init
zaira get FOO-1234
```

See the [README](https://github.com/vivainio/zaira#readme) for the full
command reference, or install the bundled
[Claude Code skill](https://github.com/vivainio/agent-skills/tree/main/skills/zaira)
with `zaira install-skills`.
