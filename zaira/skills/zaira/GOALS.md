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

# Multiple goals at once — single API call (TQL OR-list for keys, goals_byIds for ARIs)
zaira goals get TEAM-1 TEAM-2 TEAM-3                          # all to stdout
zaira goals get TEAM-1 TEAM-2 TEAM-3 -o goals/                # one file per goal in goals/
zaira goals get TEAM-1 TEAM-2 -o pair.md                      # combined markdown

# Update / check-in history for a goal (state transitions, summaries, notes)
zaira goals updates TEAM-123                                  # markdown to stdout
zaira goals updates TEAM-123 --format json -o updates.json    # raw JSON
zaira goals updates TEAM-123 --limit 10                       # cap results

# Bulk: include each goal's update history in the export
zaira goals export --url '...' --full --with-updates -o goals.json
```

## Output details

- **Status** values are mapped to friendly labels: `On track`, `At risk`, `Pending`, `Cancelled`, `Done`, `Off track`, `Paused`, `Archived`.
- **Description** and **latest update** text is rendered from Atlassian Document Format (ADF) into plain markdown — paragraphs, headings, bullet/numbered lists, code, blockquotes, hard breaks, and `**bold**` / `*em*` / `` `code` `` / `[link](url)` marks.
- **Open risks** column in the table format shows unresolved entries from `goal.risks`. Check-in history (state transitions, summaries, notes) is available separately via `zaira goals updates <KEY>` or in bulk via `zaira goals export --with-updates`.

## TQL filters

The `--tql` argument is the same query language the home.atlassian.com Goals UI uses. Common patterns:

```
archived = false
status = on_track
status = at_risk OR status = off_track
owner = <accountId> AND archived = false
name LIKE "Q3"
```

## Recipes

### Current risks summary

A markdown table of every goal that's currently at risk or off track, with the owner-written explanation in the Open risks column:

```bash
zaira goals export --url '<goals-url>' \
  --tql 'status = at_risk OR status = off_track' \
  --full --format table -o risks.md
```

### Goals by owner

Get one row per goal, then sort/group by the Owner column in your editor or with `awk -F'|' '{print $4, $2}' goals-table.md | sort`:

```bash
zaira goals export --url '<goals-url>' --full --format table -o goals-table.md
```

### Filter JSON to "goals with any risk info"

`zaira` doesn't ship a `--has-risks` flag, but the JSON output is easy to filter with `jq`. Picks up both explicit `goal.risks` entries and historical at-risk transitions in the update history:

```bash
zaira goals export --url '<goals-url>' --full -o goals.json

jq '[.[] | select(
  ((.risks.edges // []) | map(select(.node.resolvedDate == null)) | length > 0)
  or
  ((.updates.edges // []) | any(
    .node.newState.value as $n
    | $n != .node.oldState.value
    and (["at_risk","off_track","paused"] | index($n))
  ))
)]' goals.json > goals-with-risks.json
```

### Hierarchy walk: a portfolio goal and its sub-goals

`--full` already includes sub-goals (one level down). For deeper hierarchies, do one `goals get` per parent and recurse:

```bash
zaira goals get TEAM-14 --format json | jq '.subGoals.edges[].node.key'
```

### Status snapshot

Quick count of where things stand:

```bash
zaira goals export --url '<goals-url>' --full -o goals.json
jq -r '[.[] | .status.value] | group_by(.) | map({status: .[0], count: length})' goals.json
```

## Auth and endpoint

Uses Basic auth with email + API token from `zaira init` against `https://<your-site>.atlassian.net/gateway/api/graphql`. If you generated a *scoped* token, it needs the `read:goal:townsquare` scope (classic tokens just work). Some experimental fields like `goalType` are gated behind the Townsquare opt-in directive — already wired in the queries.
