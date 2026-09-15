# Hooks

Zaira validates and enriches tickets entirely through **hooks**: plain
Python functions you register against a named hook point. There is no
separate rules file format — hooks are the only guardrail mechanism, so
anything from a one-line check to logic that calls an external service is
the same kind of code.

## Quick start

```python
# hooks/policy.py
from zaira.hooks import hook, HookPoint, CreateContext
from zaira.types import Violation


@hook(HookPoint.PRE_CREATE, project="FOO")
def no_tasks(ctx: CreateContext) -> Violation | None:
    if ctx.issue_type == "Task":
        return Violation("issuetype", "hook", "FOO does not accept Task tickets")
    return None
```

Ship that file as an installed pip package (see Distribution below), then:

```bash
zaira create ticket.md   # blocked if project: FOO, type: Task
zaira hooks               # lists what's loaded
```

`Violation` (`zaira.types`) is `(field, check, message)` — `zaira
check`/`create`/`edit`/`transition` all print it the same way regardless
of which hook point produced it.

## Hook points

| Point | Runs | Signature | Can block? |
|---|---|---|---|
| `HookPoint.PRE_CREATE` | Before `zaira create` posts a ticket | `(ctx: CreateContext) -> Violation \| list[Violation] \| None` | Yes |
| `HookPoint.POST_CREATE` | After a successful `zaira create` | `(ctx: CreateContext) -> None` | No — side effects only |
| `HookPoint.PRE_WRITE` | Before `zaira edit`/`zaira transition -F` write fields to an existing ticket | `(ctx: FieldWriteContext) -> Violation \| list[Violation] \| None` | Yes |
| `HookPoint.CHECK` | Wherever a ticket is validated — `zaira check`, and `zaira transition`'s pre-transition check against the target status | `(ticket: dict, status: str) -> Violation \| list[Violation] \| None` | Yes |

A hook may return `None` (pass), a single `Violation`, or a list of them.
Any hook point may also call `note()` (see below) to surface a message
that never blocks, independent of what it returns.

`HookPoint` is a `StrEnum` — `HookPoint.PRE_CREATE == "pre_create"` — so a
bare string still works at runtime, but `HookPoint.X` is what type-checks
against the right signature (see Typing below) and is what every example
here uses.

### `CreateContext`

Passed to `PRE_CREATE`/`POST_CREATE`:

```python
@dataclass
class CreateContext:
    project: str
    issue_type: str
    front_matter: dict[
        str, Any
    ]  # mutable — same shape as the ticket file's YAML front matter
    description: str = ""  # mutable
    key: str | None = None  # set once the ticket is created, before post_create runs
```

`pre_create` hooks may edit `ctx.front_matter` / `ctx.description` in
place (or reassign `ctx.description = ...`) to enrich a ticket before
creation, in addition to returning violations to block it.

### `FieldWriteContext`

Passed to `PRE_WRITE` — a write about to happen to an *existing* ticket,
via `zaira edit --field`/`--from` or `zaira transition -F`:

```python
@dataclass
class FieldWriteContext:
    project: str
    key: str
    issue_type: str
    fields: dict[str, Any]  # human-readable field name -> raw value, before ID-mapping
```

### `CHECK`

Called from `zaira.check.check_ticket()`, so it fires for **both**
`zaira check <key>` (against the ticket's current status) and
`zaira transition <key> <status>`'s pre-transition validation (against the
target status) — with no other configuration needed.

## Filtering by project/issue type

`@hook(point, project=..., issue_type=...)` takes a single string or an
iterable of them; the hook only runs when the context matches, so you
don't need to open every hook with a manual guard clause:

```python
@hook(HookPoint.PRE_CREATE, project=["FOO", "BAR"], issue_type="Task")
def restrict(ctx: CreateContext) -> Violation | None:
    return Violation("issuetype", "hook", "Task not allowed here")
```

For `CHECK` hooks, `project` is derived from the ticket's key prefix
(`FOO-123` → `FOO`) since a ticket dict has no separate project field.

## Non-blocking messages: `note()`

A `Violation` always blocks/fails the command. For something a hook wants
to surface that *shouldn't* — a heads-up, a reminder, context worth a
human's attention — call `note()` from inside the hook instead of (or
alongside) returning a `Violation`. A hook may call it any number of
times:

```python
from zaira.hooks import hook, HookPoint, note


@hook(HookPoint.PRE_CREATE, project="FOO")
def flag_cadence(ctx: CreateContext) -> None:
    if ctx.front_matter.get("Deployment Cadence") == "Monthly Release":
        note("Monthly Release: next deploy window opens the 15th")
```

```
$ zaira create ticket.md
  NOTE  Monthly Release: next deploy window opens the 15th
Created FOO-123
```

Notes are printed by the calling command right after it runs the relevant
hooks for that command, and are drained automatically — nothing persists
between separate `zaira` invocations, and a note never affects whether the
command blocks or exits non-zero, even if the same hook call also returns
a `Violation`.

## Typing

Every hook point has a `Protocol` (`PreCreateHook`, `PostCreateHook`,
`PreWriteHook`, `CheckHook`) and `@hook(...)` is overloaded per
`HookPoint` value, so a type checker verifies your function's signature
matches the point you registered it against — get the signature wrong and
`@hook(HookPoint.PRE_CREATE)` itself is a type error, not just a runtime
surprise the first time it's called.

## Isolation and the `--no-check` escape hatch

A hook that raises is caught, reported to stderr as a warning, and
skipped — it never crashes or blocks an otherwise valid ticket operation
beyond the one check it implements. `--no-check` (on `create`, `edit`, and
`transition`) skips hooks entirely for that run.

## Field allow-lists: `allowlist_from_file`

There's no more `allowed_fields.txt` CLI feature — it's a `PRE_WRITE` hook
built from a small helper, same plain-text format as before (one field
name per line, `#` comments, blank lines ignored):

```python
# hooks/field_policy.py
from zaira.hooks import allowlist_from_file

allowlist_from_file(
    "allowed_fields.txt",
    per_project={"FOO": "allowed_fields_FOO.txt"},  # unioned with the global list
)
```

That's the whole file — `allowlist_from_file` registers itself as a
`PRE_WRITE` hook by default (pass `register=False` to get the callable
back instead, e.g. to compose it inside your own hook). It reuses the same
fuzzy-match "did you mean" suggestion logic the old feature had.

`path`/`per_project` accept anything with `.read_text()` — a
`pathlib.Path`, or an `importlib.resources` `Traversable` for data shipped
inside a pip package (see below).

## Distribution — installed pip packages only

A normal Python package that declares a `zaira.hooks` entry point pointing
at a module. Importing that module runs its `@hook(...)` registrations:

```toml
# pyproject.toml of a hook package, e.g. "zaira-hooks-acme"
[project.entry-points."zaira.hooks"]
policy = "zaira_hooks_acme.policy"
```

```python
# zaira_hooks_acme/policy.py
from zaira.hooks import hook, HookPoint, CreateContext
from zaira.types import Violation


@hook(HookPoint.PRE_CREATE, project="FOO")
def no_tasks(ctx: CreateContext) -> Violation | None:
    if ctx.issue_type == "Task":
        return Violation("issuetype", "hook", "FOO does not accept Task tickets")
    return None
```

Installing or updating is then just:

```bash
pip install zaira-hooks-acme
pip install -U zaira-hooks-acme   # ship policy updates
pip uninstall zaira-hooks-acme    # remove
```

This is versioned, works with a private package index or a git URL, and
`pip install -U`/`pip uninstall` is the entire update/removal lifecycle —
no separate bundle-install machinery needed.

#### Shipping data alongside code

A hook package can bundle plain data files (an allow-list, a lookup
table, ...) as normal Python **package data** and read them via
`importlib.resources` — the same pattern this codebase already uses for
its own bundled skill files (`zaira/skills.py`):

```
zaira_hooks_acme/
  __init__.py
  policy.py
  allowed_fields.txt
  allowed_fields_FOO.txt
```

```toml
[tool.setuptools.package-data]
zaira_hooks_acme = ["*.txt"]
```

```python
# policy.py
from importlib.resources import files
from zaira.hooks import allowlist_from_file

_data = files("zaira_hooks_acme")
allowlist_from_file(
    _data / "allowed_fields.txt",
    per_project={"FOO": _data / "allowed_fields_FOO.txt"},
)
```

## Inspecting what's loaded

```bash
zaira hooks
```

Lists every hook package loaded this run and the directory containing its imported
Python module, when available (or says none are loaded).

## Worked example: restrict issue types per project

```python
# hooks/project_policy.py
from zaira.hooks import hook, HookPoint, CreateContext
from zaira.types import Violation

DENIED_TYPES = {"FOO": {"Task"}}


@hook(HookPoint.PRE_CREATE)
def restrict_issue_types(ctx: CreateContext) -> Violation | None:
    if ctx.issue_type in DENIED_TYPES.get(ctx.project, set()):
        return Violation(
            "issuetype",
            "hook",
            f"{ctx.project} does not accept {ctx.issue_type} tickets",
        )
    return None
```

```
$ zaira create ticket.md
Blocked: cannot create Task in FOO:
  FAIL  hook        issuetype
        FOO does not accept Task tickets

Use --no-check to skip validation.
```

Note this is a client-side guardrail — it stops `zaira create`, not the
Jira UI or API directly. Jira's own project issue-type schemes remain the
actual enforcement point if you need one that can't be bypassed.
