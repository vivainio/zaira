"""Rules engine for ticket validation."""

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Mapping, NamedTuple, cast

import yaml

from zaira.export import get_ticket
from zaira.jira_client import CONFIG_DIR
from zaira.types import FieldError, RuleBlock, RulesConfig


class Violation(NamedTuple):
    """A failed ticket rule."""

    field: str
    check: str
    message: str


ALLOWED_FIELDS_FILE = CONFIG_DIR / "rules" / "allowed_fields.txt"


def _find_rules_file(path: str | Path = "rules.yaml") -> Path | None:
    """Search for rules file: explicit path, then cwd, then the zaira config dir."""
    from zaira.jira_client import CONFIG_DIR

    p = Path(path)
    if p.is_absolute() or path != "rules.yaml":
        return p if p.exists() else None
    if p.exists():
        return p
    config_path = CONFIG_DIR / "rules" / "rules.yaml"
    if config_path.exists():
        return config_path
    return None


def _merge_rule_block(base: RuleBlock, override: RuleBlock) -> RuleBlock:
    """Merge override rule block on top of base. Returns merged dict."""
    result = cast(RuleBlock, dict(base))
    for key, val in cast(dict[str, Any], override).items():
        if key in ("required", "non_empty", "subtask_types"):
            base_list = result.get(key, [])
            result[key] = list(dict.fromkeys(base_list + val))
        elif key in (
            "contains",
            "not_contains",
            "matches",
            "not_matches",
            "one_of",
            "not_one_of",
            "count_matches",
            "sections_present",
        ):
            result[key] = {**result.get(key, {}), **val}
        elif key == "no_open_linked":
            result[key] = result.get(key, []) + val
        elif key == "when":
            base_when = dict(result.get("when", {}))
            for status, status_block in val.items():
                if status in base_when:
                    base_when[status] = _merge_rule_block(
                        base_when[status], status_block
                    )
                else:
                    base_when[status] = status_block
            result["when"] = base_when
        elif key == "if":
            result["if"] = result.get("if", []) + val
        elif key == "valid_transitions":
            result["valid_transitions"] = {**result.get("valid_transitions", {}), **val}
        else:
            cast(dict[str, Any], result)[key] = val
    return result


def _merge_all_rules(base: RulesConfig, override: RulesConfig) -> RulesConfig:
    """Merge override on top of base at the top level (issue-type keyed)."""
    result = dict(base)
    for issue_type, type_rules in override.items():
        if issue_type in result:
            result[issue_type] = _merge_rule_block(result[issue_type], type_rules)
        else:
            result[issue_type] = type_rules
    return result


def _load_rules_file(path: Path, seen: frozenset[Path]) -> RulesConfig:
    """Load a YAML rules file, following import chains with cycle detection."""
    abs_path = path.resolve()
    if abs_path in seen:
        raise ValueError(f"Import cycle detected: {path}")
    seen = seen | {abs_path}
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Rules file must contain a mapping: {path}")
    data = cast(dict[str, Any], raw)
    import_str = data.pop("import", None)
    if import_str is None:
        return cast(RulesConfig, data)
    import_path = (path.parent / import_str).resolve()
    if not import_path.exists():
        raise FileNotFoundError(
            f"Import not found: {import_path} (imported from {path})"
        )
    base = _load_rules_file(import_path, seen)
    return _merge_all_rules(base, cast(RulesConfig, data))


def load_rules(path: str | Path = "rules.yaml") -> RulesConfig:
    """Load YAML rules file. Returns dict keyed by issue type name."""
    from zaira.jira_client import CONFIG_DIR

    p = _find_rules_file(path)
    if not p:
        print(
            f"Rules file not found: {path} (also checked {CONFIG_DIR / 'rules' / 'rules.yaml'})",
            file=sys.stderr,
        )
        sys.exit(1)
    return _load_rules_file(p, frozenset())


def _get_field_value(ticket: Mapping[str, Any], field_name: str) -> tuple[bool, Any]:
    """Look up a field by human-readable name in ticket dict.

    Checks standard ticket keys first, then custom_fields.
    Returns (found: bool, value).
    """
    # Normalize for case-insensitive lookup on standard fields
    lower = field_name.lower()
    standard_map = {k.lower(): k for k in ticket if k != "custom_fields"}
    if lower in standard_map:
        return True, ticket[standard_map[lower]]

    # Try without spaces (e.g. "Fix Versions" -> "fixversions")
    collapsed = lower.replace(" ", "")
    if collapsed in standard_map:
        return True, ticket[standard_map[collapsed]]

    custom = ticket.get("custom_fields", {})
    if field_name in custom:
        return True, custom[field_name]

    return False, None


def _apply_rules(ticket: Mapping[str, Any], rule_block: RuleBlock) -> list[Violation]:
    """Apply a single rule block and return violations.

    A rule block can contain: required, non_empty, contains, not_contains,
    subtask_types.
    """
    violations = []

    for required_type in rule_block.get("subtask_types", []):
        subtasks = ticket.get("subtasks", [])
        if not any(st.get("issuetype") == required_type for st in subtasks):
            violations.append(
                Violation(
                    required_type,
                    "subtask_types",
                    f'missing subtask of type "{required_type}"',
                )
            )

    for field in rule_block.get("required", []):
        found, value = _get_field_value(ticket, field)
        if not found or value is None:
            violations.append(
                Violation(field, "required", f"{field} is missing or null")
            )

    for field in rule_block.get("non_empty", []):
        found, value = _get_field_value(ticket, field)
        if not found or value is None:
            violations.append(
                Violation(field, "non_empty", f"{field} is missing or null")
            )
        elif value == "" or value == []:
            violations.append(Violation(field, "non_empty", f"{field} is empty"))

    for field, substrings in rule_block.get("contains", {}).items():
        found, value = _get_field_value(ticket, field)
        for sub in substrings if isinstance(substrings, list) else [substrings]:
            if not found or value is None:
                violations.append(
                    Violation(field, "contains", f"{field} is missing or null")
                )
            elif not isinstance(value, str) or sub not in value:
                violations.append(
                    Violation(field, "contains", f'{field} must contain "{sub}"')
                )

    for field, substrings in rule_block.get("not_contains", {}).items():
        found, value = _get_field_value(ticket, field)
        for sub in substrings if isinstance(substrings, list) else [substrings]:
            if found and isinstance(value, str) and sub in value:
                violations.append(
                    Violation(
                        field, "not_contains", f'{field} must not contain "{sub}"'
                    )
                )

    for field, patterns in rule_block.get("matches", {}).items():
        found, value = _get_field_value(ticket, field)
        for pat in patterns if isinstance(patterns, list) else [patterns]:
            if not found or value is None:
                violations.append(
                    Violation(field, "matches", f"{field} is missing or null")
                )
            elif not isinstance(value, str) or not re.search(pat, value):
                violations.append(
                    Violation(field, "matches", f"{field} must match /{pat}/")
                )

    for field, patterns in rule_block.get("not_matches", {}).items():
        found, value = _get_field_value(ticket, field)
        for pat in patterns if isinstance(patterns, list) else [patterns]:
            if found and isinstance(value, str) and re.search(pat, value):
                violations.append(
                    Violation(field, "not_matches", f"{field} must not match /{pat}/")
                )

    for field, allowed in rule_block.get("one_of", {}).items():
        found, value = _get_field_value(ticket, field)
        if not found or value is None:
            violations.append(Violation(field, "one_of", f"{field} is missing or null"))
        elif isinstance(value, list):
            bad = [str(v) for v in value if str(v) not in [str(a) for a in allowed]]
            if bad:
                violations.append(
                    Violation(
                        field,
                        "one_of",
                        f"{field} has invalid values: {', '.join(bad)} (allowed: {', '.join(str(a) for a in allowed)})",
                    )
                )
        elif str(value) not in [str(a) for a in allowed]:
            violations.append(
                Violation(
                    field,
                    "one_of",
                    f'{field} is "{value}" (allowed: {", ".join(str(a) for a in allowed)})',
                )
            )

    for field, spec in rule_block.get("count_matches", {}).items():
        found, value = _get_field_value(ticket, field)
        pattern = spec.get("pattern", "")
        min_count = spec.get("min", 1)
        max_count = spec.get("max")
        if not found or value is None:
            violations.append(
                Violation(field, "count_matches", f"{field} is missing or null")
            )
        elif not isinstance(value, str):
            violations.append(
                Violation(field, "count_matches", f"{field} is not a string")
            )
        else:
            count = len(re.findall(pattern, value))
            if count < min_count:
                violations.append(
                    Violation(
                        field,
                        "count_matches",
                        f"{field} has {count} matches for /{pattern}/ (need >= {min_count})",
                    )
                )
            elif max_count is not None and count > max_count:
                violations.append(
                    Violation(
                        field,
                        "count_matches",
                        f"{field} has {count} matches for /{pattern}/ (need <= {max_count})",
                    )
                )

    for spec in rule_block.get("no_open_linked", []):
        linked_type = spec.get("type")
        linked_priorities = spec.get("priority", [])
        if isinstance(linked_priorities, str):
            linked_priorities = [linked_priorities]
        for link in ticket.get("issuelinks", []):
            linked_key = link.get("key")
            try:
                linked_ticket = get_ticket(linked_key, full=True)
            except Exception:
                continue
            if not linked_ticket:
                continue
            if linked_type and linked_ticket.get("issuetype") != linked_type:
                continue
            if (
                linked_priorities
                and linked_ticket.get("priority") not in linked_priorities
            ):
                continue
            status_cat = linked_ticket.get("statusCategory", "")
            if status_cat != "Done":
                violations.append(
                    Violation(
                        "issuelinks",
                        "no_open_linked",
                        f"linked {linked_ticket.get('issuetype')} {linked_key} ({linked_ticket.get('priority')}) is open: {linked_ticket.get('status')}",
                    )
                )

    for field, sections in rule_block.get("sections_present", {}).items():
        found, value = _get_field_value(ticket, field)
        if not found or value is None:
            violations.append(
                Violation(field, "sections_present", f"{field} is missing or null")
            )
        elif not isinstance(value, str):
            violations.append(
                Violation(field, "sections_present", f"{field} is not a string")
            )
        else:
            for section in sections:
                # Match markdown (## Section), Jira wiki (h2. Section), or plain heading patterns
                esc = re.escape(section)
                pat = rf"(?mi)(^#{{1,6}}\s+{esc}\b|^h[1-6]\.\s+{esc}\b)"
                if not re.search(pat, value):
                    violations.append(
                        Violation(
                            field,
                            "sections_present",
                            f'{field} is missing section "{section}"',
                        )
                    )

    for field, forbidden in rule_block.get("not_one_of", {}).items():
        found, value = _get_field_value(ticket, field)
        if found and value is not None:
            forbidden_strs = [str(f) for f in forbidden]
            if isinstance(value, list):
                bad = [str(v) for v in value if str(v) in forbidden_strs]
                if bad:
                    violations.append(
                        Violation(
                            field,
                            "not_one_of",
                            f"{field} has forbidden values: {', '.join(bad)}",
                        )
                    )
            elif str(value) in forbidden_strs:
                violations.append(
                    Violation(field, "not_one_of", f'{field} must not be "{value}"')
                )

    return violations


def _match_condition(
    ticket: Mapping[str, Any], match: Mapping[str, Any], status: str
) -> bool:
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


def check_ticket(
    ticket: Mapping[str, Any],
    rules: RuleBlock | Mapping[str, object],
    status: str | None = None,
) -> list[Violation]:
    """Check a ticket dict against rules. Returns list of Violation.

    If status is given, use it instead of ticket's current status (for
    validating a transition target before it happens).
    """
    typed_rules = cast(RuleBlock, rules)

    if status is None:
        status = ticket.get("status", "")

    # Base rules
    violations = _apply_rules(ticket, typed_rules)

    # when.<status> rules (sugar for status-conditional)
    when = typed_rules.get("when", {})
    status_rules = when.get(status, {})
    if status_rules:
        violations.extend(_apply_rules(ticket, status_rules))

    # if/then rules
    for cond in typed_rules.get("if", []):
        match = cond.get("match", {})
        then = cond.get("then", {})
        if match and _match_condition(ticket, match, status):
            violations.extend(_apply_rules(ticket, then))

    return violations


def try_load_rules(path: str | Path = "rules.yaml") -> RulesConfig | None:
    """Load rules file, returning None if it doesn't exist."""
    p = _find_rules_file(path)
    if not p:
        return None
    return _load_rules_file(p, frozenset())


def load_allowed_fields(project: str = "") -> set[str] | None:
    """Load allowed fields from allowed_fields.txt and project-specific overrides.

    Args:
        project: Project key (e.g., 'AC'). If provided, also loads allowed_fields_AC.txt

    Returns:
        Union of global and project-specific allowed fields, or None if not configured
    """
    allowed = set()

    # Load global allowed fields
    if ALLOWED_FIELDS_FILE.exists():
        with open(ALLOWED_FIELDS_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    allowed.add(line)

    # Load project-specific allowed fields (union with global)
    if project:
        project_file = CONFIG_DIR / "rules" / f"allowed_fields_{project}.txt"
        if project_file.exists():
            with open(project_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        allowed.add(line)

    return allowed if allowed else None


def check_field_allowed(
    field_name: str, allowed_fields: set[str] | None
) -> FieldError | None:
    """Check if field is allowed to update.

    Returns:
        None if allowed, or dict with error info if blocked:
        {"error": str, "suggestions": [list of field names]}
    """
    if allowed_fields is None:
        return None  # No whitelist configured

    allowed_lower = {f.lower(): f for f in allowed_fields}
    if field_name.lower() not in allowed_lower:
        from zaira.util import fuzzy_match

        # Find similar field names using fuzzy matching
        similar = fuzzy_match(field_name.lower(), [f.lower() for f in allowed_fields])
        # Map back to original casing
        similar_orig = [allowed_lower[s] for s in similar]

        return FieldError(field=field_name, suggestions=similar_orig)

    return None


def validate_transition(
    ticket: Mapping[str, Any],
    all_rules: RulesConfig | Mapping[str, object],
    target_status: str,
) -> list[Violation]:
    """Check ticket against rules for target_status.

    Returns list of Violation, or empty list if no rules apply.
    """
    issue_type = ticket.get("issuetype", "")
    raw_type_rules = all_rules.get(issue_type)
    if not isinstance(raw_type_rules, dict) or not raw_type_rules:
        return []
    type_rules = cast(RuleBlock, raw_type_rules)

    violations = []

    # Check valid_transitions: is source -> target allowed?
    source_status = ticket.get("status", "")
    valid_targets = type_rules.get("valid_transitions", {}).get(source_status)
    if valid_targets is not None and target_status not in valid_targets:
        violations.append(
            Violation(
                "transition",
                "valid_transitions",
                f'cannot transition from "{source_status}" to "{target_status}" (allowed: {", ".join(valid_targets)})',
            )
        )

    violations.extend(check_ticket(ticket, type_rules, status=target_status))
    return violations


def check_command(args: argparse.Namespace) -> None:
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

        project = key.split("-")[0]
        allowed_fields = load_allowed_fields(project=project)
        issue_type = ticket.get("issuetype", "Unknown")
        status = ticket.get("status", "Unknown")
        type_rules = all_rules.get(issue_type)

        print(f"{key} ({issue_type} / {status})")

        violations = []
        if type_rules:
            violations = check_ticket(ticket, type_rules)

        if violations:
            any_fail = True

            # For required/non_empty fields, try to fetch allowed values from editmeta
            fields_needing_values = [
                v.field for v in violations if v.check in ("required", "non_empty")
            ]

            allowed_values_map = {}
            if fields_needing_values:
                from zaira.info import load_editmeta, get_editmeta_field

                try:
                    editmeta = load_editmeta(project, issue_type)
                    if editmeta and "fields" in editmeta:
                        for field_name in fields_needing_values:
                            em = get_editmeta_field(project, issue_type, field_name)
                            if em:
                                _, field_def = em
                                allowed = field_def.get("allowedValues", [])
                                if allowed:
                                    allowed_values_map[field_name] = allowed
                except Exception:
                    pass  # If we can't fetch, just skip showing values

            for v in violations:
                print(f"  FAIL  {v.check:<11s} {v.field}")
                if v.check in (
                    "contains",
                    "not_contains",
                    "matches",
                    "not_matches",
                    "subtask_types",
                    "one_of",
                    "not_one_of",
                    "count_matches",
                    "sections_present",
                    "allowed_fields",
                    "valid_transitions",
                    "no_open_linked",
                ):
                    print(f"        {v.message}")

                # Show allowed values for required/non_empty fields
                if (
                    v.check in ("required", "non_empty")
                    and v.field in allowed_values_map
                ):
                    allowed = allowed_values_map[v.field]
                    if isinstance(allowed, list) and allowed:
                        print("        Allowed values:")
                        for val in allowed[:10]:
                            print(f"          - {val}")
                        if len(allowed) > 10:
                            print(f"          ... and {len(allowed) - 10} more")
        else:
            if type_rules or allowed_fields:
                print("  ok")
            else:
                print("  ok (no rules configured)")

    if any_fail:
        sys.exit(1)
