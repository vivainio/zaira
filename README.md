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

After configuring credentials, initialize with your Jira project key(s):

```bash
zaira init FOO              # Single project
zaira init FOO BAR          # Multiple projects
```

This discovers each project's components, labels, and boards, then generates `zproject.toml` with named queries and reports.

## Commands

### export

Export individual tickets to stdout (default) or files:

```bash
# Output to stdout (default)
zaira export FOO-1234

# Save to tickets/ directory
zaira export FOO-1234 --files
zaira export FOO-1234 -o tickets/

# Bulk export with JQL, board, or sprint
zaira export --jql "project = FOO AND status = 'In Progress'" --files
zaira export --board 123 --files
zaira export --sprint 456 --files

# Export as JSON
zaira export FOO-1234 --format json

# Include linked pull requests (GitHub only)
zaira export FOO-1234 --with-prs

# Include custom fields (uses cached schema for name lookup)
zaira export FOO-1234 --all-fields
```

### create

Create a ticket from a YAML front matter file:

```bash
# Create ticket from file
zaira create ticket.md

# Create from stdin
zaira create - <<EOF
---
project: FOO
summary: Quick ticket
type: Task
---
Description here
EOF

# Preview without creating
zaira create ticket.md --dry-run
```

The file format matches exported tickets:

```markdown
---
project: FOO
summary: "Implement feature X"
type: Story
priority: High
components: [backend, api]
labels: [v2]
Epic Link: FOO-100        # Custom field (looked up via schema)
---

## Description

Feature description here...
```

Custom field names are mapped to IDs using the cached schema. Run `zaira info fields --refresh` to cache field mappings.

### my

Show your open tickets grouped by status:

```bash
zaira my
```

Tickets are sorted by age (oldest first) within each group. Uses the `my-tickets` query from `zproject.toml` if configured, otherwise defaults to `assignee = currentUser() AND status NOT IN (Done, Closed, Resolved, Disposal, Rejected)`.

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

# Force file output without zproject.toml
zaira report --jql "project = FOO" --files
```

Reports are saved to `reports/` with YAML front matter containing the refresh command (markdown only).

### refresh

Refresh a report using the command stored in its front matter:

```bash
zaira refresh my-report.md

# Also export tickets referenced in the report
zaira refresh my-report --full

# Force re-export all tickets
zaira refresh my-report --full --force
```

When using `--full`, only tickets that have changed in Jira since the last refresh are re-exported.

### boards

List available Jira boards:

```bash
zaira boards
zaira boards --project FOO
```

### edit

Edit a ticket's fields:

```bash
# Title and description
zaira edit FOO-1234 --title "New title"
zaira edit FOO-1234 --description "New description"
zaira edit FOO-1234 -t "Title" -d "Description"

# Arbitrary fields with -F (repeatable)
zaira edit FOO-1234 -F "Priority=High"
zaira edit FOO-1234 -F "Priority=High" -F "Epic Link=FOO-100"
zaira edit FOO-1234 -F "labels=bug,urgent" -F "Story Points=5"

# Assign ticket
zaira edit FOO-1234 -F "assignee=me"                  # Assign to yourself
zaira edit FOO-1234 -F "assignee=user@example.com"   # Assign by email

# From YAML file
zaira edit FOO-1234 --from fields.yaml

# From stdin
zaira edit FOO-1234 --from - <<EOF
Priority: High
Epic Link: FOO-100
Story Points: 5
labels: [bug, urgent]
EOF

# Multiline description via stdin
zaira edit FOO-1234 -d - <<EOF
h2. Overview

This is a *bold* statement with _italic_ text.
EOF
```

Custom field names are mapped to IDs using the cached schema. Descriptions support [Jira wiki syntax](https://jira.atlassian.com/secure/WikiRendererHelpAction.jspa?section=all).

### comment

Add a comment to a ticket:

```bash
zaira comment FOO-1234 "This is my comment"

# Multiline via stdin
zaira comment FOO-1234 - <<EOF
Line 1
Line 2
EOF

# Pipe from file or command
cat notes.txt | zaira comment FOO-1234 -
```

### transition

Transition a ticket to a new status:

```bash
zaira transition FOO-1234 "In Progress"
zaira transition FOO-1234 Done
```

### link

Create a link between two tickets:

```bash
zaira link FOO-1234 FOO-5678              # Default: Relates
zaira link FOO-1234 FOO-5678 --type Blocks
zaira link FOO-1234 FOO-5678 -t Duplicates
```

### info

Query Jira instance metadata. Results are cached locally and served from cache by default:

```bash
zaira info statuses      # List statuses and categories
zaira info priorities    # List priorities
zaira info issue-types   # List issue types
zaira info link-types    # List available link types
zaira info fields        # List custom fields
zaira info fields --all  # Include standard fields
zaira info fields --filter epic  # Search by name or ID

# Project-specific metadata
zaira info components FOO  # List components for project
zaira info labels FOO      # List labels for project

# Refresh from Jira API (also updates cache)
zaira info statuses --refresh
zaira info fields -r

# Refresh all metadata at once
zaira info --save
```

Instance schema is cached at `~/.cache/zaira/zschema_PROFILE.json` and project schemas at `~/.cache/zaira/zproject_PROFILE_PROJECT.json`.

## Project Configuration

The `zproject.toml` file stores project-specific settings. After running `zaira init`, you're encouraged to edit this file to rename reports, add custom queries, and organize boards to match your workflow:

```toml
[project]
site = "company.atlassian.net"
profile = "work"  # Optional: name for schema cache (default: "default")

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
    attachments/         # Downloaded attachments (up to 10 MB each)
      FOO-1234/
        screenshot.png
        design.pdf
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
Epic Link: FOO-1000       # Custom fields (with --all-fields)
Story Points: 5
synced: 2024-01-15T10:30:00
url: https://company.atlassian.net/browse/FOO-1234
---

# FOO-1234: Implement feature X

## Description

Feature description here...

## Attachments

- [screenshot.png](attachments/FOO-1234/screenshot.png) (145 KB, Jane Doe, 2024-01-14)

## Comments

### John Doe (2024-01-14T09:00:00)

Comment text...
```

## Python API

For programmatic access (or AI agents needing advanced Jira operations):

```python
import zaira

# Authenticated Jira client (jira.JIRA instance)
jira = zaira.client()
issue = jira.issue("FOO-1234")
issues = jira.search_issues("project = FOO AND status = 'In Progress'")

# Instance schema (fields, statuses, priorities, issue types, link types)
s = zaira.schema()
s["statuses"]    # {'Open': 'To Do', 'In Progress': 'In Progress', ...}
s["fields"]      # {'customfield_10001': 'Epic Link', ...}
s["priorities"]  # ['Blocker', 'Critical', 'Major', ...]

# Project schema (components, labels)
ps = zaira.project_schema("FOO")
ps["components"]  # ['Backend', 'Frontend', ...]
ps["labels"]      # ['bug', 'feature', ...]
```

The client uses credentials from `~/.config/zaira/credentials.toml`. Schema functions return cached data populated by `zaira init`.

## License

MIT
