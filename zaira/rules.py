"""Rules engine for ticket validation."""

import re
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


def _apply_rules(ticket, rule_block):
    """Apply a single rule block and return violations.

    A rule block can contain: required, non_empty, contains, not_contains,
    subtask_types.
    """
    violations = []

    for required_type in rule_block.get("subtask_types", []):
        subtasks = ticket.get("subtasks", [])
        if not any(st.get("issuetype") == required_type for st in subtasks):
            violations.append(Violation(
                required_type, "subtask_types",
                f"missing subtask of type \"{required_type}\"",
            ))

    for field in rule_block.get("required", []):
        found, value = _get_field_value(ticket, field)
        if not found or value is None:
            violations.append(Violation(field, "required", f"{field} is missing or null"))

    for field in rule_block.get("non_empty", []):
        found, value = _get_field_value(ticket, field)
        if not found or value is None:
            violations.append(Violation(field, "non_empty", f"{field} is missing or null"))
        elif value == "" or value == []:
            violations.append(Violation(field, "non_empty", f"{field} is empty"))

    for field, substring in rule_block.get("contains", {}).items():
        found, value = _get_field_value(ticket, field)
        if not found or value is None:
            violations.append(Violation(field, "contains", f"{field} is missing or null"))
        elif not isinstance(value, str) or substring not in value:
            violations.append(Violation(field, "contains", f'{field} must contain "{substring}"'))

    for field, substring in rule_block.get("not_contains", {}).items():
        found, value = _get_field_value(ticket, field)
        if found and isinstance(value, str) and substring in value:
            violations.append(Violation(field, "not_contains", f'{field} must not contain "{substring}"'))

    for field, pattern in rule_block.get("matches", {}).items():
        found, value = _get_field_value(ticket, field)
        if not found or value is None:
            violations.append(Violation(field, "matches", f"{field} is missing or null"))
        elif not isinstance(value, str) or not re.search(pattern, value):
            violations.append(Violation(field, "matches", f'{field} must match /{pattern}/'))

    for field, pattern in rule_block.get("not_matches", {}).items():
        found, value = _get_field_value(ticket, field)
        if found and isinstance(value, str) and re.search(pattern, value):
            violations.append(Violation(field, "not_matches", f'{field} must not match /{pattern}/'))

    return violations


def _match_condition(ticket, match, status):
    """Check if all field conditions in a match dict are satisfied.

    For scalar fields, compares as strings.
    For list fields (components, labels), checks membership.
    The special field 'status' uses the overridden status if provided.
    """
    for field, expected in match.items():
        if field.lower() == "status":
            actual = status
        else:
            found, actual = _get_field_value(ticket, field)
            if not found:
                return False
        if isinstance(actual, list):
            if str(expected) not in [str(v) for v in actual]:
                return False
        elif str(actual) != str(expected):
            return False
    return True


def check_ticket(ticket, rules, status=None):
    """Check a ticket dict against rules. Returns list of Violation.

    If status is given, use it instead of ticket's current status (for
    validating a transition target before it happens).
    """
    if status is None:
        status = ticket.get("status", "")

    # Base rules
    violations = _apply_rules(ticket, rules)

    # when.<status> rules (sugar for status-conditional)
    when = rules.get("when", {})
    status_rules = when.get(status, {})
    if status_rules:
        violations.extend(_apply_rules(ticket, status_rules))

    # if/then rules
    for cond in rules.get("if", []):
        match = cond.get("match", {})
        then = cond.get("then", {})
        if match and _match_condition(ticket, match, status):
            violations.extend(_apply_rules(ticket, then))

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
        ticket = get_ticket(key, full=True, include_custom=True)
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
                if v.check in ("contains", "not_contains", "matches", "not_matches", "subtask_types"):
                    print(f"        {v.message}")
        else:
            print("  ok")

    if any_fail:
        sys.exit(1)
