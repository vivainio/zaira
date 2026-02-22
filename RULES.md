# Rules engine

Zaira can validate Jira tickets against a set of field requirements and
allowed status transitions defined in a YAML file.

## Quick start

```bash
zaira check FOO-123              # check a ticket against rules.yaml
zaira check FOO-123 BAR-456      # check multiple tickets
zaira check FOO-123 --rules path/to/rules.yaml
```

`zaira transition` also runs checks automatically before executing a
transition (pass `--no-check` to skip).

## Rules file discovery

When no `--rules` path is given, zaira looks for `rules.yaml` in order:

1. Current working directory (`./rules.yaml`)
2. Platform config dir (`~/.config/zaira/rules/rules.yaml` on Linux/macOS,
   `%APPDATA%\zaira\rules\rules.yaml` on Windows)

## File structure

A rules file is a YAML document. The top-level keys are Jira issue type
names. Each issue type block can contain rule checks, status-conditional
rules, and transition constraints.

```yaml
Story:
  # rules for Stories go here

Bug:
  # rules for Bugs go here
```

---

## Rule types

Rules live inside an issue type block (or inside a `when` / `if` block —
see below). All checks for a field use the field's **human-readable name**
exactly as it appears in Jira (custom fields included).

### `required`

Field must be present and non-null.

```yaml
required: [Components, Story Points]
```

### `non_empty`

Field must be present, non-null, and not an empty string or empty list.

```yaml
non_empty: [description, Components]
```

### `one_of`

Field value must be one of the listed values.

```yaml
one_of:
  Deployment Cadence: [Weekly, Fortnightly, Monthly Release, Continuous Delivery]
```

### `not_one_of`

Field value must not be any of the listed values.

```yaml
not_one_of:
  priority: [Undefined]
```

### `contains`

String field must contain the given substring(s).

```yaml
contains:
  description: "Acceptance Criteria"
```

### `not_contains`

String field must not contain the given substring(s).

```yaml
not_contains:
  summary: ["WIP", "TODO"]
```

### `matches`

String field must match the given regex(es).

```yaml
matches:
  Fix Version: '^\d{4}\.\d+$'
```

### `not_matches`

String field must not match the given regex(es).

```yaml
not_matches:
  summary: '(?i)^copy of'
```

### `count_matches`

The number of regex matches in a string field must fall within `[min, max]`.

```yaml
count_matches:
  description:
    pattern: '^##\s'
    min: 2
    max: 10
```

### `sections_present`

String field must contain each listed section heading (markdown `## Heading`
or Jira wiki `h2. Heading`, case-insensitive match on the heading text).

```yaml
sections_present:
  description: [Overview, Acceptance Criteria, Rollback Plan]
```

### `subtask_types`

Ticket must have at least one subtask of each listed issue type.

```yaml
subtask_types: [Deployment Wave]
```

### `no_open_linked`

Linked tickets of the given type/priority must all be in a Done status
category. Both `type` and `priority` are optional filters.

```yaml
no_open_linked:
  - type: Bug
    priority: [Blocker, Critical, Major]
```

---

## Status-conditional rules (`when`)

`when` is a map of status names to rule blocks. Rules inside a status block
apply only when the ticket is in that status (or is being transitioned into
it).

```yaml
Story:
  when:
    Implementing:
      required:
        - Components
        - Deployment Cadence
    Validating:
      required: [Testing Coverage]
      no_open_linked:
        - type: Bug
          priority: [Blocker, Critical]
```

---

## Conditional rules (`if` / `match` / `then`)

`if` is a list of conditions. Each entry has a `match` dict and a `then`
rule block. All conditions in `match` must be true for `then` to apply
(AND logic). The special field `status` in `match` uses the ticket's current
(or transition-target) status.

```yaml
Story:
  if:
    - match:
        status: Implementing
        Deployment Cadence: Monthly Release
      then:
        required: [Fix Version]
    - match:
        status: Ready for Release
        Deployment Cadence: Continuous Delivery
        Reviewed Change Type: Advanced
      then:
        required: [CAB Approval Summary]
```

---

## Transition constraints (`valid_transitions`)

`valid_transitions` maps each source status to the list of statuses that
are valid transition targets. If a source status is listed, any transition
to a target not in the list is blocked.

```yaml
Story:
  valid_transitions:
    New: [Analyzing, Backlog, On Hold, Disposal]
    Analyzing: [Implementing, Ready for Implementation, Backlog, On Hold, Disposal]
    Implementing: [Ready for Validation, Validating, Backlog, On Hold, Disposal]
```

Source statuses not listed in `valid_transitions` are unconstrained.

---

## Per-project rules (`import`)

A rules file can declare `import: <path>` to merge on top of another file.
The path is resolved **relative to the importing file**.

```yaml
# rules.FOO.yaml
import: rules.yaml      # inherit the team baseline

Story:
  when:
    Implementing:
      required: [Extra Approval]    # FOO adds one more required field
```

```bash
zaira check FOO-123 --rules rules.FOO.yaml
```

The importing file's rules are merged **additively** on top of the imported
base:

- List fields (`required`, `non_empty`, `subtask_types`) — union
- Dict fields (`one_of`, `contains`, etc.) — override wins on key collision
- `when` — merged per status
- `if` — lists concatenated
- `valid_transitions` — override wins per source status
- `no_open_linked` — lists concatenated

Imports can be chained to arbitrary depth: an imported file may itself
declare `import`. Cycles are detected and reported as an error.

To use a completely independent rule set for a project, simply omit `import`
and write the file from scratch.

---

## Full example

```yaml
# rules.yaml

Story:
  valid_transitions:
    New: [Analyzing, Backlog, On Hold, Disposal]
    Analyzing: [Implementing, Ready for Implementation, Backlog, On Hold, Disposal]
    Implementing: [Ready for Validation, Validating, Backlog, On Hold, Disposal]
    Ready for Validation: [Validating, Backlog, On Hold, Disposal]
    Validating: [Ready for Release, Backlog, On Hold, Disposal]
    Ready for Release: [Done, Backlog, On Hold, Disposal]

  when:
    New:
      non_empty: [description]
    Analyzing:
      required: [Story Points, Components, Acceptance Criteria]
    Implementing:
      required:
        - Components
        - Deployment Cadence
        - Downtime Needed
        - Feature Enablement
        - Performance Impact
        - Security Impact
        - Regression Risk
    Validating:
      required: [Acceptance Criteria, Reviewed Change Type, Testing Coverage]
      no_open_linked:
        - type: Bug
          priority: [Blocker, Critical, Major]

  if:
    - match:
        status: Implementing
        Deployment Cadence: Monthly Release
      then:
        required: [Fix Version]
    - match:
        status: Ready for Release
        Deployment Cadence: Continuous Delivery
        Reviewed Change Type: Advanced
      then:
        required: [CAB Approval Summary]
    - match:
        status: Ready for Release
        Deployment Cadence: Continuous Delivery
      then:
        subtask_types: [Deployment Wave]

Bug:
  when:
    Done:
      subtask_types: [Deployment Wave]
```
