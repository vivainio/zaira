"""Tests for zaira.rules module."""

from unittest.mock import patch

from zaira.rules import (
    check_ticket,
    validate_transition,
    _find_rules_file,
    load_rules,
)
import zaira.jira_client as jira_client_mod


def _ticket(**overrides) -> object:
    base = {
        "key": "TEST-1",
        "summary": "Test ticket",
        "issuetype": "Story",
        "status": "To Do",
        "priority": "Medium",
        "assignee": "alice",
        "reporter": "bob",
        "description": "Some description",
        "components": [],
        "labels": [],
        "custom_fields": {},
    }
    base.update(overrides)
    return base


class TestCheckTicket:
    def test_no_rules(self) -> None:
        assert check_ticket(_ticket(), {}) == []

    def test_required_passes(self) -> None:
        rules = {"required": ["summary", "assignee"]}
        assert check_ticket(_ticket(), rules) == []

    def test_required_fails_missing(self) -> None:
        rules = {"required": ["Story Points"]}
        v = check_ticket(_ticket(), rules)
        assert len(v) == 1
        assert v[0].field == "Story Points"
        assert v[0].check == "required"

    def test_required_fails_none(self) -> None:
        rules = {"required": ["assignee"]}
        v = check_ticket(_ticket(assignee=None), rules)
        assert len(v) == 1
        assert v[0].check == "required"

    def test_non_empty_passes(self) -> None:
        rules = {"non_empty": ["description"]}
        assert check_ticket(_ticket(), rules) == []

    def test_non_empty_fails_empty_string(self) -> None:
        rules = {"non_empty": ["description"]}
        v = check_ticket(_ticket(description=""), rules)
        assert len(v) == 1
        assert v[0].check == "non_empty"

    def test_non_empty_fails_empty_list(self) -> None:
        rules = {"non_empty": ["labels"]}
        v = check_ticket(_ticket(labels=[]), rules)
        assert len(v) == 1
        assert v[0].check == "non_empty"

    def test_non_empty_fails_missing(self) -> None:
        rules = {"non_empty": ["Story Points"]}
        v = check_ticket(_ticket(), rules)
        assert len(v) == 1
        assert v[0].check == "non_empty"

    def test_when_status_matches(self) -> None:
        rules = {
            "required": ["summary"],
            "when": {
                "Done": {"required": ["Resolution"]},
            },
        }
        v = check_ticket(_ticket(status="Done"), rules)
        assert len(v) == 1
        assert v[0].field == "Resolution"

    def test_when_status_no_match(self) -> None:
        rules = {
            "required": ["summary"],
            "when": {
                "Done": {"required": ["Resolution"]},
            },
        }
        assert check_ticket(_ticket(status="To Do"), rules) == []

    def test_custom_field_required(self) -> None:
        rules = {"required": ["Release Date"]}
        ticket = _ticket(custom_fields={"Release Date": "2025-01-01"})
        assert check_ticket(ticket, rules) == []

    def test_custom_field_missing(self) -> None:
        rules = {"required": ["Release Date"]}
        v = check_ticket(_ticket(), rules)
        assert len(v) == 1
        assert v[0].field == "Release Date"

    def test_custom_field_non_empty(self) -> None:
        rules = {"non_empty": ["Target Environment"]}
        ticket = _ticket(custom_fields={"Target Environment": ""})
        v = check_ticket(ticket, rules)
        assert len(v) == 1
        assert v[0].check == "non_empty"

    def test_combined_base_and_when(self) -> None:
        rules = {
            "required": ["summary"],
            "non_empty": ["description"],
            "when": {
                "Done": {
                    "required": ["Resolution"],
                    "non_empty": ["labels"],
                },
            },
        }
        ticket = _ticket(status="Done", description="", labels=[])
        v = check_ticket(ticket, rules)
        fields = {vi.field for vi in v}
        assert "Resolution" in fields
        assert "description" in fields
        assert "labels" in fields

    def test_case_insensitive_standard_fields(self) -> None:
        rules = {"required": ["Summary", "STATUS"]}
        assert check_ticket(_ticket(), rules) == []

    def test_contains_passes(self) -> None:
        rules = {"contains": {"description": "Some"}}
        assert check_ticket(_ticket(), rules) == []

    def test_contains_fails_substring_missing(self) -> None:
        rules = {"contains": {"description": "acceptance criteria"}}
        v = check_ticket(_ticket(description="just a description"), rules)
        assert len(v) == 1
        assert v[0].check == "contains"
        assert "acceptance criteria" in v[0].message

    def test_contains_fails_field_missing(self) -> None:
        rules = {"contains": {"Story Points": "5"}}
        v = check_ticket(_ticket(), rules)
        assert len(v) == 1
        assert v[0].check == "contains"

    def test_contains_fails_field_none(self) -> None:
        rules = {"contains": {"description": "blah"}}
        v = check_ticket(_ticket(description=None), rules)
        assert len(v) == 1
        assert v[0].check == "contains"

    def test_contains_fails_non_string_field(self) -> None:
        rules = {"contains": {"labels": "foo"}}
        v = check_ticket(_ticket(labels=["bar"]), rules)
        assert len(v) == 1
        assert v[0].check == "contains"

    def test_contains_in_when(self) -> None:
        rules = {
            "when": {
                "Done": {"contains": {"description": "resolution"}},
            },
        }
        v = check_ticket(_ticket(status="Done", description="no match"), rules)
        assert len(v) == 1
        assert v[0].check == "contains"
        assert (
            check_ticket(_ticket(status="To Do", description="no match"), rules) == []
        )

    def test_contains_custom_field(self) -> None:
        rules = {"contains": {"Release Notes": "tested"}}
        ticket = _ticket(custom_fields={"Release Notes": "fully tested in staging"})
        assert check_ticket(ticket, rules) == []

    def test_not_contains_passes(self) -> None:
        rules = {"not_contains": {"description": "TODO"}}
        assert check_ticket(_ticket(description="all done"), rules) == []

    def test_not_contains_fails(self) -> None:
        rules = {"not_contains": {"description": "TODO"}}
        v = check_ticket(_ticket(description="TODO: fix this"), rules)
        assert len(v) == 1
        assert v[0].check == "not_contains"
        assert "TODO" in v[0].message

    def test_not_contains_skips_missing_field(self) -> None:
        rules = {"not_contains": {"Story Points": "0"}}
        assert check_ticket(_ticket(), rules) == []

    def test_not_contains_skips_non_string(self) -> None:
        rules = {"not_contains": {"labels": "bad"}}
        assert check_ticket(_ticket(labels=["bad"]), rules) == []

    def test_not_contains_in_when(self) -> None:
        rules = {
            "when": {
                "Done": {"not_contains": {"description": "WIP"}},
            },
        }
        v = check_ticket(_ticket(status="Done", description="WIP stuff"), rules)
        assert len(v) == 1
        assert (
            check_ticket(_ticket(status="To Do", description="WIP stuff"), rules) == []
        )


class TestStatusOverride:
    def test_check_ticket_with_status_override(self) -> None:
        rules = {
            "required": ["summary"],
            "when": {
                "Done": {"required": ["Resolution"]},
            },
        }
        # Ticket is currently "To Do" but we check against "Done"
        ticket = _ticket(status="To Do")
        v = check_ticket(ticket, rules, status="Done")
        assert len(v) == 1
        assert v[0].field == "Resolution"

    def test_check_ticket_override_ignores_current_status(self) -> None:
        rules = {
            "when": {
                "To Do": {"required": ["Story Points"]},
                "Done": {"required": ["Resolution"]},
            },
        }
        # Ticket is "To Do" but we check against "Done" — should NOT check To Do rules
        ticket = _ticket(status="To Do")
        v = check_ticket(ticket, rules, status="Done")
        assert len(v) == 1
        assert v[0].field == "Resolution"


class TestValidateTransition:
    def test_returns_violations_for_target_status(self) -> None:
        all_rules = {
            "Story": {
                "when": {
                    "Done": {"required": ["Resolution"]},
                },
            },
        }
        ticket = _ticket(issuetype="Story", status="In Progress")
        v = validate_transition(ticket, all_rules, "Done")
        assert len(v) == 1
        assert v[0].field == "Resolution"

    def test_returns_empty_for_unknown_type(self) -> None:
        all_rules = {"Story": {"required": ["summary"]}}
        ticket = _ticket(issuetype="Bug")
        assert validate_transition(ticket, all_rules, "Done") == []

    def test_includes_base_rules(self) -> None:
        all_rules = {
            "Story": {
                "required": ["assignee"],
                "when": {
                    "Done": {"required": ["Resolution"]},
                },
            },
        }
        # assignee is None — base rules still apply
        ticket = _ticket(issuetype="Story", assignee=None)
        v = validate_transition(ticket, all_rules, "Done")
        fields = {vi.field for vi in v}
        assert "assignee" in fields
        assert "Resolution" in fields


class TestIfThen:
    def test_if_match_triggers(self) -> None:
        rules = {
            "if": [
                {
                    "match": {"Priority": "Critical"},
                    "then": {"required": ["Rollback Plan"]},
                }
            ],
        }
        v = check_ticket(_ticket(priority="Critical"), rules)
        assert len(v) == 1
        assert v[0].field == "Rollback Plan"

    def test_if_no_match_skips(self) -> None:
        rules = {
            "if": [
                {
                    "match": {"Priority": "Critical"},
                    "then": {"required": ["Rollback Plan"]},
                }
            ],
        }
        assert check_ticket(_ticket(priority="Medium"), rules) == []

    def test_if_multiple_conditions_and(self) -> None:
        rules = {
            "if": [
                {
                    "match": {"Priority": "Critical", "status": "Done"},
                    "then": {"required": ["Post Mortem"]},
                }
            ],
        }
        # Both match
        v = check_ticket(_ticket(priority="Critical", status="Done"), rules)
        assert len(v) == 1
        assert v[0].field == "Post Mortem"
        # Only one matches
        assert check_ticket(_ticket(priority="Critical", status="To Do"), rules) == []
        assert check_ticket(_ticket(priority="Medium", status="Done"), rules) == []

    def test_if_multiple_blocks(self) -> None:
        rules = {
            "if": [
                {
                    "match": {"Priority": "Critical"},
                    "then": {"required": ["Rollback Plan"]},
                },
                {
                    "match": {"Priority": "Blocker"},
                    "then": {"required": ["Escalation Owner"]},
                },
            ],
        }
        v = check_ticket(_ticket(priority="Critical"), rules)
        assert len(v) == 1
        assert v[0].field == "Rollback Plan"
        v = check_ticket(_ticket(priority="Blocker"), rules)
        assert len(v) == 1
        assert v[0].field == "Escalation Owner"
        assert check_ticket(_ticket(priority="Medium"), rules) == []

    def test_if_with_custom_field(self) -> None:
        rules = {
            "if": [
                {
                    "match": {"Target Environment": "Production"},
                    "then": {"required": ["Rollback Plan"]},
                }
            ],
        }
        ticket = _ticket(custom_fields={"Target Environment": "Production"})
        v = check_ticket(ticket, rules)
        assert len(v) == 1
        assert v[0].field == "Rollback Plan"
        # Different env — no match
        ticket2 = _ticket(custom_fields={"Target Environment": "Staging"})
        assert check_ticket(ticket2, rules) == []

    def test_if_then_all_check_types(self) -> None:
        rules = {
            "if": [
                {
                    "match": {"status": "Done"},
                    "then": {
                        "required": ["Resolution"],
                        "non_empty": ["labels"],
                        "contains": {"description": "outcome"},
                        "not_contains": {"description": "TODO"},
                    },
                }
            ],
        }
        ticket = _ticket(status="Done", description="TODO stuff", labels=[])
        v = check_ticket(ticket, rules)
        checks = {vi.check for vi in v}
        assert "required" in checks
        assert "non_empty" in checks
        assert "contains" in checks
        assert "not_contains" in checks

    def test_if_combined_with_base_and_when(self) -> None:
        rules = {
            "required": ["summary"],
            "when": {
                "Done": {"required": ["Resolution"]},
            },
            "if": [
                {
                    "match": {"Priority": "Critical"},
                    "then": {"required": ["Rollback Plan"]},
                }
            ],
        }
        ticket = _ticket(status="Done", priority="Critical")
        v = check_ticket(ticket, rules)
        fields = {vi.field for vi in v}
        assert "Resolution" in fields
        assert "Rollback Plan" in fields

    def test_if_uses_status_override(self) -> None:
        rules = {
            "if": [
                {
                    "match": {"status": "Done"},
                    "then": {"required": ["Resolution"]},
                }
            ],
        }
        # Ticket is To Do, but override to Done
        ticket = _ticket(status="To Do")
        v = check_ticket(ticket, rules, status="Done")
        assert len(v) == 1
        assert v[0].field == "Resolution"
        # Without override, no match
        assert check_ticket(ticket, rules) == []

    def test_if_missing_field_no_match(self) -> None:
        rules = {
            "if": [
                {
                    "match": {"Nonexistent Field": "anything"},
                    "then": {"required": ["summary"]},
                }
            ],
        }
        assert check_ticket(_ticket(), rules) == []

    def test_if_match_list_field_contains(self) -> None:
        rules = {
            "if": [
                {
                    "match": {"components": "backend"},
                    "then": {"required": ["API Review"]},
                }
            ],
        }
        v = check_ticket(_ticket(components=["backend", "api"]), rules)
        assert len(v) == 1
        assert v[0].field == "API Review"

    def test_if_match_list_field_not_contains(self) -> None:
        rules = {
            "if": [
                {
                    "match": {"components": "backend"},
                    "then": {"required": ["API Review"]},
                }
            ],
        }
        assert check_ticket(_ticket(components=["frontend"]), rules) == []

    def test_if_match_labels(self) -> None:
        rules = {
            "if": [
                {
                    "match": {"labels": "security"},
                    "then": {"required": ["Security Review"]},
                }
            ],
        }
        v = check_ticket(_ticket(labels=["security", "urgent"]), rules)
        assert len(v) == 1
        assert v[0].field == "Security Review"
        assert check_ticket(_ticket(labels=["urgent"]), rules) == []

    def test_if_match_list_and_scalar(self) -> None:
        rules = {
            "if": [
                {
                    "match": {"components": "backend", "Priority": "Critical"},
                    "then": {"required": ["Rollback Plan"]},
                }
            ],
        }
        # Both match
        v = check_ticket(_ticket(components=["backend"], priority="Critical"), rules)
        assert len(v) == 1
        # Only list matches
        assert (
            check_ticket(_ticket(components=["backend"], priority="Medium"), rules)
            == []
        )
        # Only scalar matches
        assert (
            check_ticket(_ticket(components=["frontend"], priority="Critical"), rules)
            == []
        )

    def test_if_match_empty_list_no_match(self) -> None:
        rules = {
            "if": [
                {
                    "match": {"components": "backend"},
                    "then": {"required": ["API Review"]},
                }
            ],
        }
        assert check_ticket(_ticket(components=[]), rules) == []


class TestSubtaskTypes:
    def test_subtask_type_present(self) -> None:
        rules = {"subtask_types": ["Deployment Wave"]}
        ticket = _ticket(
            subtasks=[
                {
                    "key": "T-2",
                    "summary": "Deploy",
                    "status": "New",
                    "issuetype": "Deployment Wave",
                },
            ]
        )
        assert check_ticket(ticket, rules) == []

    def test_subtask_type_missing(self) -> None:
        rules = {"subtask_types": ["Deployment Wave"]}
        ticket = _ticket(subtasks=[])
        v = check_ticket(ticket, rules)
        assert len(v) == 1
        assert v[0].check == "subtask_types"
        assert v[0].field == "Deployment Wave"

    def test_subtask_type_wrong_type(self) -> None:
        rules = {"subtask_types": ["Deployment Wave"]}
        ticket = _ticket(
            subtasks=[
                {
                    "key": "T-2",
                    "summary": "Sub",
                    "status": "New",
                    "issuetype": "Sub-task",
                },
            ]
        )
        v = check_ticket(ticket, rules)
        assert len(v) == 1

    def test_multiple_subtask_types(self) -> None:
        rules = {"subtask_types": ["Deployment Wave", "Test Execution"]}
        ticket = _ticket(
            subtasks=[
                {
                    "key": "T-2",
                    "summary": "Deploy",
                    "status": "New",
                    "issuetype": "Deployment Wave",
                },
            ]
        )
        v = check_ticket(ticket, rules)
        assert len(v) == 1
        assert v[0].field == "Test Execution"

    def test_subtask_types_in_when(self) -> None:
        rules = {
            "when": {
                "Done": {"subtask_types": ["Deployment Wave"]},
            },
        }
        ticket = _ticket(status="Done", subtasks=[])
        v = check_ticket(ticket, rules)
        assert len(v) == 1
        assert check_ticket(_ticket(status="To Do", subtasks=[]), rules) == []

    def test_subtask_types_in_if_then(self) -> None:
        rules = {
            "if": [
                {
                    "match": {"Priority": "Critical"},
                    "then": {"subtask_types": ["Deployment Wave"]},
                }
            ],
        }
        ticket = _ticket(priority="Critical", subtasks=[])
        v = check_ticket(ticket, rules)
        assert len(v) == 1
        assert check_ticket(_ticket(priority="Medium", subtasks=[]), rules) == []

    def test_no_subtasks_field(self) -> None:
        rules = {"subtask_types": ["Deployment Wave"]}
        ticket = _ticket()
        v = check_ticket(ticket, rules)
        assert len(v) == 1


class TestMatches:
    def test_matches_passes(self) -> None:
        rules = {"matches": {"description": r"AC-\d+"}}
        assert check_ticket(_ticket(description="See AC-123 for details"), rules) == []

    def test_matches_fails(self) -> None:
        rules = {"matches": {"description": r"AC-\d+"}}
        v = check_ticket(_ticket(description="no ticket ref"), rules)
        assert len(v) == 1
        assert v[0].check == "matches"
        assert "AC-" in v[0].message

    def test_matches_missing_field(self) -> None:
        rules = {"matches": {"Story Points": r"\d+"}}
        v = check_ticket(_ticket(), rules)
        assert len(v) == 1
        assert v[0].check == "matches"

    def test_matches_none_field(self) -> None:
        rules = {"matches": {"description": r"."}}
        v = check_ticket(_ticket(description=None), rules)
        assert len(v) == 1

    def test_matches_non_string_field(self) -> None:
        rules = {"matches": {"labels": r"foo"}}
        v = check_ticket(_ticket(labels=["foo"]), rules)
        assert len(v) == 1

    def test_matches_case_insensitive_flag(self) -> None:
        rules = {"matches": {"summary": r"(?i)urgent"}}
        assert check_ticket(_ticket(summary="URGENT fix needed"), rules) == []

    def test_matches_custom_field(self) -> None:
        rules = {"matches": {"Release Notes": r"v\d+\.\d+"}}
        ticket = _ticket(custom_fields={"Release Notes": "Released in v2.1"})
        assert check_ticket(ticket, rules) == []

    def test_not_matches_passes(self) -> None:
        rules = {"not_matches": {"summary": r"(?i)\bwip\b"}}
        assert check_ticket(_ticket(summary="Final version"), rules) == []

    def test_not_matches_fails(self) -> None:
        rules = {"not_matches": {"summary": r"(?i)\bwip\b"}}
        v = check_ticket(_ticket(summary="WIP: draft"), rules)
        assert len(v) == 1
        assert v[0].check == "not_matches"

    def test_not_matches_skips_missing(self) -> None:
        rules = {"not_matches": {"Story Points": r"0"}}
        assert check_ticket(_ticket(), rules) == []

    def test_not_matches_skips_non_string(self) -> None:
        rules = {"not_matches": {"labels": r"bad"}}
        assert check_ticket(_ticket(labels=["bad"]), rules) == []

    def test_matches_in_when(self) -> None:
        rules = {
            "when": {
                "Done": {"matches": {"description": r"(?i)resolution"}},
            },
        }
        v = check_ticket(_ticket(status="Done", description="no match"), rules)
        assert len(v) == 1
        assert (
            check_ticket(_ticket(status="To Do", description="no match"), rules) == []
        )

    def test_matches_in_if_then(self) -> None:
        rules = {
            "if": [
                {
                    "match": {"Priority": "Critical"},
                    "then": {"not_matches": {"description": r"(?i)\btodo\b"}},
                }
            ],
        }
        v = check_ticket(_ticket(priority="Critical", description="TODO fix"), rules)
        assert len(v) == 1
        assert (
            check_ticket(_ticket(priority="Medium", description="TODO fix"), rules)
            == []
        )


class TestOneOf:
    def test_one_of_passes(self) -> None:
        rules = {"one_of": {"Priority": ["Critical", "High", "Medium"]}}
        assert check_ticket(_ticket(priority="High"), rules) == []

    def test_one_of_fails(self) -> None:
        rules = {"one_of": {"Priority": ["Critical", "High"]}}
        v = check_ticket(_ticket(priority="Low"), rules)
        assert len(v) == 1
        assert v[0].check == "one_of"
        assert "Low" in v[0].message
        assert "Critical" in v[0].message

    def test_one_of_missing_field(self) -> None:
        rules = {"one_of": {"Story Points": [1, 2, 3, 5, 8, 13]}}
        v = check_ticket(_ticket(), rules)
        assert len(v) == 1
        assert v[0].check == "one_of"

    def test_one_of_none_field(self) -> None:
        rules = {"one_of": {"assignee": ["alice", "bob"]}}
        v = check_ticket(_ticket(assignee=None), rules)
        assert len(v) == 1

    def test_one_of_list_field_all_valid(self) -> None:
        rules = {"one_of": {"labels": ["bug", "feature", "urgent"]}}
        assert check_ticket(_ticket(labels=["bug", "urgent"]), rules) == []

    def test_one_of_list_field_some_invalid(self) -> None:
        rules = {"one_of": {"labels": ["bug", "feature"]}}
        v = check_ticket(_ticket(labels=["bug", "wontfix"]), rules)
        assert len(v) == 1
        assert "wontfix" in v[0].message

    def test_one_of_numeric_comparison(self) -> None:
        rules = {"one_of": {"Story Points": [1, 2, 3, 5, 8, 13]}}
        ticket = _ticket(custom_fields={"Story Points": 5})
        assert check_ticket(ticket, rules) == []

    def test_one_of_in_when(self) -> None:
        rules = {
            "when": {
                "Done": {"one_of": {"Priority": ["Critical", "High"]}},
            },
        }
        v = check_ticket(_ticket(status="Done", priority="Low"), rules)
        assert len(v) == 1
        assert check_ticket(_ticket(status="To Do", priority="Low"), rules) == []

    def test_one_of_in_if_then(self) -> None:
        rules = {
            "if": [
                {
                    "match": {"components": "backend"},
                    "then": {"one_of": {"Priority": ["Critical", "High"]}},
                }
            ],
        }
        v = check_ticket(_ticket(components=["backend"], priority="Low"), rules)
        assert len(v) == 1
        assert (
            check_ticket(_ticket(components=["frontend"], priority="Low"), rules) == []
        )


class TestNotOneOf:
    def test_not_one_of_passes(self) -> None:
        rules = {"not_one_of": {"Priority": ["Trivial", "Low"]}}
        assert check_ticket(_ticket(priority="High"), rules) == []

    def test_not_one_of_fails(self) -> None:
        rules = {"not_one_of": {"Priority": ["Trivial", "Low"]}}
        v = check_ticket(_ticket(priority="Low"), rules)
        assert len(v) == 1
        assert v[0].check == "not_one_of"
        assert "Low" in v[0].message

    def test_not_one_of_missing_field_passes(self) -> None:
        rules = {"not_one_of": {"Story Points": [0]}}
        assert check_ticket(_ticket(), rules) == []

    def test_not_one_of_none_passes(self) -> None:
        rules = {"not_one_of": {"assignee": ["bob"]}}
        assert check_ticket(_ticket(assignee=None), rules) == []

    def test_not_one_of_list_field_all_ok(self) -> None:
        rules = {"not_one_of": {"labels": ["wontfix", "invalid"]}}
        assert check_ticket(_ticket(labels=["bug", "urgent"]), rules) == []

    def test_not_one_of_list_field_some_forbidden(self) -> None:
        rules = {"not_one_of": {"labels": ["wontfix", "invalid"]}}
        v = check_ticket(_ticket(labels=["bug", "wontfix"]), rules)
        assert len(v) == 1
        assert "wontfix" in v[0].message

    def test_not_one_of_in_when(self) -> None:
        rules = {
            "when": {
                "Done": {"not_one_of": {"Priority": ["Trivial"]}},
            },
        }
        v = check_ticket(_ticket(status="Done", priority="Trivial"), rules)
        assert len(v) == 1
        assert check_ticket(_ticket(status="To Do", priority="Trivial"), rules) == []


class TestContainsList:
    def test_contains_list_all_present(self) -> None:
        rules = {"contains": {"description": ["Root Cause", "Verification"]}}
        t = _ticket(description="Root Cause: x\nVerification: y")
        assert check_ticket(t, rules) == []

    def test_contains_list_one_missing(self) -> None:
        rules = {"contains": {"description": ["Root Cause", "Verification"]}}
        t = _ticket(description="Root Cause: x")
        v = check_ticket(t, rules)
        assert len(v) == 1
        assert "Verification" in v[0].message

    def test_contains_list_all_missing(self) -> None:
        rules = {"contains": {"description": ["Root Cause", "Verification"]}}
        t = _ticket(description="nothing here")
        v = check_ticket(t, rules)
        assert len(v) == 2

    def test_contains_list_field_missing(self) -> None:
        rules = {"contains": {"description": ["foo", "bar"]}}
        t = _ticket(description=None)
        v = check_ticket(t, rules)
        assert len(v) == 2
        assert all(vi.check == "contains" for vi in v)

    def test_contains_single_string_still_works(self) -> None:
        rules = {"contains": {"description": "hello"}}
        assert check_ticket(_ticket(description="hello world"), rules) == []

    def test_not_contains_list_all_absent(self) -> None:
        rules = {"not_contains": {"description": ["TODO", "FIXME"]}}
        assert check_ticket(_ticket(description="all done"), rules) == []

    def test_not_contains_list_one_present(self) -> None:
        rules = {"not_contains": {"description": ["TODO", "FIXME"]}}
        v = check_ticket(_ticket(description="TODO: fix this"), rules)
        assert len(v) == 1
        assert "TODO" in v[0].message

    def test_not_contains_list_both_present(self) -> None:
        rules = {"not_contains": {"description": ["TODO", "FIXME"]}}
        v = check_ticket(_ticket(description="TODO FIXME"), rules)
        assert len(v) == 2

    def test_matches_list_all_match(self) -> None:
        rules = {"matches": {"description": [r"(?i)unit test", r"(?i)e2e test"]}}
        t = _ticket(description="Unit Test: x\nE2E Test: y")
        assert check_ticket(t, rules) == []

    def test_matches_list_one_missing(self) -> None:
        rules = {"matches": {"description": [r"(?i)unit test", r"(?i)e2e test"]}}
        t = _ticket(description="Unit Test: x")
        v = check_ticket(t, rules)
        assert len(v) == 1
        assert "e2e test" in v[0].message

    def test_not_matches_list_none_match(self) -> None:
        rules = {"not_matches": {"summary": [r"(?i)\bwip\b", r"(?i)\bdraft\b"]}}
        assert check_ticket(_ticket(summary="Final version"), rules) == []

    def test_not_matches_list_one_matches(self) -> None:
        rules = {"not_matches": {"summary": [r"(?i)\bwip\b", r"(?i)\bdraft\b"]}}
        v = check_ticket(_ticket(summary="WIP: something"), rules)
        assert len(v) == 1


class TestCountMatches:
    def test_count_matches_passes(self) -> None:
        rules = {
            "count_matches": {"description": {"pattern": r"Verifies: AC-\d+", "min": 2}}
        }
        t = _ticket(description="Verifies: AC-1\nVerifies: AC-2\nVerifies: AC-3")
        assert check_ticket(t, rules) == []

    def test_count_matches_fails_below_min(self) -> None:
        rules = {
            "count_matches": {"description": {"pattern": r"Verifies: AC-\d+", "min": 3}}
        }
        t = _ticket(description="Verifies: AC-1")
        v = check_ticket(t, rules)
        assert len(v) == 1
        assert v[0].check == "count_matches"
        assert "1 matches" in v[0].message
        assert ">= 3" in v[0].message

    def test_count_matches_with_max(self) -> None:
        rules = {"count_matches": {"description": {"pattern": r"TODO", "max": 2}}}
        t = _ticket(description="TODO TODO TODO")
        v = check_ticket(t, rules)
        assert len(v) == 1
        assert "<= 2" in v[0].message

    def test_count_matches_max_passes(self) -> None:
        rules = {
            "count_matches": {"description": {"pattern": r"TODO", "min": 1, "max": 3}}
        }
        t = _ticket(description="TODO TODO")
        assert check_ticket(t, rules) == []

    def test_count_matches_missing_field(self) -> None:
        rules = {"count_matches": {"description": {"pattern": r".", "min": 1}}}
        v = check_ticket(_ticket(description=None), rules)
        assert len(v) == 1

    def test_count_matches_non_string(self) -> None:
        rules = {"count_matches": {"labels": {"pattern": r".", "min": 1}}}
        v = check_ticket(_ticket(labels=["a"]), rules)
        assert len(v) == 1

    def test_count_matches_default_min(self) -> None:
        rules = {"count_matches": {"description": {"pattern": r"AC-\d+"}}}
        t = _ticket(description="See AC-1")
        assert check_ticket(t, rules) == []

    def test_count_matches_zero_matches(self) -> None:
        rules = {"count_matches": {"description": {"pattern": r"AC-\d+", "min": 1}}}
        t = _ticket(description="no references")
        v = check_ticket(t, rules)
        assert len(v) == 1
        assert "0 matches" in v[0].message

    def test_count_matches_in_when(self) -> None:
        rules = {
            "when": {
                "Done": {
                    "count_matches": {
                        "description": {"pattern": r"Verifies:", "min": 2}
                    }
                },
            },
        }
        v = check_ticket(_ticket(status="Done", description="Verifies: one"), rules)
        assert len(v) == 1
        assert (
            check_ticket(_ticket(status="To Do", description="Verifies: one"), rules)
            == []
        )

    def test_count_matches_in_if_then(self) -> None:
        rules = {
            "if": [
                {
                    "match": {"Priority": "Critical"},
                    "then": {
                        "count_matches": {
                            "description": {"pattern": r"Verifies:", "min": 3}
                        }
                    },
                }
            ],
        }
        v = check_ticket(
            _ticket(priority="Critical", description="Verifies: one"), rules
        )
        assert len(v) == 1
        assert (
            check_ticket(_ticket(priority="Medium", description="Verifies: one"), rules)
            == []
        )


class TestSectionsPresent:
    def test_markdown_sections_present(self) -> None:
        rules = {
            "sections_present": {"description": ["Unit Tests", "Integration Tests"]}
        }
        desc = "## Unit Tests\n- test1\n## Integration Tests\n- test2"
        assert check_ticket(_ticket(description=desc), rules) == []

    def test_markdown_h3_sections(self) -> None:
        rules = {"sections_present": {"description": ["Unit Tests"]}}
        desc = "### Unit Tests\n- test1"
        assert check_ticket(_ticket(description=desc), rules) == []

    def test_jira_wiki_sections(self) -> None:
        rules = {"sections_present": {"description": ["Unit Tests", "E2E Tests"]}}
        desc = "h2. Unit Tests\n- test1\nh2. E2E Tests\n- test2"
        assert check_ticket(_ticket(description=desc), rules) == []

    def test_jira_wiki_h3(self) -> None:
        rules = {"sections_present": {"description": ["Unit Tests"]}}
        desc = "h3. Unit Tests\nsome tests"
        assert check_ticket(_ticket(description=desc), rules) == []

    def test_section_missing(self) -> None:
        rules = {"sections_present": {"description": ["Unit Tests", "E2E Tests"]}}
        desc = "## Unit Tests\n- test1"
        v = check_ticket(_ticket(description=desc), rules)
        assert len(v) == 1
        assert v[0].check == "sections_present"
        assert "E2E Tests" in v[0].message

    def test_all_sections_missing(self) -> None:
        rules = {"sections_present": {"description": ["Unit Tests", "E2E Tests"]}}
        desc = "just some text"
        v = check_ticket(_ticket(description=desc), rules)
        assert len(v) == 2

    def test_field_missing(self) -> None:
        rules = {"sections_present": {"description": ["Unit Tests"]}}
        v = check_ticket(_ticket(description=None), rules)
        assert len(v) == 1

    def test_field_non_string(self) -> None:
        rules = {"sections_present": {"labels": ["Unit Tests"]}}
        v = check_ticket(_ticket(labels=["x"]), rules)
        assert len(v) == 1

    def test_case_insensitive_section_name(self) -> None:
        rules = {"sections_present": {"description": ["Unit Tests"]}}
        desc = "## unit tests\n- test1"
        assert check_ticket(_ticket(description=desc), rules) == []

    def test_section_with_extra_text_after(self) -> None:
        rules = {"sections_present": {"description": ["Unit Tests"]}}
        desc = "## Unit Tests (3 scenarios)\n- test1"
        assert check_ticket(_ticket(description=desc), rules) == []

    def test_sections_in_when(self) -> None:
        rules = {
            "when": {
                "Done": {"sections_present": {"description": ["Unit Tests"]}},
            },
        }
        v = check_ticket(_ticket(status="Done", description="no sections"), rules)
        assert len(v) == 1
        assert (
            check_ticket(_ticket(status="To Do", description="no sections"), rules)
            == []
        )

    def test_sections_in_if_then(self) -> None:
        rules = {
            "if": [
                {
                    "match": {"issuetype": "Story"},
                    "then": {
                        "sections_present": {"description": ["Unit Tests", "E2E Tests"]}
                    },
                }
            ],
        }
        v = check_ticket(_ticket(issuetype="Story", description="no sections"), rules)
        assert len(v) == 2
        assert (
            check_ticket(_ticket(issuetype="Bug", description="no sections"), rules)
            == []
        )


class TestValidTransitions:
    def _rules(self) -> dict[str, object]:
        return {
            "Story": {
                "valid_transitions": {
                    "New": ["Analyzing", "Backlog"],
                    "Analyzing": ["Implementing", "Backlog"],
                },
            }
        }

    def test_allowed_transition_passes(self) -> None:
        ticket = _ticket(issuetype="Story", status="New")
        v = validate_transition(ticket, self._rules(), "Analyzing")
        assert v == []

    def test_forbidden_transition_fails(self) -> None:
        ticket = _ticket(issuetype="Story", status="New")
        v = validate_transition(ticket, self._rules(), "Implementing")
        assert len(v) == 1
        assert v[0].check == "valid_transitions"
        assert v[0].field == "transition"
        assert "New" in v[0].message
        assert "Implementing" in v[0].message

    def test_unknown_source_status_skips_check(self) -> None:
        # No valid_transitions entry for "On Hold" — no violation
        ticket = _ticket(issuetype="Story", status="On Hold")
        v = validate_transition(ticket, self._rules(), "Backlog")
        assert v == []

    def test_no_valid_transitions_key_skips_check(self) -> None:
        all_rules = {"Story": {"when": {"Done": {"required": ["Resolution"]}}}}
        ticket = _ticket(issuetype="Story", status="New")
        v = validate_transition(ticket, all_rules, "Done")
        assert len(v) == 1
        assert v[0].field == "Resolution"

    def test_field_violations_still_reported_on_forbidden_transition(self) -> None:
        all_rules = {
            "Story": {
                "valid_transitions": {"New": ["Backlog"]},
                "when": {"Implementing": {"required": ["Story Points"]}},
            }
        }
        ticket = _ticket(issuetype="Story", status="New")
        v = validate_transition(ticket, all_rules, "Implementing")
        checks = {vi.check for vi in v}
        assert "valid_transitions" in checks
        assert "required" in checks

    def test_unknown_issue_type_returns_empty(self) -> None:
        ticket = _ticket(issuetype="Task", status="New")
        v = validate_transition(ticket, self._rules(), "Analyzing")
        assert v == []


class TestNoOpenLinked:
    def _linked_ticket(
        self, key: str, issuetype: str, priority: str, status: str, status_cat: str
    ) -> dict[str, object]:
        return {
            "key": key,
            "issuetype": issuetype,
            "priority": priority,
            "status": status,
            "statusCategory": status_cat,
        }

    def test_no_violations_when_no_linked_issues(self) -> None:
        rules = {
            "no_open_linked": [{"type": "Bug", "priority": ["Blocker", "Critical"]}]
        }
        assert check_ticket(_ticket(issuelinks=[]), rules) == []

    def test_no_violations_when_linked_bug_is_done(self) -> None:
        rules = {"no_open_linked": [{"type": "Bug", "priority": ["Blocker"]}]}
        ticket = _ticket(
            issuelinks=[
                {
                    "key": "BUG-1",
                    "type": "Blocks",
                    "direction": "outward",
                    "summary": "Bad bug",
                }
            ]
        )
        with patch("zaira.rules.get_ticket") as mock_get:
            mock_get.return_value = self._linked_ticket(
                "BUG-1", "Bug", "Blocker", "Done", "Done"
            )
            v = check_ticket(ticket, rules)
        assert v == []

    def test_violation_when_open_blocker_bug_linked(self) -> None:
        rules = {
            "no_open_linked": [
                {"type": "Bug", "priority": ["Blocker", "Critical", "Major"]}
            ]
        }
        ticket = _ticket(
            issuelinks=[
                {
                    "key": "BUG-1",
                    "type": "Blocks",
                    "direction": "outward",
                    "summary": "Bad bug",
                }
            ]
        )
        with patch("zaira.rules.get_ticket") as mock_get:
            mock_get.return_value = self._linked_ticket(
                "BUG-1", "Bug", "Blocker", "In Progress", "In Progress"
            )
            v = check_ticket(ticket, rules)
        assert len(v) == 1
        assert v[0].check == "no_open_linked"
        assert "BUG-1" in v[0].message
        assert "Blocker" in v[0].message

    def test_no_violation_when_type_does_not_match(self) -> None:
        rules = {"no_open_linked": [{"type": "Bug", "priority": ["Blocker"]}]}
        ticket = _ticket(
            issuelinks=[
                {
                    "key": "TASK-1",
                    "type": "relates to",
                    "direction": "outward",
                    "summary": "Task",
                }
            ]
        )
        with patch("zaira.rules.get_ticket") as mock_get:
            mock_get.return_value = self._linked_ticket(
                "TASK-1", "Task", "Blocker", "In Progress", "In Progress"
            )
            v = check_ticket(ticket, rules)
        assert v == []

    def test_no_violation_when_priority_does_not_match(self) -> None:
        rules = {
            "no_open_linked": [{"type": "Bug", "priority": ["Blocker", "Critical"]}]
        }
        ticket = _ticket(
            issuelinks=[
                {
                    "key": "BUG-2",
                    "type": "relates to",
                    "direction": "outward",
                    "summary": "Minor bug",
                }
            ]
        )
        with patch("zaira.rules.get_ticket") as mock_get:
            mock_get.return_value = self._linked_ticket(
                "BUG-2", "Bug", "Minor", "In Progress", "In Progress"
            )
            v = check_ticket(ticket, rules)
        assert v == []

    def test_multiple_linked_issues_multiple_violations(self) -> None:
        rules = {
            "no_open_linked": [{"type": "Bug", "priority": ["Blocker", "Critical"]}]
        }
        ticket = _ticket(
            issuelinks=[
                {
                    "key": "BUG-1",
                    "type": "Blocks",
                    "direction": "outward",
                    "summary": "Bug 1",
                },
                {
                    "key": "BUG-2",
                    "type": "Blocks",
                    "direction": "outward",
                    "summary": "Bug 2",
                },
            ]
        )
        with patch("zaira.rules.get_ticket") as mock_get:
            mock_get.side_effect = [
                self._linked_ticket("BUG-1", "Bug", "Blocker", "Open", "To Do"),
                self._linked_ticket(
                    "BUG-2", "Bug", "Critical", "In Progress", "In Progress"
                ),
            ]
            v = check_ticket(ticket, rules)
        assert len(v) == 2

    def test_no_open_linked_in_when(self) -> None:
        rules = {
            "when": {
                "Validating": {
                    "no_open_linked": [{"type": "Bug", "priority": ["Blocker"]}],
                },
            },
        }
        ticket = _ticket(
            status="Validating",
            issuelinks=[
                {
                    "key": "BUG-1",
                    "type": "Blocks",
                    "direction": "outward",
                    "summary": "Bug",
                }
            ],
        )
        with patch("zaira.rules.get_ticket") as mock_get:
            mock_get.return_value = self._linked_ticket(
                "BUG-1", "Bug", "Blocker", "Open", "To Do"
            )
            v = check_ticket(ticket, rules)
        assert len(v) == 1
        assert check_ticket(_ticket(status="Implementing", issuelinks=[]), rules) == []


class TestFindRulesFile:
    def test_finds_cwd_file(self, tmp_path, monkeypatch) -> None:
        rules_file = tmp_path / "rules.yaml"
        rules_file.write_text("Bug: {}")
        monkeypatch.chdir(tmp_path)
        result = _find_rules_file("rules.yaml")
        assert result is not None
        assert result.resolve() == rules_file.resolve()

    def test_explicit_path_returned_if_exists(self, tmp_path) -> None:
        p = tmp_path / "myrules.yaml"
        p.write_text("Bug: {}")
        assert _find_rules_file(str(p)) == p

    def test_explicit_path_returns_none_if_missing(self, tmp_path) -> None:
        assert _find_rules_file(str(tmp_path / "nope.yaml")) is None

    def test_falls_back_to_config_dir(self, tmp_path, monkeypatch) -> None:
        fake_config = tmp_path / "zaira"
        rules_dir = fake_config / "rules"
        rules_dir.mkdir(parents=True)
        rules_file = rules_dir / "rules.yaml"
        rules_file.write_text("Bug: {}")
        monkeypatch.setattr(jira_client_mod, "CONFIG_DIR", fake_config)
        monkeypatch.chdir(tmp_path)  # no rules.yaml here
        result = _find_rules_file("rules.yaml")
        assert result == rules_file

    def test_returns_none_if_not_found_anywhere(self, tmp_path, monkeypatch) -> None:
        fake_config = tmp_path / "zaira"
        fake_config.mkdir()
        monkeypatch.setattr(jira_client_mod, "CONFIG_DIR", fake_config)
        monkeypatch.chdir(tmp_path)  # no rules.yaml here
        result = _find_rules_file("rules.yaml")
        assert result is None


class TestImport:
    def _write(self, path: str, content: str) -> object:
        path.write_text(content)
        return path

    def test_import_merges_base_and_override(self, tmp_path) -> None:
        self._write(
            tmp_path / "base.yaml",
            """\
Story:
  required: [summary, assignee]
""",
        )
        overlay = self._write(
            tmp_path / "overlay.yaml",
            """\
import: base.yaml
Story:
  required: [Extra Field]
""",
        )
        rules = load_rules(str(overlay))
        assert set(rules["Story"]["required"]) == {"summary", "assignee", "Extra Field"}

    def test_import_list_union_deduplicates(self, tmp_path) -> None:
        self._write(tmp_path / "base.yaml", "Story:\n  required: [summary, assignee]\n")
        overlay = self._write(
            tmp_path / "overlay.yaml",
            "import: base.yaml\nStory:\n  required: [assignee, Extra Field]\n",
        )
        rules = load_rules(str(overlay))
        req = rules["Story"]["required"]
        assert req.count("assignee") == 1
        assert "Extra Field" in req

    def test_import_dict_key_override_wins(self, tmp_path) -> None:
        self._write(
            tmp_path / "base.yaml",
            "Story:\n  one_of:\n    Priority: [Low, Medium]\n    Severity: [Minor]\n",
        )
        overlay = self._write(
            tmp_path / "overlay.yaml",
            "import: base.yaml\nStory:\n  one_of:\n    Priority: [High, Critical]\n",
        )
        rules = load_rules(str(overlay))
        assert rules["Story"]["one_of"]["Priority"] == ["High", "Critical"]
        assert rules["Story"]["one_of"]["Severity"] == ["Minor"]

    def test_import_no_open_linked_concatenated(self, tmp_path) -> None:
        self._write(
            tmp_path / "base.yaml",
            "Story:\n  no_open_linked:\n    - {type: Bug, priority: Blocker}\n",
        )
        overlay = self._write(
            tmp_path / "overlay.yaml",
            "import: base.yaml\nStory:\n  no_open_linked:\n    - {type: Task, priority: Critical}\n",
        )
        rules = load_rules(str(overlay))
        assert len(rules["Story"]["no_open_linked"]) == 2

    def test_import_when_merges_per_status(self, tmp_path) -> None:
        self._write(
            tmp_path / "base.yaml",
            """\
Story:
  when:
    Done:
      required: [Resolution]
""",
        )
        overlay = self._write(
            tmp_path / "overlay.yaml",
            """\
import: base.yaml
Story:
  when:
    Done:
      required: [Extra Done Field]
    Implementing:
      required: [Story Points]
""",
        )
        rules = load_rules(str(overlay))
        done = rules["Story"]["when"]["Done"]
        assert set(done["required"]) == {"Resolution", "Extra Done Field"}
        assert rules["Story"]["when"]["Implementing"]["required"] == ["Story Points"]

    def test_import_if_concatenated(self, tmp_path) -> None:
        self._write(
            tmp_path / "base.yaml",
            """\
Story:
  if:
    - match: {Priority: Critical}
      then: {required: [Rollback Plan]}
""",
        )
        overlay = self._write(
            tmp_path / "overlay.yaml",
            """\
import: base.yaml
Story:
  if:
    - match: {Priority: Blocker}
      then: {required: [Escalation Owner]}
""",
        )
        rules = load_rules(str(overlay))
        assert len(rules["Story"]["if"]) == 2

    def test_import_valid_transitions_override_per_status(self, tmp_path) -> None:
        self._write(
            tmp_path / "base.yaml",
            """\
Story:
  valid_transitions:
    New: [Analyzing, Backlog]
    Analyzing: [Implementing]
""",
        )
        overlay = self._write(
            tmp_path / "overlay.yaml",
            """\
import: base.yaml
Story:
  valid_transitions:
    New: [Backlog]
""",
        )
        rules = load_rules(str(overlay))
        assert rules["Story"]["valid_transitions"]["New"] == ["Backlog"]
        assert rules["Story"]["valid_transitions"]["Analyzing"] == ["Implementing"]

    def test_import_adds_new_issue_type(self, tmp_path) -> None:
        self._write(tmp_path / "base.yaml", "Story:\n  required: [summary]\n")
        overlay = self._write(
            tmp_path / "overlay.yaml",
            "import: base.yaml\nBug:\n  required: [assignee]\n",
        )
        rules = load_rules(str(overlay))
        assert "Story" in rules
        assert "Bug" in rules

    def test_import_chain(self, tmp_path) -> None:
        self._write(tmp_path / "base.yaml", "Story:\n  required: [summary]\n")
        self._write(
            tmp_path / "mid.yaml", "import: base.yaml\nStory:\n  required: [assignee]\n"
        )
        overlay = self._write(
            tmp_path / "overlay.yaml",
            "import: mid.yaml\nStory:\n  required: [Extra Field]\n",
        )
        rules = load_rules(str(overlay))
        assert set(rules["Story"]["required"]) == {"summary", "assignee", "Extra Field"}

    def test_import_cycle_raises(self, tmp_path) -> None:
        import pytest

        a = tmp_path / "a.yaml"
        b = tmp_path / "b.yaml"
        a.write_text("import: b.yaml\nStory:\n  required: [summary]\n")
        b.write_text("import: a.yaml\nStory:\n  required: [assignee]\n")
        with pytest.raises(ValueError, match="cycle"):
            load_rules(str(a))

    def test_import_missing_file_raises(self, tmp_path) -> None:
        import pytest

        overlay = self._write(
            tmp_path / "overlay.yaml",
            "import: nonexistent.yaml\nStory:\n  required: [summary]\n",
        )
        with pytest.raises(FileNotFoundError):
            load_rules(str(overlay))

    def test_import_path_relative_to_file(self, tmp_path) -> None:
        subdir = tmp_path / "sub"
        subdir.mkdir()
        self._write(subdir / "base.yaml", "Story:\n  required: [summary]\n")
        overlay = self._write(
            tmp_path / "overlay.yaml",
            "import: sub/base.yaml\nStory:\n  required: [Extra Field]\n",
        )
        rules = load_rules(str(overlay))
        assert set(rules["Story"]["required"]) == {"summary", "Extra Field"}

    def test_no_import_loads_normally(self, tmp_path) -> None:
        rules_file = self._write(
            tmp_path / "rules.yaml", "Story:\n  required: [summary]\n"
        )
        rules = load_rules(str(rules_file))
        assert rules == {"Story": {"required": ["summary"]}}
