"""User-defined Python hook/plugin system for ticket lifecycle events.

A hook is a plain function registered against a named hook point with the
`@hook` decorator:

    from zaira.hooks import hook, HookPoint, CreateContext
    from zaira.types import Violation

    @hook(HookPoint.PRE_CREATE, project="FOO")
    def no_tasks(ctx: CreateContext) -> Violation | None:
        if ctx.issue_type == "Task":
            return Violation("issuetype", "hook", "FOO does not accept Task tickets")
        return None

Hook points (see HookPoint):
  - PRE_CREATE: runs before a ticket is created. Receives a CreateContext;
    may edit ctx.front_matter / ctx.description in place, and may return
    Violation(s) to block creation.
  - POST_CREATE: runs after a successful create, for side effects only
    (notifications, auto-linking, ...). ctx.key is set. Return value is
    ignored -- a post_create hook can't block anything that already happened.
  - PRE_WRITE: runs before `zaira edit`/`zaira transition -F` write fields
    to an existing ticket. Receives a FieldWriteContext (field name -> raw
    value, before ID-mapping); may return Violation(s) to block the write.
    This is where a field allow-list belongs -- see allowlist_from_file().
  - CHECK: runs wherever a ticket is validated (zaira check, and zaira
    transition's pre-transition validation against the target status).
    Receives (ticket, status); may return Violation(s).

A hook may return None (pass), a single Violation, or a list of them.
`Violation` (zaira.types) is `(field, check, message)` -- the same type
zaira check/transition already print, so hook failures report identically
to any other check.

## Non-blocking messages: note()

A Violation always blocks/fails. For something a hook wants to surface
that shouldn't -- a heads-up, a reminder, context worth a human's
attention -- call note() from inside the hook instead of (or alongside)
returning a Violation. A hook may call it any number of times:

    from zaira.hooks import note

    @hook(HookPoint.PRE_CREATE, project="FOO")
    def flag_cadence(ctx: CreateContext) -> None:
        if ctx.front_matter.get("Deployment Cadence") == "Monthly Release":
            note("Monthly Release: next deploy window opens the 15th")

Notes are printed by the calling command alongside whatever else it
reports, but never affect whether the command blocks or exits non-zero.

## Filtering by project/issue type

`@hook(point, project=..., issue_type=...)` accepts a single string or an
iterable of them; the hook is only invoked when the context's project
and/or issue type matches, so hooks don't need to open with a manual
`if ctx.project == "FOO": ...` guard:

    @hook(HookPoint.PRE_CREATE, project=["FOO", "BAR"], issue_type="Task")
    def ...

## Isolation and the `--no-check` escape hatch

A hook that raises is caught, reported to stderr as a warning, and
skipped -- it never crashes or blocks an otherwise valid ticket operation
beyond the one check it implements. `--no-check` (where the calling
command supports it) skips hooks entirely.

## Distribution -- two independent channels, both loaded every run

  1. Local files: ./hooks/*.py (repo-local) and CONFIG_DIR/hooks/*.py
     (per-user/per-machine). Each file is imported once per invocation;
     every @hook(...) call at module level registers. No packaging
     required -- good for quick, unshared policy.
  2. Installed pip packages that declare a "zaira.hooks" entry point
     pointing at a module; importing that module runs its @hook(...)
     registrations. This is the path for versioned, shareable policy --
     `pip install zaira-hooks-acme` picks it up with no zaira-side install
     step, `pip install -U` ships updates, `pip uninstall` removes it:

         # pyproject.toml of a hook package
         [project.entry-points."zaira.hooks"]
         acme_policy = "zaira_hooks_acme.policy"

     A hook package can bundle data alongside its code as normal Python
     package data (see zaira/skills.py for the same pattern already used
     in this codebase) and read it via importlib.resources -- e.g. a field
     allow-list shipped as a .txt resource, see allowlist_from_file().

`zaira hooks` lists what's loaded (files and packages) for any given run.
"""

import functools
import importlib.util
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, Protocol, cast, overload

from zaira.jira_client import CONFIG_DIR
from zaira.types import Violation

HOOKS_DIR = CONFIG_DIR / "hooks"
LOCAL_HOOKS_DIR = Path("hooks")
ENTRY_POINT_GROUP = "zaira.hooks"


class HookPoint(StrEnum):
    """Symbolic hook point names -- pass to @hook(...). Also plain strings
    (HookPoint.PRE_CREATE == "pre_create"), so a bare string still works."""

    PRE_CREATE = "pre_create"
    POST_CREATE = "post_create"
    PRE_WRITE = "pre_write"
    CHECK = "check"


HookResult = Violation | list[Violation] | None


@dataclass
class CreateContext:
    """Mutable context passed to PRE_CREATE/POST_CREATE hooks.

    pre_create hooks may edit `front_matter` (same shape as the YAML front
    matter parsed from the ticket file) and `description` in place before
    the ticket is built. `key` is unset during pre_create and filled in
    before post_create hooks run.
    """

    project: str
    issue_type: str
    front_matter: dict[str, Any]
    description: str = ""
    key: str | None = None


@dataclass
class FieldWriteContext:
    """Context passed to PRE_WRITE hooks: a write about to happen to an
    existing ticket, via `zaira edit` or `zaira transition -F`.

    `fields` maps human-readable field name -> raw value, exactly as given
    on the command line / in the --from YAML, before ID-mapping.
    """

    project: str
    key: str
    issue_type: str
    fields: dict[str, Any]


class PreCreateHook(Protocol):
    def __call__(self, ctx: CreateContext) -> HookResult: ...


class PostCreateHook(Protocol):
    def __call__(self, ctx: CreateContext) -> None: ...


class PreWriteHook(Protocol):
    def __call__(self, ctx: FieldWriteContext) -> HookResult: ...


class CheckHook(Protocol):
    def __call__(self, ticket: Mapping[str, Any], status: str) -> HookResult: ...


@dataclass
class _Registry:
    pre_create: list[PreCreateHook] = field(default_factory=list)
    post_create: list[PostCreateHook] = field(default_factory=list)
    pre_write: list[PreWriteHook] = field(default_factory=list)
    check: list[CheckHook] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    loaded: bool = False


_registry = _Registry()


def _as_set(value: str | Iterable[str] | None) -> set[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return {value}
    return set(value)


def _context_project_and_type(
    name: HookPoint, args: tuple[Any, ...]
) -> tuple[str, str]:
    """Extract (project, issue_type) from a hook call's positional args."""
    if name is HookPoint.CHECK:
        ticket = cast(Mapping[str, Any], args[0])
        key = str(ticket.get("key", ""))
        project = key.split("-", 1)[0] if "-" in key else ""
        issue_type = str(ticket.get("issuetype", ""))
        return project, issue_type
    ctx = args[0]
    return getattr(ctx, "project", ""), getattr(ctx, "issue_type", "")


def _apply_filter(
    name: HookPoint,
    fn: Callable[..., Any],
    projects: set[str] | None,
    issue_types: set[str] | None,
) -> Callable[..., Any]:
    if projects is None and issue_types is None:
        return fn

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        project, issue_type = _context_project_and_type(name, args)
        if projects is not None and project not in projects:
            return None
        if issue_types is not None and issue_type not in issue_types:
            return None
        return fn(*args, **kwargs)

    return wrapper


@overload
def hook(
    name: Literal[HookPoint.PRE_CREATE],
    *,
    project: str | Iterable[str] | None = None,
    issue_type: str | Iterable[str] | None = None,
) -> Callable[[PreCreateHook], PreCreateHook]: ...
@overload
def hook(
    name: Literal[HookPoint.POST_CREATE],
    *,
    project: str | Iterable[str] | None = None,
    issue_type: str | Iterable[str] | None = None,
) -> Callable[[PostCreateHook], PostCreateHook]: ...
@overload
def hook(
    name: Literal[HookPoint.PRE_WRITE],
    *,
    project: str | Iterable[str] | None = None,
    issue_type: str | Iterable[str] | None = None,
) -> Callable[[PreWriteHook], PreWriteHook]: ...
@overload
def hook(
    name: Literal[HookPoint.CHECK],
    *,
    project: str | Iterable[str] | None = None,
    issue_type: str | Iterable[str] | None = None,
) -> Callable[[CheckHook], CheckHook]: ...
def hook(
    name: HookPoint,
    *,
    project: str | Iterable[str] | None = None,
    issue_type: str | Iterable[str] | None = None,
) -> Callable[[Any], Any]:
    """Decorator: register a function under a hook point name.

    The overloads above type-check the decorated function's signature
    against the hook point named -- e.g. @hook(HookPoint.PRE_CREATE)
    requires a `(ctx: CreateContext) -> Violation | list[Violation] | None`
    callable.

    `project=`/`issue_type=` (a single string or an iterable of them)
    narrow when the hook is invoked at all -- the decorated function is
    only called when the context's project/issue type matches, so hooks
    don't need to open with a manual `if ctx.project == "FOO": ...` guard.
    """
    projects = _as_set(project)
    issue_types = _as_set(issue_type)

    def decorator(fn: Any) -> Any:
        target = _apply_filter(name, fn, projects, issue_types)
        if name == HookPoint.PRE_CREATE:
            _registry.pre_create.append(cast(PreCreateHook, target))
        elif name == HookPoint.POST_CREATE:
            _registry.post_create.append(cast(PostCreateHook, target))
        elif name == HookPoint.PRE_WRITE:
            _registry.pre_write.append(cast(PreWriteHook, target))
        elif name == HookPoint.CHECK:
            _registry.check.append(cast(CheckHook, target))
        else:
            raise ValueError(f"Unknown hook point: {name!r}")
        return fn

    return decorator


def _hook_name(fn: Callable[..., Any]) -> str:
    return f"{getattr(fn, '__module__', '?')}.{getattr(fn, '__qualname__', getattr(fn, '__name__', '?'))}"


def _exec_file(path: Path) -> None:
    module_name = f"zaira_hook_{path.stem}_{abs(hash(str(path)))}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            return
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        _registry.sources.append(f"file: {path}")
    except Exception as e:
        print(f"warning: failed to load hook file {path}: {e}", file=sys.stderr)


def _load_entry_point(ep: EntryPoint) -> None:
    try:
        ep.load()  # importing the target module runs its @hook(...) registrations
        _registry.sources.append(f"package: {ep.name} ({ep.value})")
    except Exception as e:
        print(f"warning: failed to load hook package '{ep.name}': {e}", file=sys.stderr)


def load_hooks() -> None:
    """Discover and load hooks: local files, then installed pip packages.

    Idempotent -- safe to call from every command that consults hooks.
    """
    if _registry.loaded:
        return
    _registry.loaded = True

    for hooks_dir in (LOCAL_HOOKS_DIR, HOOKS_DIR):
        if hooks_dir.is_dir():
            for path in sorted(hooks_dir.glob("*.py")):
                _exec_file(path)

    try:
        eps = entry_points(group=ENTRY_POINT_GROUP)
    except Exception as e:
        print(
            f"warning: failed to query {ENTRY_POINT_GROUP!r} entry points: {e}",
            file=sys.stderr,
        )
        eps = ()
    for ep in eps:
        _load_entry_point(ep)


def _normalize(result: HookResult) -> list[Violation]:
    if result is None:
        return []
    return result if isinstance(result, list) else [result]


def run_pre_create_hooks(ctx: CreateContext) -> list[Violation]:
    """Run all PRE_CREATE hooks against ctx, collecting violations.

    Hooks may mutate ctx.front_matter / ctx.description in place. A hook
    that raises is reported to stderr and skipped, never propagated.
    """
    load_hooks()
    violations: list[Violation] = []
    for fn in _registry.pre_create:
        try:
            violations.extend(_normalize(fn(ctx)))
        except Exception as e:
            print(f"warning: hook {_hook_name(fn)} raised: {e}", file=sys.stderr)
    return violations


def run_post_create_hooks(ctx: CreateContext) -> None:
    """Run all POST_CREATE hooks for side effects. Never raises."""
    load_hooks()
    for fn in _registry.post_create:
        try:
            fn(ctx)
        except Exception as e:
            print(f"warning: hook {_hook_name(fn)} raised: {e}", file=sys.stderr)


def run_pre_write_hooks(ctx: FieldWriteContext) -> list[Violation]:
    """Run all PRE_WRITE hooks, collecting violations. Never raises."""
    load_hooks()
    violations: list[Violation] = []
    for fn in _registry.pre_write:
        try:
            violations.extend(_normalize(fn(ctx)))
        except Exception as e:
            print(f"warning: hook {_hook_name(fn)} raised: {e}", file=sys.stderr)
    return violations


def run_check_hooks(ticket: Mapping[str, Any], status: str) -> list[Violation]:
    """Run all CHECK hooks, collecting violations. Never raises."""
    load_hooks()
    violations: list[Violation] = []
    for fn in _registry.check:
        try:
            violations.extend(_normalize(fn(ticket, status)))
        except Exception as e:
            print(f"warning: hook {_hook_name(fn)} raised: {e}", file=sys.stderr)
    return violations


def hooks_enabled() -> bool:
    """True if any hook (file- or package-based) is registered."""
    load_hooks()
    return bool(
        _registry.pre_create
        or _registry.post_create
        or _registry.pre_write
        or _registry.check
    )


def loaded_sources() -> list[str]:
    """Human-readable list of hook sources loaded this run, for `zaira hooks`."""
    load_hooks()
    return list(_registry.sources)


def note(message: str) -> None:
    """Queue a free-text message from inside a hook.

    Unlike a Violation, a note is not tied to a field/check and never
    blocks or fails anything -- it's just surfaced to the user alongside
    whatever else the command reports. A single hook call may emit any
    number of notes. Call from any hook point:

        @hook(HookPoint.PRE_CREATE, project="FOO")
        def flag_cadence(ctx: CreateContext) -> None:
            if ctx.front_matter.get("Deployment Cadence") == "Monthly Release":
                note("Monthly Release: next deploy window opens the 15th")

    The calling command (create/edit/transition/check) drains and prints
    these via drain_notes() after running hooks; you don't call that
    yourself.
    """
    _registry.notes.append(message)


def drain_notes() -> list[str]:
    """Return and clear all notes queued via note() since the last drain.

    Called once by each command after it finishes running the relevant
    hooks for that command (pre_create+post_create for create, pre_write
    for edit/transition's field write, check for check/transition).
    """
    notes = list(_registry.notes)
    _registry.notes.clear()
    return notes


def reset_registry() -> None:
    """Clear registered hooks and loaded-module state. For tests only."""
    global _registry
    _registry = _Registry()


def _read_field_list(source: Any) -> set[str]:
    """Read a plain-text field list: one name per line, '#' comments and
    blank lines ignored. `source` is anything with .read_text() -- a
    pathlib.Path, or an importlib.resources Traversable for package data."""
    if isinstance(source, str):
        source = Path(source)
    text = source.read_text()
    return {
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def allowlist_from_file(
    path: Any,
    *,
    per_project: Mapping[str, Any] | None = None,
    register: bool = True,
) -> Callable[[FieldWriteContext], list[Violation]]:
    """Build (and, by default, register) a PRE_WRITE hook enforcing a field
    allow-list loaded from file(s) -- the hook equivalent of the old
    allowed_fields.txt / allowed_fields_{PROJECT}.txt.

    `path` is the global allow-list: plain text, one field name per line,
    '#' comments and blank lines ignored. `per_project` optionally maps
    project key -> another such file, unioned with the global list for
    that project. Both accept a pathlib.Path or an importlib.resources
    Traversable, so a hook package can ship its allow-list as package data:

        from importlib.resources import files
        from zaira.hooks import allowlist_from_file

        data = files("zaira_hooks_acme")
        allowlist_from_file(data / "allowed_fields.txt",
                             per_project={"FOO": data / "allowed_fields_FOO.txt"})

    Pass register=False to get the callable back without auto-registering
    it, e.g. to compose it inside your own PRE_WRITE hook.
    """
    global_set = _read_field_list(path)
    project_sets = {
        proj: _read_field_list(p) for proj, p in (per_project or {}).items()
    }

    def check(ctx: FieldWriteContext) -> list[Violation]:
        allowed = global_set | project_sets.get(ctx.project, set())
        if not allowed:
            return []
        allowed_lower = {a.lower(): a for a in allowed}
        violations = []
        for name in ctx.fields:
            if name.lower() not in allowed_lower:
                from zaira.util import fuzzy_match

                similar = fuzzy_match(name.lower(), list(allowed_lower.keys()))
                msg = f"{name!r} is not an allowed field"
                if similar:
                    suggestions = ", ".join(allowed_lower[s] for s in similar)
                    msg += f". Did you mean: {suggestions}?"
                violations.append(Violation(name, "allowed_fields", msg))
        return violations

    if register:
        hook(HookPoint.PRE_WRITE)(check)
    return check
