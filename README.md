# Zaira

A CLI tool for offline Jira ticket management. Export tickets to markdown, generate reports, and keep everything in sync.

Designed for AI-assisted development workflows. By exporting Jira tickets to plain markdown files, AI agents and coding assistants can easily read project context, understand requirements, and reference ticket details without needing direct Jira API access.

## Installation

```bash
uv tool install zaira
```

Or with pip:

```bash
pip install zaira
```

## Setup

### 1. Configure credentials

Run `zaira init` to create the credentials file:

```bash
zaira init
```

This creates `~/.config/zaira/credentials.toml`. Edit it with your Jira details:

```toml
site = "your-company.atlassian.net"
email = "your-email@example.com"
api_token = "your-api-token"
```

Get your API token from: https://id.atlassian.com/manage-profile/security/api-tokens

### 2. Initialize project

After configuring credentials, initialize your project:

```bash
zaira init --project FOO
```

This discovers your project's components, labels, boards, and issue types, then generates `zproject.toml` with named queries and reports.

## Commands

### export

Export individual tickets. Without a `zproject.toml`, outputs to stdout. In a project directory, saves to `tickets/`:

```bash
# Outside project → stdout
zaira export FOO-1234

# Inside project → saves to tickets/
zaira export FOO-1234 FOO-1235
zaira export --jql "project = FOO AND status = 'In Progress'"
zaira export --board 123
zaira export --sprint 456

# Force stdout with -o -
zaira export FOO-1234 -o -

# Export as JSON
zaira export FOO-1234 --format json
```

### report

Generate markdown reports from JQL queries:

```bash
# Use a named report from zproject.toml
zaira report my-tickets

# Use a named query
zaira report --query my-tickets

# Use raw JQL
zaira report --jql "project = FOO AND type = Bug" --title "Bugs"

# Group by field
zaira report --jql "project = FOO" --group-by status

# Filter by label
zaira report --board main --label backend

# Export tickets along with the report
zaira report my-tickets --full

# Force re-export all tickets
zaira report my-tickets --full --force

# Output as JSON or CSV
zaira report my-tickets --format json
zaira report my-tickets --format csv
```

Reports are saved to `reports/` with YAML front matter containing the sync command (markdown only).

### sync

Re-sync a report using the command stored in its front matter:

```bash
zaira sync my-report.md

# Also export tickets referenced in the report
zaira sync my-report --full

# Force re-export all tickets
zaira sync my-report --full --force
```

When using `--full`, only tickets that have changed in Jira since the last sync are re-exported.

### boards

List available Jira boards:

```bash
zaira boards
zaira boards --project FOO
```

## Project Configuration

The `zproject.toml` file stores project-specific settings. After running `zaira init`, you're encouraged to edit this file to rename reports, add custom queries, and organize boards to match your workflow:

```toml
[project]
key = "FOO"
site = "company.atlassian.net"

[boards]
main = 123
support = 456

[queries]
my-tickets = "assignee = currentUser() AND project = FOO AND status != Done"
bugs = "project = FOO AND type = Bug AND status != Done"
# Queries can span multiple projects
all-my-work = "assignee = currentUser() AND project IN (FOO, BAR) AND status != Done"

[reports]
my-tickets = { query = "my-tickets", group_by = "status" }
bugs = { jql = "project = FOO AND type = Bug", group_by = "priority" }
sprint = { board = 123, group_by = "status", full = true }
# Reports can target multiple projects via JQL
cross-team = { jql = "project IN (FOO, BAR) AND type = Bug", group_by = "project" }
```

## Output Structure

```
project/
  zproject.toml          # Project configuration
  tickets/               # Exported tickets
    FOO-1234-ticket-title.md
    FOO-1234-ticket-title.json  # with --format json
    by-component/        # Symlinks grouped by component (markdown only)
      backend/
        FOO-1234-ticket-title.md -> ../../FOO-1234-ticket-title.md
    by-parent/           # Symlinks grouped by parent ticket
      FOO-1000-epic-name/
        FOO-1234-ticket-title.md -> ../../FOO-1234-ticket-title.md
  reports/               # Generated reports
    my-tickets.md
    my-tickets.json      # with --format json
    my-tickets.csv       # with --format csv
```

## Ticket Format

Exported tickets include YAML front matter:

```markdown
---
key: FOO-1234
summary: "Implement feature X"
type: Story
status: In Progress
priority: High
assignee: user@example.com
reporter: pm@example.com
components: Backend
labels: api, v2
parent: FOO-1000
synced: 2024-01-15T10:30:00
url: https://company.atlassian.net/browse/FOO-1234
---

# FOO-1234: Implement feature X

## Description

Feature description here...

## Comments

### John Doe (2024-01-14T09:00:00)

Comment text...
```

## Python API

For programmatic access (or AI agents needing advanced Jira operations), use `zaira.client()` to get an authenticated Jira client:

```python
import zaira

jira = zaira.client()

# Use the standard jira library API
issue = jira.issue("FOO-1234")
print(issue.fields.summary)

# Search with JQL
issues = jira.search_issues("project = FOO AND status = 'In Progress'")
for issue in issues:
    print(f"{issue.key}: {issue.fields.summary}")
```

This returns a `jira.JIRA` instance from the [jira](https://jira.readthedocs.io/) library, using credentials from `~/.config/zaira/credentials.toml`.

## License

MIT
