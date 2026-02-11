"""Tests for zaira.rules module."""

from zaira.rules import check_ticket, validate_transition, Violation


def _ticket(**overrides):
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
    def test_no_rules(self):
        assert check_ticket(_ticket(), {}) == []

    def test_required_passes(self):
        rules = {"required": ["summary", "assignee"]}
        assert check_ticket(_ticket(), rules) == []

    def test_required_fails_missing(self):
        rules = {"required": ["Story Points"]}
        v = check_ticket(_ticket(), rules)
        assert len(v) == 1
        assert v[0].field == "Story Points"
        assert v[0].check == "required"

    def test_required_fails_none(self):
        rules = {"required": ["assignee"]}
        v = check_ticket(_ticket(assignee=None), rules)
        assert len(v) == 1
        assert v[0].check == "required"

    def test_non_empty_passes(self):
        rules = {"non_empty": ["description"]}
        assert check_ticket(_ticket(), rules) == []

    def test_non_empty_fails_empty_string(self):
        rules = {"non_empty": ["description"]}
        v = check_ticket(_ticket(description=""), rules)
        assert len(v) == 1
        assert v[0].check == "non_empty"

    def test_non_empty_fails_empty_list(self):
        rules = {"non_empty": ["labels"]}
        v = check_ticket(_ticket(labels=[]), rules)
        assert len(v) == 1
        assert v[0].check == "non_empty"

    def test_non_empty_fails_missing(self):
        rules = {"non_empty": ["Story Points"]}
        v = check_ticket(_ticket(), rules)
        assert len(v) == 1
        assert v[0].check == "non_empty"

    def test_when_status_matches(self):
        rules = {
            "required": ["summary"],
            "when": {
                "Done": {"required": ["Resolution"]},
            },
        }
        v = check_ticket(_ticket(status="Done"), rules)
        assert len(v) == 1
        assert v[0].field == "Resolution"

    def test_when_status_no_match(self):
        rules = {
            "required": ["summary"],
            "when": {
                "Done": {"required": ["Resolution"]},
            },
        }
        assert check_ticket(_ticket(status="To Do"), rules) == []

    def test_custom_field_required(self):
        rules = {"required": ["Release Date"]}
        ticket = _ticket(custom_fields={"Release Date": "2025-01-01"})
        assert check_ticket(ticket, rules) == []

    def test_custom_field_missing(self):
        rules = {"required": ["Release Date"]}
        v = check_ticket(_ticket(), rules)
        assert len(v) == 1
        assert v[0].field == "Release Date"

    def test_custom_field_non_empty(self):
        rules = {"non_empty": ["Target Environment"]}
        ticket = _ticket(custom_fields={"Target Environment": ""})
        v = check_ticket(ticket, rules)
        assert len(v) == 1
        assert v[0].check == "non_empty"

    def test_combined_base_and_when(self):
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

    def test_case_insensitive_standard_fields(self):
        rules = {"required": ["Summary", "STATUS"]}
        assert check_ticket(_ticket(), rules) == []

    def test_contains_passes(self):
        rules = {"contains": {"description": "Some"}}
        assert check_ticket(_ticket(), rules) == []

    def test_contains_fails_substring_missing(self):
        rules = {"contains": {"description": "acceptance criteria"}}
        v = check_ticket(_ticket(description="just a description"), rules)
        assert len(v) == 1
        assert v[0].check == "contains"
        assert "acceptance criteria" in v[0].message

    def test_contains_fails_field_missing(self):
        rules = {"contains": {"Story Points": "5"}}
        v = check_ticket(_ticket(), rules)
        assert len(v) == 1
        assert v[0].check == "contains"

    def test_contains_fails_field_none(self):
        rules = {"contains": {"description": "blah"}}
        v = check_ticket(_ticket(description=None), rules)
        assert len(v) == 1
        assert v[0].check == "contains"

    def test_contains_fails_non_string_field(self):
        rules = {"contains": {"labels": "foo"}}
        v = check_ticket(_ticket(labels=["bar"]), rules)
        assert len(v) == 1
        assert v[0].check == "contains"

    def test_contains_in_when(self):
        rules = {
            "when": {
                "Done": {"contains": {"description": "resolution"}},
            },
        }
        v = check_ticket(_ticket(status="Done", description="no match"), rules)
        assert len(v) == 1
        assert v[0].check == "contains"
        assert check_ticket(_ticket(status="To Do", description="no match"), rules) == []

    def test_contains_custom_field(self):
        rules = {"contains": {"Release Notes": "tested"}}
        ticket = _ticket(custom_fields={"Release Notes": "fully tested in staging"})
        assert check_ticket(ticket, rules) == []

    def test_not_contains_passes(self):
        rules = {"not_contains": {"description": "TODO"}}
        assert check_ticket(_ticket(description="all done"), rules) == []

    def test_not_contains_fails(self):
        rules = {"not_contains": {"description": "TODO"}}
        v = check_ticket(_ticket(description="TODO: fix this"), rules)
        assert len(v) == 1
        assert v[0].check == "not_contains"
        assert "TODO" in v[0].message

    def test_not_contains_skips_missing_field(self):
        rules = {"not_contains": {"Story Points": "0"}}
        assert check_ticket(_ticket(), rules) == []

    def test_not_contains_skips_non_string(self):
        rules = {"not_contains": {"labels": "bad"}}
        assert check_ticket(_ticket(labels=["bad"]), rules) == []

    def test_not_contains_in_when(self):
        rules = {
            "when": {
                "Done": {"not_contains": {"description": "WIP"}},
            },
        }
        v = check_ticket(_ticket(status="Done", description="WIP stuff"), rules)
        assert len(v) == 1
        assert check_ticket(_ticket(status="To Do", description="WIP stuff"), rules) == []


class TestStatusOverride:
    def test_check_ticket_with_status_override(self):
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

    def test_check_ticket_override_ignores_current_status(self):
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
    def test_returns_violations_for_target_status(self):
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

    def test_returns_empty_for_unknown_type(self):
        all_rules = {"Story": {"required": ["summary"]}}
        ticket = _ticket(issuetype="Bug")
        assert validate_transition(ticket, all_rules, "Done") == []

    def test_includes_base_rules(self):
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
    def test_if_match_triggers(self):
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

    def test_if_no_match_skips(self):
        rules = {
            "if": [
                {
                    "match": {"Priority": "Critical"},
                    "then": {"required": ["Rollback Plan"]},
                }
            ],
        }
        assert check_ticket(_ticket(priority="Medium"), rules) == []

    def test_if_multiple_conditions_and(self):
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

    def test_if_multiple_blocks(self):
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

    def test_if_with_custom_field(self):
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

    def test_if_then_all_check_types(self):
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

    def test_if_combined_with_base_and_when(self):
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

    def test_if_uses_status_override(self):
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

    def test_if_missing_field_no_match(self):
        rules = {
            "if": [
                {
                    "match": {"Nonexistent Field": "anything"},
                    "then": {"required": ["summary"]},
                }
            ],
        }
        assert check_ticket(_ticket(), rules) == []

    def test_if_match_list_field_contains(self):
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

    def test_if_match_list_field_not_contains(self):
        rules = {
            "if": [
                {
                    "match": {"components": "backend"},
                    "then": {"required": ["API Review"]},
                }
            ],
        }
        assert check_ticket(_ticket(components=["frontend"]), rules) == []

    def test_if_match_labels(self):
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

    def test_if_match_list_and_scalar(self):
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
        assert check_ticket(_ticket(components=["backend"], priority="Medium"), rules) == []
        # Only scalar matches
        assert check_ticket(_ticket(components=["frontend"], priority="Critical"), rules) == []

    def test_if_match_empty_list_no_match(self):
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
    def test_subtask_type_present(self):
        rules = {"subtask_types": ["Deployment Wave"]}
        ticket = _ticket(subtasks=[
            {"key": "T-2", "summary": "Deploy", "status": "New", "issuetype": "Deployment Wave"},
        ])
        assert check_ticket(ticket, rules) == []

    def test_subtask_type_missing(self):
        rules = {"subtask_types": ["Deployment Wave"]}
        ticket = _ticket(subtasks=[])
        v = check_ticket(ticket, rules)
        assert len(v) == 1
        assert v[0].check == "subtask_types"
        assert v[0].field == "Deployment Wave"

    def test_subtask_type_wrong_type(self):
        rules = {"subtask_types": ["Deployment Wave"]}
        ticket = _ticket(subtasks=[
            {"key": "T-2", "summary": "Sub", "status": "New", "issuetype": "Sub-task"},
        ])
        v = check_ticket(ticket, rules)
        assert len(v) == 1

    def test_multiple_subtask_types(self):
        rules = {"subtask_types": ["Deployment Wave", "Test Execution"]}
        ticket = _ticket(subtasks=[
            {"key": "T-2", "summary": "Deploy", "status": "New", "issuetype": "Deployment Wave"},
        ])
        v = check_ticket(ticket, rules)
        assert len(v) == 1
        assert v[0].field == "Test Execution"

    def test_subtask_types_in_when(self):
        rules = {
            "when": {
                "Done": {"subtask_types": ["Deployment Wave"]},
            },
        }
        ticket = _ticket(status="Done", subtasks=[])
        v = check_ticket(ticket, rules)
        assert len(v) == 1
        assert check_ticket(_ticket(status="To Do", subtasks=[]), rules) == []

    def test_subtask_types_in_if_then(self):
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

    def test_no_subtasks_field(self):
        rules = {"subtask_types": ["Deployment Wave"]}
        ticket = _ticket()
        v = check_ticket(ticket, rules)
        assert len(v) == 1


class TestMatches:
    def test_matches_passes(self):
        rules = {"matches": {"description": r"AC-\d+"}}
        assert check_ticket(_ticket(description="See AC-123 for details"), rules) == []

    def test_matches_fails(self):
        rules = {"matches": {"description": r"AC-\d+"}}
        v = check_ticket(_ticket(description="no ticket ref"), rules)
        assert len(v) == 1
        assert v[0].check == "matches"
        assert "AC-" in v[0].message

    def test_matches_missing_field(self):
        rules = {"matches": {"Story Points": r"\d+"}}
        v = check_ticket(_ticket(), rules)
        assert len(v) == 1
        assert v[0].check == "matches"

    def test_matches_none_field(self):
        rules = {"matches": {"description": r"."}}
        v = check_ticket(_ticket(description=None), rules)
        assert len(v) == 1

    def test_matches_non_string_field(self):
        rules = {"matches": {"labels": r"foo"}}
        v = check_ticket(_ticket(labels=["foo"]), rules)
        assert len(v) == 1

    def test_matches_case_insensitive_flag(self):
        rules = {"matches": {"summary": r"(?i)urgent"}}
        assert check_ticket(_ticket(summary="URGENT fix needed"), rules) == []

    def test_matches_custom_field(self):
        rules = {"matches": {"Release Notes": r"v\d+\.\d+"}}
        ticket = _ticket(custom_fields={"Release Notes": "Released in v2.1"})
        assert check_ticket(ticket, rules) == []

    def test_not_matches_passes(self):
        rules = {"not_matches": {"summary": r"(?i)\bwip\b"}}
        assert check_ticket(_ticket(summary="Final version"), rules) == []

    def test_not_matches_fails(self):
        rules = {"not_matches": {"summary": r"(?i)\bwip\b"}}
        v = check_ticket(_ticket(summary="WIP: draft"), rules)
        assert len(v) == 1
        assert v[0].check == "not_matches"

    def test_not_matches_skips_missing(self):
        rules = {"not_matches": {"Story Points": r"0"}}
        assert check_ticket(_ticket(), rules) == []

    def test_not_matches_skips_non_string(self):
        rules = {"not_matches": {"labels": r"bad"}}
        assert check_ticket(_ticket(labels=["bad"]), rules) == []

    def test_matches_in_when(self):
        rules = {
            "when": {
                "Done": {"matches": {"description": r"(?i)resolution"}},
            },
        }
        v = check_ticket(_ticket(status="Done", description="no match"), rules)
        assert len(v) == 1
        assert check_ticket(_ticket(status="To Do", description="no match"), rules) == []

    def test_matches_in_if_then(self):
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
        assert check_ticket(_ticket(priority="Medium", description="TODO fix"), rules) == []
