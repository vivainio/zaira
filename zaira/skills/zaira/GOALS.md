# Atlassian Goals

Export Atlassian Goals (the Townsquare/Atlas product at `home.atlassian.com`) using the same Jira credentials (`zaira init`). Talks to the GraphQL gateway on your Atlassian site; no extra setup.

## Commands

```bash
# Bulk export — paste the home.atlassian.com goals URL, cloudId + TQL are parsed out of it
zaira goals export --url 'https://home.atlassian.com/o/<orgId>/goals?cloudId=<cloudId>&tql=<encoded>'

# Or pass them directly
zaira goals export --cloud-id <cloudId> --tql 'archived = false'

# Output formats
zaira goals export --url '...' --format json -o goals.json
zaira goals export --url '...' --format md   -o goals.md     # one section per goal
zaira goals export --url '...' --format table -o goals.md    # one row per goal (Key, Name, Owner, Status, Target, Description, Latest update, Open risks)

# Slim vs full field set
zaira goals export --url '...'                               # slim by default
zaira goals export --url '...' --full --format md -o goals.md  # description, sub-goals, projects, progress, latest update, tags, risks, etc.

# Single goal — cloudId is auto-detected from your Jira site
zaira goals get TEAM-123                                      # full fields, JSON to stdout
zaira goals get TEAM-123 -o goal.md                           # markdown (extension auto-picks format)
zaira goals get TEAM-123 --minimal --format json              # slim
zaira goals get ari:cloud:townsquare:...:goal/abc123          # ARI also works
```

## Output details

- **Status** values are mapped to friendly labels: `On track`, `At risk`, `Pending`, `Cancelled`, `Done`, `Off track`, `Paused`, `Archived`.
- **Description** and **latest update** text is rendered from Atlassian Document Format (ADF) into plain markdown — paragraphs, headings, bullet/numbered lists, code, blockquotes, hard breaks, and `**bold**` / `*em*` / `` `code` `` / `[link](url)` marks.
- **Open risks** column in the table format combines two sources:
  - Unresolved entries from `goal.risks` (the dedicated risks feature in Atlassian Goals).
  - Update summaries from the goal's check-in history where the status *transitioned into* `at_risk`, `off_track`, or `paused` — i.e. the explanation a goal owner wrote when they marked the goal at-risk. Each entry is prefixed with the date and the new status, e.g. `(2026-04-02 → At risk) Some PI1 dev items still need work…`.
  - Plus any non-archived `updateNotes` on those check-ins (free-form risk/blocker notes).

## TQL filters

The `--tql` argument is the same query language the home.atlassian.com Goals UI uses. Common patterns:

```
archived = false
status = on_track
status = at_risk OR status = off_track
owner = <accountId> AND archived = false
name LIKE "Q3"
```

## Auth and endpoint

Uses Basic auth with email + API token from `zaira init` against `https://<your-site>.atlassian.net/gateway/api/graphql`. If you generated a *scoped* token, it needs the `read:goal:townsquare` scope (classic tokens just work). Some experimental fields like `goalType` are gated behind the Townsquare opt-in directive — already wired in the queries.
