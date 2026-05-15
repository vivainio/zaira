---
name: zaira
description: Access Jira tickets offline using zaira CLI. Use when user needs to export, report, or refresh Jira tickets, or mentions "jira", "zaira", or ticket keys like "FOO-123".
---

# Zaira - Jira CLI

Exports Jira tickets to local markdown for offline access. See https://github.com/vivainio/zaira for setup.

**Start here:** `zaira get FOO-1234` is usually the first command to run — it fetches and displays a ticket. Use `--min` for a quick peek (key + summary + description only).

## Commands

```bash
# Search tickets
zaira search "login bug"                    # Text search
zaira search "login bug" -p FOO             # Text search in project
zaira search -p FOO -s "In Progress"        # Filter by project and status
zaira search -a "john.doe" -p FOO           # Filter by assignee
zaira search --jql "project = FOO AND created >= -7d"  # Raw JQL
zaira search "keyword" -n 20                # Limit results
zaira search "login" --format json          # JSON output
zaira search "login" --format toon          # TOON format (requires: pip install toon-format)

# Get tickets (stdout by default, -o to save files)
zaira get FOO-1234 --min                    # Peek: key + summary + description only (preferred for quick reads)
zaira get FOO-1234                          # View ticket to stdout
zaira get FOO-1234 FOO-5678                 # View multiple tickets
zaira get FOO-1234 --format json            # JSON output
zaira get FOO-1234 --all-fields             # Include custom fields
zaira get FOO-1234 -o tickets/              # Save to files
zaira get --jql "project = FOO" -o tickets/ # Batch export by JQL
zaira get --board 123 -o tickets/           # Export from board
zaira get --sprint 456 -o tickets/          # Export from sprint
zaira get FOO-1234 --with-prs              # Include linked GitHub PRs
zaira get FOO-1234 --with-tests            # Include linked Xray tests and executions
zaira get --jql "..." -o tickets/ --parallel  # Parallel export + attachment download

# Reports (group-by: status, priority, issuetype, assignee, labels, components, parent)
zaira report --board 123 --group-by status  # Generate report from board
zaira report my-tickets --full              # Named report + export tickets
zaira report --dashboard 123                # Report from Jira dashboard
zaira report --jql "project = FOO" --files  # Force file output
zaira report --jql "..." -g components      # Group by component
zaira report --jql "..." --full --parallel  # Parallel ticket export
zaira report --dashboard 123 --parallel     # Parallel dashboard gadget queries
zaira refresh sprint-review.md              # Refresh existing report

# View my tickets
zaira my                                    # Show my assigned tickets
zaira my -r                                 # Show tickets I reported (created)
zaira recent                                # Show recently viewed tickets (website "Recent" list)
zaira recent -n 10                          # Limit to 10
zaira boards                                # List boards

# Create ticket from YAML front matter
zaira create ticket.md                      # Create from file
zaira create - --dry-run                    # Preview from stdin

# Edit ticket fields
zaira edit FOO-1234 --title "New title"
zaira edit FOO-1234 --description "New description"
zaira edit FOO-1234 --field "Priority=High" --field "Epic Link=FOO-100"
zaira edit FOO-1234 --field "assignee=me"   # Assign to yourself
zaira edit FOO-1234 --field "assignee=user@example.com"  # Assign by email
zaira edit FOO-1234 --field "components=Backend"  # Set component (case-insensitive, validated against project)
zaira edit FOO-1234 --from fields.yaml      # Update from YAML file
zaira edit FOO-1234 --from -                # Update from stdin YAML
zaira edit FOO-1234 --field "Description=-" # Read field value from stdin
zaira edit FOO-1234 --field "Priority=High" --dry-run  # Preview without updating
zaira edit FOO-1234 --field "Priority=High" --no-check  # Skip field whitelist validation

# Log work hours
zaira log FOO-1234 2h                       # Log 2 hours
zaira log FOO-1234 30m -c "Code review"     # Log with comment
zaira log FOO-1234 "1h 30m" -d 2026-02-05  # Log to specific date
zaira log FOO-1234 --list                   # List worklogs with total

# Query hours across tickets
zaira hours                                 # Last 7 days (personal)
zaira hours --days 14                       # Last 14 days
zaira hours --from 2026-01-20 --to 2026-01-24  # Custom range
zaira hours --summary                       # Ticket totals only
zaira hours FOO-123 FOO-456                 # Hours by person on tickets

# Download attachments by pattern
zaira get-attachment FOO-1234 "*.pdf"        # Download PDFs to current dir
zaira get-attachment FOO-1234 "report*" -o tmp/  # Download to specific dir
zaira get-attachment FOO-1234 "*"            # Download all attachments

# Upload attachments
zaira attach FOO-1234 file1.pdf file2.png    # Upload files to ticket

# Other actions
zaira comment FOO-1234 "Comment text"       # Add comment to ticket
zaira link FOO-1234 FOO-5678 --type Blocks  # Link tickets
zaira transition FOO-1234 "In Progress"     # Change ticket status
zaira transition FOO-1234 --list            # List available transitions
zaira transition FOO-1234 Done -F "Resolution=Done"  # Set fields during transition
zaira transition FOO-1234 Done -c "Comment text"  # Include comment with transition
zaira transition FOO-1234 Done -F "Resolution=Done" -c "Comment"  # Fields + comment
zaira transition FOO-1234 Done --dry-run    # Preview without transitioning
zaira transition FOO-1234 Done --no-check  # Skip rules validation

# Activity history (local log of write operations)
zaira history                               # Last 20 entries
zaira history -n 50                         # Last 50 entries
zaira history -k FOO-1234                   # Filter by ticket key

# Rules validation
zaira check FOO-1234                        # Check ticket against rules.yaml
zaira check FOO-1234 FOO-5678              # Check multiple tickets

# Rules bundle management
zaira bundle install skills/jira-process/rules  # Install from local directory
zaira bundle install https://example.com/bundle.zip  # Install from URL
zaira bundle update                         # Re-fetch from recorded source
zaira bundle update --dry-run               # Preview what would change

# Cache management
# If zaira behaves unexpectedly or gets out of sync, 'zaira reset' is safe to run at any time.
# It clears the local cache and zaira will re-fetch fresh data from Jira on next use.
zaira reset                                 # Clear all cached data (editmeta, schema, field descriptions)
zaira reset --rules                         # Disable rules bundle (renames rules/ to rules-disabled/)

# Instance metadata (cached locally)
zaira info statuses                         # List statuses
zaira info fields                           # List custom fields (filtered by allowed_fields if configured)
zaira info fields --all                     # Show all fields (bypass allowed_fields filter)
zaira info fields --refresh                 # Refresh from Jira API
zaira info field Priority "Story Points"    # Look up editmeta for fields (values grouped by project)
zaira info field components                 # List valid components grouped by project
zaira info field components -p FOO          # List valid components for a specific project
```

## Jira Formatting

When editing ticket descriptions or comments, use Jira wiki markup (not markdown):

```
h1. Heading 1
h2. Heading 2
h3. Heading 3

* Bullet item
* Another item

# Numbered item
# Another numbered item

*bold*  _italic_  -strikethrough-
[link text|https://example.com]
{code}code block{code}
```

## Confluence Wiki

See [CONFLUENCE.md](./CONFLUENCE.md) for wiki commands (`zaira wiki get/put/edit/delete`).

## Atlassian Goals

See [GOALS.md](./GOALS.md) for the Atlassian Goals (Townsquare) export commands (`zaira goals export/get`).

## Programmatic Access

```python
import zaira

# Jira client
jira = zaira.client()
issue = jira.issue("FOO-123")

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

## Output

- `tickets/` - Exported ticket markdown files
- `reports/` - Generated reports
- `~/.cache/zaira/` - Cached schema (fields, statuses, etc.) and `activity.log`

## Setup

```bash
zaira init                                  # Setup/verify credentials
```

## Project Setup (for project managers)

**Note:** `zproject.toml` is for project managers and power users who need repeatable reports, query aliases, and batch operations. Most users don't need this - the commands above work without any project configuration.

```bash
zaira init-project FOO                      # Generate zproject.toml for project
zaira init-project FOO BAR                  # Multiple projects
zaira init-project FOO --force              # Overwrite existing config
```

In a directory with `zproject.toml`, you can use named queries, report aliases, and batch operations.
