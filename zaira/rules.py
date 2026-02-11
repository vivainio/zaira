"""Rules engine for ticket validation."""

import sys
from collections import namedtuple
from pathlib import Path

import yaml

from zaira.export import get_ticket

Violation = namedtuple("Violation", ["field", "check", "message"])


def load_rules(path="rules.yaml"):
    """Load YAML rules file. Returns dict keyed by issue type name."""
    p = Path(path)
    if not p.exists():
        print(f"Rules file not found: {p}", file=sys.stderr)
        sys.exit(1)
    with open(p) as f:
        return yaml.safe_load(f)


def _get_field_value(ticket, field_name):
    """Look up a field by human-readable name in ticket dict.

    Checks standard ticket keys first, then custom_fields.
    Returns (found: bool, value).
    """
    # Normalize for case-insensitive lookup on standard fields
    lower = field_name.lower()
    standard_map = {k.lower(): k for k in ticket if k != "custom_fields"}
    if lower in standard_map:
        return True, ticket[standard_map[lower]]

    custom = ticket.get("custom_fields", {})
    if field_name in custom:
        return True, custom[field_name]

    return False, None


def check_ticket(ticket, rules, status=None):
    """Check a ticket dict against rules. Returns list of Violation.

    If status is given, use it instead of ticket's current status (for
    validating a transition target before it happens).
    """
    violations = []

    if status is None:
        status = ticket.get("status", "")
    base_required = rules.get("required", [])
    base_non_empty = rules.get("non_empty", [])

    base_contains = rules.get("contains", {})

    # Merge when-rules for current status
    when = rules.get("when", {})
    status_rules = when.get(status, {})
    all_required = base_required + status_rules.get("required", [])
    all_non_empty = base_non_empty + status_rules.get("non_empty", [])
    all_contains = {**base_contains, **status_rules.get("contains", {})}
    all_not_contains = {**rules.get("not_contains", {}), **status_rules.get("not_contains", {})}

    for field in all_required:
        found, value = _get_field_value(ticket, field)
        if not found or value is None:
            violations.append(Violation(field, "required", f"{field} is missing or null"))

    for field in all_non_empty:
        found, value = _get_field_value(ticket, field)
        if not found or value is None:
            violations.append(Violation(field, "non_empty", f"{field} is missing or null"))
        elif value == "" or value == []:
            violations.append(Violation(field, "non_empty", f"{field} is empty"))

    for field, substring in all_contains.items():
        found, value = _get_field_value(ticket, field)
        if not found or value is None:
            violations.append(Violation(field, "contains", f"{field} is missing or null"))
        elif not isinstance(value, str) or substring not in value:
            violations.append(Violation(field, "contains", f'{field} must contain "{substring}"'))

    for field, substring in all_not_contains.items():
        found, value = _get_field_value(ticket, field)
        if found and isinstance(value, str) and substring in value:
            violations.append(Violation(field, "not_contains", f'{field} must not contain "{substring}"'))

    return violations


def try_load_rules(path="rules.yaml"):
    """Load rules file, returning None if it doesn't exist."""
    p = Path(path)
    if not p.exists():
        return None
    with open(p) as f:
        return yaml.safe_load(f)


def validate_transition(ticket, all_rules, target_status):
    """Check ticket against rules for target_status.

    Returns list of Violation, or empty list if no rules apply.
    """
    issue_type = ticket.get("issuetype", "")
    type_rules = all_rules.get(issue_type)
    if not type_rules:
        return []
    return check_ticket(ticket, type_rules, status=target_status)


def check_command(args):
    """CLI handler: load rules, fetch tickets, run checks, print report."""
    rules_path = getattr(args, "rules", "rules.yaml")
    all_rules = load_rules(rules_path)
    keys = args.keys

    any_fail = False
    for key in keys:
        ticket = get_ticket(key, include_custom=True)
        if not ticket:
            print(f"{key}: could not fetch ticket", file=sys.stderr)
            any_fail = True
            continue

        issue_type = ticket.get("issuetype", "Unknown")
        status = ticket.get("status", "Unknown")
        type_rules = all_rules.get(issue_type)

        print(f"{key} ({issue_type} / {status})")
        if not type_rules:
            print("  ok (no rules for this type)")
            continue

        violations = check_ticket(ticket, type_rules)
        if violations:
            any_fail = True
            for v in violations:
                print(f"  FAIL  {v.check:<11s} {v.field}")
                if v.check == "contains":
                    print(f"        {v.message}")
        else:
            print("  ok")

    if any_fail:
        sys.exit(1)
