"""Transition Jira tickets between statuses."""

import argparse
import sys
from typing import Any

from zaira.jira_client import format_jira_error, get_jira, get_jira_site


def get_transitions(key: str, expand: str | None = None) -> list[dict]:
    """Get available transitions for a ticket.

    Args:
        key: Ticket key (e.g., PROJ-123)
        expand: Optional Jira expand param. Pass "transitions.fields" to
            include the fields shown on each transition's screen.
    """
    jira = get_jira()
    try:
        if expand:
            return jira.transitions(key, expand=expand)
        return jira.transitions(key)
    except Exception as e:
        print(
            f"Error getting transitions for {key}: {format_jira_error(e)}",
            file=sys.stderr,
        )
        return []


def _find_transition(transitions: list[dict], status: str) -> dict | None:
    """Find the transition matching a transition name or target status name (case-insensitive)."""
    status_lower = status.lower()
    for t in transitions:
        if t["name"].lower() == status_lower or t["to"]["name"].lower() == status_lower:
            return t
    return None


def _print_unmatched_status(status: str, transitions: list[dict]) -> None:
    print(f"Error: No transition to '{status}' available", file=sys.stderr)
    print("\nAvailable transitions:", file=sys.stderr)
    for t in transitions:
        print(f"  - {t['name']} → {t['to']['name']}", file=sys.stderr)


def transition_ticket(
    key: str,
    status: str,
    fields: dict[str, Any] | None = None,
    comment: str | None = None,
) -> bool:
    """Transition a ticket to a new status.

    Args:
        key: Ticket key (e.g., PROJ-123)
        status: Target status name or transition name
        fields: Optional dict of field_id -> value to set during transition
        comment: Optional comment to include with the transition

    Returns:
        True if successful, False otherwise
    """
    jira = get_jira()
    try:
        transitions = jira.transitions(key)
        match = _find_transition(transitions, status)
        if not match:
            _print_unmatched_status(status, transitions)
            return False

        jira.transition_issue(key, match["id"], fields=fields or {}, comment=comment)
        return True
    except Exception as e:
        msg = format_jira_error(e)
        print(f"Error transitioning {key}: {msg}", file=sys.stderr)
        _suggest_field_names(msg)
        return False


def _suggest_field_names(msg: str) -> None:
    """If the error message references customfield_NNNNN IDs, print friendly names."""
    import re

    from zaira.info import get_field_name

    seen: set[str] = set()
    for fid in re.findall(r"customfield_\d+", msg):
        if fid in seen:
            continue
        seen.add(fid)
        try:
            name = get_field_name(fid)
        except Exception:
            name = None
        if name and name != fid:
            print(f"  Did you mean: {name!r} (instead of {fid})?", file=sys.stderr)


def _format_field_value(value: Any) -> str:
    """Render a --field value (as produced by edit.parse_field_args) for display."""
    if isinstance(value, dict):
        return str(value.get("name") or value.get("value") or value)
    if isinstance(value, list):
        return ", ".join(_format_field_value(v) for v in value)
    return str(value)


def _print_transition_fields(
    fields: dict, provided: dict[str, Any] | None = None
) -> None:
    """Print field definitions as parsed by info._parse_editmeta_response.

    `provided` is the field_id -> value dict (as parsed from --field args, if
    any); each field is annotated with the value that would be set, or
    "(not set)" so it's obvious what's still missing.
    """
    if not fields:
        print("  (no fields on this transition screen)")
        return
    provided = provided or {}
    for fname, fdef in fields.items():
        print(f"  {fname}")
        print(f"    id:       {fdef['id']}")
        print(f"    type:     {fdef['type']}")
        if fdef.get("required"):
            print("    required: True")
        values = fdef.get("allowedValues")
        if values:
            print(f"    values:   {', '.join(str(v) for v in values)}")
        if fdef["id"] in provided:
            print(f"    value:    {_format_field_value(provided[fdef['id']])}")
        else:
            print("    value:    (not set)")


def _parse_transition_fields(
    key: str, project: str, field_args: list[str], issue_type: str | None = None
) -> dict:
    """Parse --field NAME=VALUE args into a field_id -> value dict.

    `issue_type` may be passed in if already resolved by the caller, to
    avoid a second `jira.issue()` round trip.
    """
    if not field_args:
        return {}
    from zaira.edit import parse_field_args
    from zaira.info import ensure_editmeta

    if issue_type is None:
        issue = get_jira().issue(key, fields="issuetype")
        issue_type = issue.fields.issuetype.name
    ensure_editmeta(key, issue_type)
    return parse_field_args(field_args, project=project, issue_type=issue_type)


def transition_command(args: argparse.Namespace) -> None:
    """Handle transition subcommand."""
    key = args.key.upper()
    jira_site = get_jira_site()

    if args.list:
        transitions = get_transitions(key)
        if transitions:
            print(f"Available transitions for {key}:")
            for t in transitions:
                print(f"  - {t['name']} → {t['to']['name']}")
        return

    if not args.status:
        print("Error: Specify a status or use --list", file=sys.stderr)
        sys.exit(1)

    status = args.status
    field_args = getattr(args, "field", None) or []
    project = key.split("-")[0]

    if getattr(args, "dry_run", False):
        # Non-mutating: peek at the real transition screen (and any values
        # --field would set) straight from Jira, without the hook gates
        # below — --no-check isn't needed.
        fields = _parse_transition_fields(key, project, field_args)
        transitions = get_transitions(key, expand="transitions.fields")
        match = _find_transition(transitions, status) if transitions else None
        if not match:
            if transitions:
                _print_unmatched_status(status, transitions)
            sys.exit(1)

        print(f"Would transition {key} to '{status}'")
        comment = getattr(args, "comment", None)
        if comment:
            print(f"  With comment: {comment}")

        from zaira.info import _parse_editmeta_response

        print("\nFields on this transition screen:")
        _print_transition_fields(_parse_editmeta_response(match), provided=fields)
        return

    # Resolve issue type once, up front, if we'll need it below (for the
    # pre_write hook check and/or field-ID mapping).
    issue_type = None
    if field_args:
        issue = get_jira().issue(key, fields="issuetype")
        issue_type = issue.fields.issuetype.name

    # Run "pre_write" hooks (zaira.hooks) against the raw field names/values
    # BEFORE parsing (unless --no-check is set) -- must happen before
    # mapping field names to IDs.
    if field_args and not getattr(args, "no_check", False):
        from zaira.hooks import FieldWriteContext, drain_notes, run_pre_write_hooks

        write_fields: dict[str, Any] = {}
        for arg in field_args:
            if "=" in arg:
                name, _, value = arg.partition("=")
                write_fields[name.strip()] = value

        violations = run_pre_write_hooks(
            FieldWriteContext(
                project=project,
                key=key,
                issue_type=issue_type or "",
                fields=write_fields,
            )
        )
        for msg in drain_notes():
            print(f"  NOTE  {msg}")
        if violations:
            print("Error: field write blocked:", file=sys.stderr)
            for v in violations:
                print(f"  FAIL  {v.check:<11s} {v.field}", file=sys.stderr)
                print(f"        {v.message}", file=sys.stderr)
            print("\nUse --no-check to skip validation.", file=sys.stderr)
            sys.exit(1)

    fields = _parse_transition_fields(key, project, field_args, issue_type=issue_type)

    # Run "check" hooks (zaira.hooks) against the transition's target status
    # before transitioning (unless --no-check is set).
    if not getattr(args, "no_check", False):
        from zaira.check import validate_transition
        from zaira.export import get_ticket
        from zaira.hooks import drain_notes, hooks_enabled

        violations = []
        available_transitions = []

        if hooks_enabled():
            ticket = get_ticket(key, full=True, include_custom=True)
            if ticket:
                # Resolve transition name (e.g. "Start Implementation") to
                # the actual target status name (e.g. "Implementing") so
                # check hooks compare status-to-status.
                target_status = status
                available_transitions = get_transitions(key)
                match = _find_transition(available_transitions, status)
                if match:
                    target_status = match["to"]["name"]
                violations.extend(validate_transition(ticket, target_status))

        for msg in drain_notes():
            print(f"  NOTE  {msg}")
        if violations:
            print(
                f"Blocked: {key} fails checks for '{status}':",
                file=sys.stderr,
            )
            for v in violations:
                print(f"  FAIL  {v.check:<11s} {v.field}", file=sys.stderr)
                print(f"        {v.message}", file=sys.stderr)
            print("\nUse --no-check to skip validation.", file=sys.stderr)
            sys.exit(1)

    comment = getattr(args, "comment", None)

    if transition_ticket(key, status, fields=fields, comment=comment):
        print(f"Transitioned {key}")
        print(f"View at: https://{jira_site}/browse/{key}")
        from zaira.activity_log import record

        record("transition", key, f"→ {status}")
    else:
        sys.exit(1)
