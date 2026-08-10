# Zaira

> **Pronunciation:** *ZAY-rah* /ˈzeɪ.rə/ — named after Jira (*JEE-rah* /ˈdʒiː.rə/), though it works with Confluence too. Finnish speakers may pronounce it however they like.

A CLI tool for Jira and Confluence management. Export tickets to markdown, generate reports, and keep everything in sync.

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

This creates a credentials file in your platform's config directory (`~/Library/Application Support/zaira/` on macOS, `~/.config/zaira/` on Linux). Edit it with your Jira site and email:

```toml
site = "your-company.atlassian.net"
email = "your-email@example.com"
```

Then run `zaira init` again — it will prompt for your API token (hidden input) and store it in the OS keyring (Keychain on macOS, Secret Service / kwallet on Linux, Credential Manager on Windows).

Get your API token from: https://id.atlassian.com/manage-profile/security/api-tokens

Use `zaira init --set-token` to replace a stored token. If you prefer the old behaviour, you can still put `api_token = "..."` directly in `credentials.toml`; it will be used in preference to the keyring.

### 2. Initialize project (optional, for project managers)

For advanced workflows with named queries, report templates, and board aliases, generate `zproject.toml`:

```bash
zaira init-project FOO              # Single project
zaira init-project FOO BAR          # Multiple projects
```

This discovers each project's components, labels, and boards, then generates `zproject.toml` with named queries and reports. This is intended for project managers and power users who need repeatable reports and batch operations. Most commands work without this file.

## WSL

On WSL, zaira stores the API token in Windows Credential Manager instead of the Linux keyring (which isn't a real secret store on most WSL setups). It does this by shelling out to the [`wincred`](https://github.com/vivainio/wincred) helper binary, which it shares with Windows-side zaira.

Install it:

```bash
zaira init --install-wincred
```

This downloads `wincred.exe` into a Windows-side `.local\bin` directory found on PATH (uv on Windows provides `%USERPROFILE%\.local\bin`), then runs the normal credential setup.

## Commands

### get

Get individual tickets to stdout (default) or files:

```bash
# Output to stdout (default)
zaira get FOO-1234

# Save to a directory
zaira get FOO-1234 -o tickets/

# Bulk get with JQL, board, or sprint
zaira get --jql "project = FOO AND status = 'In Progress'" -o tickets/
zaira get --board 123 -o tickets/
zaira get --sprint 456 -o tickets/

# Output as JSON
zaira get FOO-1234 --format json

# Include linked pull requests (GitHub only)
zaira get FOO-1234 --with-prs

# Include custom fields (uses cached schema for name lookup)
zaira get FOO-1234 --all-fields

# Use a named field as body instead of description
zaira get FOO-1234 --field "Solution Section"

# Minimal output (key + summary front matter, description as body)
zaira get FOO-1234 --min

# Skip wiki-to-markdown conversion (preserve Jira wiki markup)
zaira get FOO-1234 --raw
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

### put

Push summary and description from a markdown file back to Jira:

```bash
# Round-trip: get → edit → put
zaira get FOO-123 > ticket.md
# ... edit ticket.md ...
zaira put ticket.md

# Preview changes without pushing
zaira put ticket.md --dry-run

# Skip markdown-to-wiki conversion (input is already Jira wiki syntax)
zaira put ticket.md --raw

# Read from stdin
zaira put -
```

Works with the full export format (extracts description between `## Description` and `## Links`) and a minimal format where the front matter contains only `key` and the body is the description:

```markdown
---
key: FOO-123
---
New description goes here.
```

Markdown in the description is auto-converted to Jira wiki syntax.

#### Custom field targeting with `--field`

By default, the body is written to the `description` field. Use `--field` to target a different Jira field:

```bash
# Round-trip a custom field
zaira get FOO-123 --field "Solution Section" > solution.md
# ... edit solution.md ...
zaira put solution.md

# Override target field from CLI (takes precedence over front matter)
zaira put solution.md --field "Solution Section"
```

When `get` is called with `--field`, it emits `field:` in the front matter. When `put` sees `field:` in front matter (or `--field` on the CLI), it writes the body to that Jira field instead of description:

```markdown
---
key: FOO-123
summary: "Implement feature X"
field: Solution Section
---
Solution content goes here.
```

### search

Search Jira tickets with text, filters, or raw JQL:

```bash
# Full-text search
zaira search "login bug"

# Pass JQL directly (auto-detected)
zaira search "project = FOO AND status = 'In Progress'"

# Explicit JQL
zaira search --jql "project = FOO AND type = Bug"

# Filter options
zaira search "login" --project FOO
zaira search "login" --status "In Progress"
zaira search "login" --assignee me
zaira search "login" --limit 20

# Extra columns
zaira search --jql "project = FOO" -f "fixVersions,assignee,priority"
zaira search "login" -p FOO -f "duedate,components,Developer"

# Output formats
zaira search "login" --format json        # JSON output
zaira search "login" --format toon        # TOON format (requires: pip install toon-format)
```

The `-f`/`--fields` flag adds extra columns to the output. Accepts standard fields (`assignee`, `priority`, `fixVersions`, `duedate`, `components`, `labels`, `resolution`), aliases (`Fix Versions`, `due date`, `type`), and custom fields by human name. Prints a header row and auto-sizes columns.

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

# Read any field value from stdin with -F "Field=-"
cat description.md | zaira edit FOO-1234 -F "Description=-"

# Preview changes without updating
zaira edit FOO-1234 -F "Priority=High" --dry-run

# Skip allowed_fields validation
zaira edit FOO-1234 -F "CustomField=value" --no-check
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

# Preview without executing
zaira transition FOO-1234 Done --dry-run

# Add a comment with the transition
zaira transition FOO-1234 Done --comment "Deployed to prod"

# Skip rules.yaml validation
zaira transition FOO-1234 Done --no-check
```

### check (experimental)

Validate tickets against a `rules.yaml` file:

```bash
zaira check FOO-123
zaira check FOO-123 FOO-456 FOO-789
zaira check FOO-123 --rules path/to/rules.yaml
```

See [RULES.md](RULES.md) for complete documentation on rules file format, discovery, and all available checks.

**Transition validation:** When `rules.yaml` exists, `zaira transition` automatically checks the target status rules before transitioning. If the ticket fails validation, the transition is blocked:

```
$ zaira transition FOO-123 Done
Blocked: FOO-123 fails rules for 'Done':
  FAIL  required    Resolution
  FAIL  not_contains Description

Use --no-check to skip validation.
```

Use `--no-check` to bypass: `zaira transition FOO-123 Done --no-check`

### link

Create a link between two tickets:

```bash
zaira link FOO-1234 FOO-5678              # Default: Relates
zaira link FOO-1234 FOO-5678 --type Blocks
zaira link FOO-1234 FOO-5678 -t Duplicates
```

### log

Log work hours to a ticket:

```bash
# Log time
zaira log FOO-1234 2h
zaira log FOO-1234 30m
zaira log FOO-1234 "1h 30m"

# Log with comment
zaira log FOO-1234 2h --comment "Code review"
zaira log FOO-1234 1h -c "Sprint planning"

# Log to a specific date
zaira log FOO-1234 3h --date 2026-02-05

# List existing worklogs
zaira log FOO-1234 --list
```

Time formats: `30m` (minutes), `2h` (hours), `1d` (day = 8h), `1w` (week = 40h), or compound like `1h 30m`. The `--list` flag shows all worklogs with author, date, and a total.

### hours

Show logged hours across all tickets for a time period:

```bash
# Last 7 days (default)
zaira hours

# Last 14 days
zaira hours --days 14

# Custom date range
zaira hours --from 2026-01-20 --to 2026-01-24

# Ticket totals only (no daily breakdown)
zaira hours --summary

# Hours by person on specific tickets
zaira hours FOO-123 FOO-456

# Combine ticket mode with date filtering
zaira hours FOO-123 --from 2026-01-01 --to 2026-01-31
```

Without ticket keys, shows your personal timesheet with daily breakdown. With ticket keys, shows hours split by person per ticket.

### attach

Upload attachments to a ticket:

```bash
zaira attach FOO-1234 screenshot.png
zaira attach FOO-1234 *.png doc.pdf       # Multiple files
```

### dashboards

List available Jira dashboards:

```bash
zaira dashboards
zaira dashboards --mine              # Only your dashboards
zaira dashboards --filter "sprint"   # Filter by name
zaira dashboards --limit 100         # Max results (default: 50)
```

### dashboard

Export a specific dashboard:

```bash
zaira dashboard 16148
zaira dashboard "https://company.atlassian.net/jira/dashboards/16148"
zaira dashboard 16148 --format json
zaira dashboard 16148 -o dashboard.md
```

### wiki

Access Confluence pages using the same credentials:

```bash
# List space contents
zaira wiki ls ENG                           # List root pages and folders
zaira wiki ls ENG -d 2                      # Tree with depth 2
zaira wiki ls ENG -d -1                     # Full tree (unlimited depth)
zaira wiki ls ENG -d 0                      # Root level only
zaira wiki ls "https://acme.atlassian.net/wiki/spaces/ENG/overview"  # From URL
zaira wiki ls my                            # List your personal space

# Get page by ID or URL (outputs markdown with front matter)
zaira wiki get 123456
zaira wiki get "https://site.atlassian.net/wiki/spaces/SPACE/pages/123456/Title"
zaira wiki get 123456 --format html       # Raw storage format
zaira wiki get 123456 --format json       # Full API response

# Export multiple pages to directory
zaira wiki get 123 456 789 -o docs/

# Export page and all children recursively
zaira wiki get 123 --children -o docs/

# List page and children (without exporting)
zaira wiki get 123 --list

# Search pages
zaira wiki search "search terms"
zaira wiki search "docs" --space TEAM     # Filter by space
zaira wiki search "docs" --space my       # Personal space (auto-detected)
zaira wiki search --creator "John Doe"    # Filter by creator
zaira wiki search "api" --limit 50        # Limit results (default: 25)
zaira wiki search "api" --format url      # Output just URLs
zaira wiki search "api" --format json     # Full JSON response
zaira wiki search --cql 'space = "ENG" AND label = "api"'  # Raw CQL
zaira wiki search "api" --format toon     # TOON format (requires: pip install toon-format)

# Create page from markdown
zaira wiki create -s SPACE -t "Page Title" -m -b page.md
zaira wiki create -s my -t "Title" -m -b page.md         # Personal space (auto-detected)
zaira wiki create -s SPACE -t "Title" -m -b -   # From stdin
zaira wiki create -t "Child Page" -p 123 -m -b page.md  # Under parent (space inferred)

# Upload attachments
zaira wiki attach 123456 image.png                        # Single file
zaira wiki attach 123456 *.png                            # Glob pattern
zaira wiki attach 123456 image.png --replace              # Replace if exists

# Download attachments by filename pattern
zaira wiki get-attachment 123456 '*.pdf'                  # Match pattern
zaira wiki get-attachment 123456 '*' -o ./files           # All, into directory
# Note: `wiki get` lists attachments in the markdown frontmatter
# (`attachments: [foo.pdf, bar.xlsx]`), and `wiki get --format json`
# includes them under `children.attachment.results`.

# Delete page
zaira wiki delete 123456              # Prompts for confirmation
zaira wiki delete 123456 --yes        # Skip confirmation

# Edit page properties
zaira wiki edit 123456 --title "New Title"
zaira wiki edit 123456 --parent 789            # Move under different parent (by ID)
zaira wiki edit 123456 --parent guides/api    # Move to folder path
zaira wiki edit 123456 --labels "docs,api,v2"  # Set labels (replaces existing)
zaira wiki edit 123456 --space NEWSPACE        # Move to different space
```

#### wiki put (with sync)

Update Confluence pages from markdown files with automatic sync tracking:

```bash
# Push local changes (page ID from front matter)
zaira wiki put -m page.md

# Multiple files / globs / directories
zaira wiki put -m docs/*.md
zaira wiki put -m docs/

# Check sync status
zaira wiki put -m page.md --status

# View diff between local and remote
zaira wiki put -m page.md --diff

# Pull remote changes to local file
zaira wiki put -m page.md --pull

# Force push (overwrite conflicts)
zaira wiki put -m page.md --force

# Create new pages for files without front matter
zaira wiki put -m docs/*.md --create              # Parent auto-detected from siblings
zaira wiki put -m docs/*.md --create --parent 123  # Explicit parent
zaira wiki put -m docs/*.md --create --space ENG   # Space from flag (or front matter)

# Mirror a local directory tree to Confluence folders
zaira wiki put docs/ --space ENG --mirror
zaira wiki put docs/ --space ENG --mirror --parent team-docs

# Explicit page ID (single file, overrides front matter)
zaira wiki put -m page.md -p 123456
```

**Creating new pages:** With `--create`, files without `confluence:` front matter become new pages. The parent is determined by (in order): `--parent` flag, `space:`/`folder:` front matter, or auto-detection from sibling files. After creation, front matter is added to the file.

**Mirroring directories:** `--mirror` maps a local directory tree to Confluence folders. It recursively finds `.md` files, derives `folder:` from each file's relative path, and writes `space:` and `folder:` into front matter. Then the normal create/push pipeline handles the rest — missing folders are created, and existing pages are moved if their folder changed. Requires `--space` (unless every file already has `space:` in front matter). Implies `--create`. Use `--parent` to nest everything under a prefix (e.g. `--parent team-docs` turns `api/design.md` into `folder: team-docs/api`).

**Front matter:** Files link to Confluence pages via YAML front matter. Title, labels, space, and folder sync automatically on push/pull:

```markdown
---
confluence: 123456
title: My Document
space: ENG
folder: guides/api
labels: [docs, api]
---

Content here with ![images](./images/diagram.png)
```

The `space:` and `folder:` fields are populated automatically on get/pull. When creating new pages with `--create`, they determine where the page is placed — missing folders are created automatically. Changing `folder:` and pushing moves the page to the new location. Title priority: front matter `title:` > first `# Heading` > filename.

**Image handling:** Local images (`![alt](./images/foo.png)`) are automatically uploaded as Confluence attachments on push, and downloaded to `images/` on pull. Only changed images are re-uploaded.

**Conflict detection:** Tracks versions and content hashes. If both local and remote changed since last sync, you'll get a conflict warning:

```
Error: Conflict detected!
  Local file changed since last sync
  Remote changed: version 5 -> 7
Use --diff to see changes, --force to overwrite remote, or --pull to discard local changes
```

### goals

Export Atlassian Goals (the Townsquare/Atlas product at `home.atlassian.com`) using the same Jira API token. Two subcommands, mirroring `report` (bulk) and `get` (single):

```bash
# Bulk export — paste the home.atlassian.com goals URL and zaira pulls cloudId + TQL out of it
zaira goals export --url 'https://home.atlassian.com/o/<orgId>/goals?cloudId=<cloudId>&tql=<encoded>'

# Or pass them directly
zaira goals export --cloud-id <cloudId> --tql 'archived = false'

# Output formats
zaira goals export --url '...' --format json -o goals.json
zaira goals export --url '...' --format md   -o goals.md     # one section per goal
zaira goals export --url '...' --format table -o goals.md    # one row per goal (Key, Name, Owner, Status, Target, Description, Latest update, Open risks)

# Slim vs full field set (default is slim; --full pulls description, sub-goals, projects, progress, latest update, tags, risks, etc.)
zaira goals export --url '...' --full --format md -o goals.md

# Single goal — cloudId is auto-detected from your Jira site
zaira goals get TEAM-123                                # full fields, JSON to stdout
zaira goals get TEAM-123 --minimal                      # slim fields only
zaira goals get TEAM-123 -o goal.md                     # markdown (extension picks format)
zaira goals get ari:cloud:townsquare:...:goal/abc123 --format json

# Batch — multiple keys in one API call
zaira goals get TEAM-1 TEAM-2 TEAM-3 -o goals/          # one file per goal
zaira goals get TEAM-1 TEAM-2 -o pair.md                # combined markdown
```

Talks to the GraphQL gateway on your Jira site (`/gateway/api/graphql`); no extra setup beyond `zaira init`. Status enum values are mapped to friendly labels (`On track`, `At risk`, `Pending`, `Cancelled`, …) and ADF-formatted descriptions and updates are rendered as plain markdown.

The `table` format's **Open risks** column shows unresolved entries from `goal.risks`. Use `zaira goals updates <KEY>` to see a goal's check-in history; pass `--with-updates` on `goals export` to include the update history in the bulk output.

### changelog

Show the change history for a ticket (who changed what, when):

```bash
zaira changelog FOO-123

# Show only last N changes
zaira changelog FOO-123 --tail 10

# Filter to a specific field
zaira changelog FOO-123 --field status

# List numbered revisions for a field
zaira changelog FOO-123 --field description --revisions

# Print a specific revision to stdout
zaira changelog FOO-123 --field description --rev 3

# Show full old/new values instead of diffs
zaira changelog FOO-123 --full
```

### history

Show recent write activity from the local activity log:

```bash
zaira history                   # Last 20 entries
zaira history --tail 50         # More entries
zaira history --key FOO-123     # Filter by ticket
```

### learn

Cache the editable fields for a project or issue (used by `allowed_fields` validation):

```bash
zaira learn FOO-123             # Learn from a specific issue
zaira learn FOO                 # Learn one issue per issue type in project FOO
zaira learn fields.yaml         # Import field mappings from a YAML file
```

### reset

Clear cached data or disable rules:

```bash
zaira reset                     # Clear all cached schema/editmeta data
zaira reset --rules             # Disable installed rules bundle (renames rules/ to rules-disabled/)
```

### bundle

Install and update rule bundles:

```bash
zaira bundle install https://example.com/rules.zip
zaira bundle install /path/to/local/rules.zip
zaira bundle install https://example.com/rules.zip --dry-run

zaira bundle update             # Re-fetch bundle from recorded source
zaira bundle update --dry-run
```

See [RULES.md](RULES.md) for documentation on rule bundle format.

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

## Xray Cloud (optional)

Xray support is an optional integration rather than part of Zaira's core Jira
functionality. It requires a separate Xray Cloud API key in addition to the Jira
credentials configured by `zaira init`.

Create an Xray API key in **Xray Global Settings → API Keys**, then store its
Client ID and Client Secret in the OS secret store:

```bash
zaira init-xray
```

On WSL, Zaira stores both values in Windows Credential Manager through
`wincred.exe`. They use the distinct targets `zaira-xray-client-id` and
`zaira-xray-client-secret` and are never written to a configuration file.

Include linked Xray tests, executions, and manual steps in a normal Jira ticket
export:

```bash
zaira get FOO-1234 --with-tests
```

Extract Xray tests as standalone Markdown documents:

```bash
# Print one or more tests to stdout
zaira xray get FOO-1234
zaira xray get FOO-1234 FOO-5678

# Write one KEY.md file per test
zaira xray get FOO-1234 FOO-5678 -o tests/
```

Output follows the Xray test kind:

- Manual tests use a Markdown table with Action, Data, and Expected Result.
- Cucumber tests use a fenced `gherkin` block.
- Generic tests use a Definition section.

## Project Configuration (for project managers)

The `zproject.toml` file stores project-specific settings for project managers and power users. After running `zaira init-project`, you can edit this file to rename reports, add custom queries, and organize boards to match your workflow:

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
# Save tickets to a custom directory (default: tickets/)
reported = { query = "reported-by-me", group_by = "status", tickets_dir = "reported/" }
```

## Output Structure

```
project/
  zproject.toml          # Project configuration
  tickets/               # Tickets from `zaira get`
    FOO-1234-ticket-title.md
    attachments/         # Downloaded attachments (up to 10 MB each)
      FOO-1234/
        screenshot.png
        design.pdf
    by-component/        # Symlinks grouped by component (requires symlinks=true)
      backend/
        FOO-1234-ticket-title.md -> ../../FOO-1234-ticket-title.md
    by-parent/           # Symlinks grouped by parent ticket (requires symlinks=true)
      FOO-1000-epic-name/
        FOO-1234-ticket-title.md -> ../../FOO-1234-ticket-title.md
  reports/               # Generated reports
    my-tickets.md
    my-tickets.json      # with --format json
    my-tickets.csv       # with --format csv
```

## Ticket Format

Tickets from `zaira get` include YAML front matter:

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

The client uses credentials from the platform config directory (`~/Library/Application Support/zaira/credentials.toml` on macOS, `~/.config/zaira/credentials.toml` on Linux). Schema functions return cached data populated by `zaira init-project` or `zaira info --save`.

## Claude Code Agent Skill

A [zaira agent skill](https://github.com/vivainio/agent-skills/tree/main/skills/zaira) is available for AI coding assistants, enabling agents to use zaira commands directly.

Install the bundled Claude Code skills with:

```bash
zaira install-skills                       # installs to ~/.claude/skills/
zaira install-skills --skills-dir ./skills # custom target directory
```

## License

MIT
