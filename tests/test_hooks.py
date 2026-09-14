"""Tests for zaira.hooks module."""

import argparse
from collections.abc import Iterator, Mapping
from typing import Any, Never
from unittest.mock import MagicMock, patch

import pytest

import zaira.hooks as hooks_mod
from zaira.check import check_ticket
from zaira.create import create_command
from zaira.edit import edit_command
from zaira.hooks import (
    CreateContext,
    FieldWriteContext,
    HookPoint,
    allowlist_from_file,
    drain_notes,
    hook,
    hooks_enabled,
    note,
    run_check_hooks,
    run_post_create_hooks,
    run_pre_create_hooks,
    run_pre_write_hooks,
)
from zaira.types import Violation


@pytest.fixture(autouse=True)
def _clean_registry() -> Iterator[None]:
    """Every test gets an empty hook registry, regardless of what ran before/after."""
    hooks_mod.reset_registry()
    yield
    hooks_mod.reset_registry()


def _ticket(**overrides: object) -> dict[str, object]:
    base = {
        "key": "FOO-1",
        "summary": "Test ticket",
        "issuetype": "Task",
        "status": "To Do",
        "custom_fields": {},
    }
    base.update(overrides)
    return base


class TestHookRegistration:
    def test_no_hooks_registered_by_default(self) -> None:
        assert hooks_enabled() is False
        assert run_pre_create_hooks(CreateContext("FOO", "Task", {})) == []
        assert run_check_hooks(_ticket(), "To Do") == []
        assert run_pre_write_hooks(FieldWriteContext("FOO", "FOO-1", "Task", {})) == []

    def test_pre_create_hook_registers_and_runs(self) -> None:
        @hook(HookPoint.PRE_CREATE)
        def block_task(ctx: CreateContext) -> Violation | None:
            if ctx.project == "FOO" and ctx.issue_type == "Task":
                return Violation(
                    "issuetype", "hook", "FOO does not accept Task tickets"
                )
            return None

        assert hooks_enabled() is True
        violations = run_pre_create_hooks(CreateContext("FOO", "Task", {}))
        assert len(violations) == 1
        assert violations[0].check == "hook"
        assert "Task" in violations[0].message

        # A different project/type is unaffected
        assert run_pre_create_hooks(CreateContext("FOO", "Story", {})) == []
        assert run_pre_create_hooks(CreateContext("BAR", "Task", {})) == []

    def test_hook_point_is_a_plain_string_too(self) -> None:
        """HookPoint members are StrEnum -- a bare string still registers."""

        @hook("pre_create")  # ty: ignore[no-matching-overload]
        def block(ctx: CreateContext) -> Violation:
            return Violation("x", "hook", "blocked")

        assert HookPoint.PRE_CREATE == "pre_create"
        assert len(run_pre_create_hooks(CreateContext("FOO", "Task", {}))) == 1

    def test_pre_create_hook_can_return_list(self) -> None:
        @hook(HookPoint.PRE_CREATE)
        def multi(ctx: CreateContext) -> list[Violation]:
            return [
                Violation("a", "hook", "one"),
                Violation("b", "hook", "two"),
            ]

        violations = run_pre_create_hooks(CreateContext("FOO", "Task", {}))
        assert [v.field for v in violations] == ["a", "b"]

    def test_pre_create_hook_can_mutate_front_matter(self) -> None:
        @hook(HookPoint.PRE_CREATE)
        def enrich(ctx: CreateContext) -> None:
            ctx.front_matter["Components"] = ["auto-tagged"]

        ctx = CreateContext("FOO", "Story", {"summary": "x"})
        run_pre_create_hooks(ctx)
        assert ctx.front_matter["Components"] == ["auto-tagged"]

    def test_raising_hook_is_isolated(self, capsys) -> None:
        @hook(HookPoint.PRE_CREATE)
        def broken(ctx: CreateContext) -> Never:
            raise RuntimeError("boom")

        @hook(HookPoint.PRE_CREATE)
        def working(ctx: CreateContext) -> Violation:
            return Violation("x", "hook", "still runs")

        violations = run_pre_create_hooks(CreateContext("FOO", "Task", {}))
        assert len(violations) == 1
        assert violations[0].message == "still runs"
        assert "boom" in capsys.readouterr().err

    def test_check_hook_runs_via_check_ticket(self) -> None:
        @hook(HookPoint.CHECK)
        def flag_high_priority_bugs(
            ticket: Mapping[str, Any], status: str
        ) -> Violation | None:
            if ticket.get("issuetype") == "Bug" and status == "Done":
                return Violation("status", "hook", "bugs need sign-off before Done")
            return None

        # Fires with no other configuration needed for this issue type.
        v = check_ticket(_ticket(issuetype="Bug"), status="Done")
        assert len(v) == 1
        assert v[0].message == "bugs need sign-off before Done"

        assert check_ticket(_ticket(issuetype="Bug"), status="To Do") == []

    def test_post_create_hook_receives_key(self) -> None:
        seen = {}

        @hook(HookPoint.POST_CREATE)
        def notify(ctx: CreateContext) -> None:
            seen["key"] = ctx.key
            seen["project"] = ctx.project

        ctx = CreateContext("FOO", "Story", {}, key="FOO-42")
        run_post_create_hooks(ctx)
        assert seen == {"key": "FOO-42", "project": "FOO"}

    def test_post_create_hook_return_value_ignored(self) -> None:
        # A post_create hook that violates its own `-> None` contract (e.g. an
        # untyped local hook file) must not crash run_post_create_hooks --
        # only its side effects matter, its return value is discarded.
        @hook(HookPoint.POST_CREATE)  # ty: ignore[invalid-argument-type]
        def noisy(ctx: CreateContext) -> Violation:
            return Violation("x", "hook", "ignored")

        run_post_create_hooks(CreateContext("FOO", "Story", {}))  # should not raise

    def test_pre_write_hook_registers_and_runs(self) -> None:
        @hook(HookPoint.PRE_WRITE)
        def restrict(ctx: FieldWriteContext) -> Violation | None:
            if "Secret Field" in ctx.fields:
                return Violation("Secret Field", "hook", "not editable")
            return None

        violations = run_pre_write_hooks(
            FieldWriteContext("FOO", "FOO-1", "Story", {"Secret Field": "x"})
        )
        assert len(violations) == 1
        assert violations[0].field == "Secret Field"

        assert (
            run_pre_write_hooks(
                FieldWriteContext("FOO", "FOO-1", "Story", {"Priority": "High"})
            )
            == []
        )


class TestHookFiltering:
    """@hook(point, project=..., issue_type=...) narrows when a hook fires."""

    def test_project_filter_single_value(self) -> None:
        @hook(HookPoint.PRE_CREATE, project="FOO")
        def restricted(ctx: CreateContext) -> Violation:
            return Violation("x", "hook", "blocked")

        assert len(run_pre_create_hooks(CreateContext("FOO", "Task", {}))) == 1
        assert run_pre_create_hooks(CreateContext("BAR", "Task", {})) == []

    def test_project_filter_iterable(self) -> None:
        @hook(HookPoint.PRE_CREATE, project=["FOO", "BAR"])
        def restricted(ctx: CreateContext) -> Violation:
            return Violation("x", "hook", "blocked")

        assert len(run_pre_create_hooks(CreateContext("FOO", "Task", {}))) == 1
        assert len(run_pre_create_hooks(CreateContext("BAR", "Task", {}))) == 1
        assert run_pre_create_hooks(CreateContext("BAZ", "Task", {})) == []

    def test_issue_type_filter(self) -> None:
        @hook(HookPoint.PRE_CREATE, issue_type="Task")
        def restricted(ctx: CreateContext) -> Violation:
            return Violation("x", "hook", "blocked")

        assert len(run_pre_create_hooks(CreateContext("FOO", "Task", {}))) == 1
        assert run_pre_create_hooks(CreateContext("FOO", "Story", {})) == []

    def test_combined_project_and_issue_type_filter(self) -> None:
        @hook(HookPoint.PRE_CREATE, project="FOO", issue_type="Task")
        def restricted(ctx: CreateContext) -> Violation:
            return Violation("x", "hook", "blocked")

        assert len(run_pre_create_hooks(CreateContext("FOO", "Task", {}))) == 1
        assert run_pre_create_hooks(CreateContext("FOO", "Story", {})) == []
        assert run_pre_create_hooks(CreateContext("BAR", "Task", {})) == []

    def test_check_hook_filter_derives_project_from_ticket_key(self) -> None:
        @hook(HookPoint.CHECK, project="FOO")
        def restricted(ticket, status) -> Violation:
            return Violation("x", "hook", "blocked")

        assert len(check_ticket(_ticket(key="FOO-9"))) == 1
        assert check_ticket(_ticket(key="BAR-9")) == []

    def test_unfiltered_hook_still_runs_everywhere(self) -> None:
        @hook(HookPoint.PRE_CREATE)
        def unrestricted(ctx: CreateContext) -> Violation:
            return Violation("x", "hook", "blocked")

        assert len(run_pre_create_hooks(CreateContext("FOO", "Task", {}))) == 1
        assert len(run_pre_create_hooks(CreateContext("BAR", "Story", {}))) == 1


class TestNotes:
    """note()/drain_notes() -- free-text messages, never block anything."""

    def test_drain_notes_starts_empty(self) -> None:
        assert drain_notes() == []

    def test_note_is_queued_and_drained(self) -> None:
        note("first")
        note("second")
        assert drain_notes() == ["first", "second"]

    def test_drain_clears_the_queue(self) -> None:
        note("only once")
        assert drain_notes() == ["only once"]
        assert drain_notes() == []

    def test_hook_calling_note_does_not_block(self) -> None:
        @hook(HookPoint.PRE_CREATE)
        def informational_only(ctx: CreateContext) -> None:
            note("just a heads-up, not a violation")

        violations = run_pre_create_hooks(CreateContext("FOO", "Task", {}))
        assert violations == []
        assert drain_notes() == ["just a heads-up, not a violation"]

    def test_note_and_violation_from_same_hook(self) -> None:
        @hook(HookPoint.PRE_CREATE)
        def both(ctx: CreateContext) -> Violation:
            note("some context about why this is blocked")
            return Violation("issuetype", "hook", "blocked")

        violations = run_pre_create_hooks(CreateContext("FOO", "Task", {}))
        assert len(violations) == 1
        assert drain_notes() == ["some context about why this is blocked"]

    def test_reset_registry_also_clears_pending_notes(self) -> None:
        note("orphaned")
        hooks_mod.reset_registry()
        assert drain_notes() == []


class TestAllowlistFromFile:
    def test_blocks_field_not_in_list(self, tmp_path) -> None:
        allow_file = tmp_path / "allowed_fields.txt"
        allow_file.write_text("Priority\nStory Points\n# comment\n\n")

        check = allowlist_from_file(allow_file, register=False)
        violations = check(
            FieldWriteContext("FOO", "FOO-1", "Story", {"Secret Field": "x"})
        )
        assert len(violations) == 1
        assert violations[0].check == "allowed_fields"

    def test_allows_listed_field_case_insensitively(self, tmp_path) -> None:
        allow_file = tmp_path / "allowed_fields.txt"
        allow_file.write_text("Priority\n")

        check = allowlist_from_file(allow_file, register=False)
        assert (
            check(FieldWriteContext("FOO", "FOO-1", "Story", {"priority": "High"}))
            == []
        )

    def test_suggests_close_match(self, tmp_path) -> None:
        allow_file = tmp_path / "allowed_fields.txt"
        allow_file.write_text("Story Points\n")

        check = allowlist_from_file(allow_file, register=False)
        violations = check(
            FieldWriteContext("FOO", "FOO-1", "Story", {"Stroy Points": "5"})
        )
        assert "Story Points" in violations[0].message

    def test_per_project_override_unions_with_global(self, tmp_path) -> None:
        global_file = tmp_path / "global.txt"
        global_file.write_text("Priority\n")
        foo_file = tmp_path / "foo.txt"
        foo_file.write_text("Custom Approval\n")

        check = allowlist_from_file(
            global_file, per_project={"FOO": foo_file}, register=False
        )
        assert (
            check(
                FieldWriteContext("FOO", "FOO-1", "Story", {"Custom Approval": "yes"})
            )
            == []
        )
        # Global field still allowed everywhere
        assert (
            check(FieldWriteContext("BAR", "BAR-1", "Story", {"Priority": "High"}))
            == []
        )
        # FOO-only field not allowed for another project
        assert (
            len(
                check(
                    FieldWriteContext(
                        "BAR", "BAR-1", "Story", {"Custom Approval": "yes"}
                    )
                )
            )
            == 1
        )

    def test_register_true_wires_into_pre_write(self, tmp_path) -> None:
        allow_file = tmp_path / "allowed_fields.txt"
        allow_file.write_text("Priority\n")

        allowlist_from_file(allow_file)  # register=True by default

        violations = run_pre_write_hooks(
            FieldWriteContext("FOO", "FOO-1", "Story", {"Secret Field": "x"})
        )
        assert len(violations) == 1

    def test_empty_allowlist_permits_everything(self, tmp_path) -> None:
        allow_file = tmp_path / "allowed_fields.txt"
        allow_file.write_text("# nothing configured\n")

        check = allowlist_from_file(allow_file, register=False)
        assert (
            check(FieldWriteContext("FOO", "FOO-1", "Story", {"Anything": "x"})) == []
        )


class TestCreateCommandHookIntegration:
    """End-to-end: a pre_create hook blocking `zaira create`."""

    @pytest.fixture(autouse=True)
    def _no_ensure_editmeta(self) -> object:
        with patch("zaira.info.ensure_editmeta_for_type", return_value=None):
            yield

    def test_blocks_creation(self, tmp_path, capsys) -> None:
        @hook(HookPoint.PRE_CREATE)
        def no_tasks_in_foo(ctx: CreateContext) -> Violation | None:
            if ctx.project == "FOO" and ctx.issue_type == "Task":
                return Violation(
                    "issuetype", "hook", "FOO does not accept Task tickets"
                )
            return None

        ticket_file = tmp_path / "ticket.md"
        ticket_file.write_text("""---
project: FOO
type: Task
summary: Should be blocked
---

Description.
""")
        args = argparse.Namespace(file=str(ticket_file), dry_run=False, no_check=False)

        with pytest.raises(SystemExit) as exc_info:
            create_command(args)

        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert "Blocked" in err
        assert "FOO does not accept Task tickets" in err

    def test_note_prints_without_blocking(self, tmp_path, capsys, mock_jira) -> None:
        @hook(HookPoint.PRE_CREATE)
        def flag_cadence(ctx: CreateContext) -> None:
            if ctx.front_matter.get("cadence") == "Monthly Release":
                note("Monthly Release: next deploy window opens the 15th")

        ticket_file = tmp_path / "ticket.md"
        ticket_file.write_text("""---
project: FOO
type: Story
summary: Fine, just informational
cadence: Monthly Release
---

Description.
""")
        mock_issue = MagicMock()
        mock_issue.key = "FOO-1"
        mock_jira.create_issue.return_value = mock_issue

        args = argparse.Namespace(file=str(ticket_file), dry_run=False, no_check=False)
        create_command(args)

        out = capsys.readouterr().out
        assert "NOTE  Monthly Release: next deploy window opens the 15th" in out
        assert "Created FOO-1" in out

    def test_no_check_skips_hook(self, tmp_path, capsys, mock_jira) -> None:
        @hook(HookPoint.PRE_CREATE)
        def no_tasks_in_foo(ctx: CreateContext) -> Violation | None:
            if ctx.project == "FOO" and ctx.issue_type == "Task":
                return Violation(
                    "issuetype", "hook", "FOO does not accept Task tickets"
                )
            return None

        ticket_file = tmp_path / "ticket.md"
        ticket_file.write_text("""---
project: FOO
type: Task
summary: Should be allowed with --no-check
---

Description.
""")
        mock_issue = MagicMock()
        mock_issue.key = "FOO-100"
        mock_jira.create_issue.return_value = mock_issue

        args = argparse.Namespace(file=str(ticket_file), dry_run=False, no_check=True)
        create_command(args)

        assert "Created FOO-100" in capsys.readouterr().out

    def test_allowed_project_passes(self, tmp_path, capsys, mock_jira) -> None:
        @hook(HookPoint.PRE_CREATE)
        def no_tasks_in_foo(ctx: CreateContext) -> Violation | None:
            if ctx.project == "FOO" and ctx.issue_type == "Task":
                return Violation(
                    "issuetype", "hook", "FOO does not accept Task tickets"
                )
            return None

        ticket_file = tmp_path / "ticket.md"
        ticket_file.write_text("""---
project: BAR
type: Task
summary: Fine elsewhere
---

Description.
""")
        mock_issue = MagicMock()
        mock_issue.key = "BAR-1"
        mock_jira.create_issue.return_value = mock_issue

        args = argparse.Namespace(file=str(ticket_file), dry_run=False, no_check=False)
        create_command(args)

        assert "Created BAR-1" in capsys.readouterr().out


class TestEditCommandHookIntegration:
    """End-to-end: a pre_write hook blocking `zaira edit --field`."""

    def test_blocks_disallowed_field(self, tmp_path, capsys, mock_jira) -> None:
        @hook(HookPoint.PRE_WRITE)
        def restrict(ctx: FieldWriteContext) -> Violation | None:
            if "Secret Field" in ctx.fields:
                return Violation("Secret Field", "hook", "not editable")
            return None

        mock_issue = MagicMock()
        mock_issue.fields.issuetype.name = "Story"
        mock_jira.issue.return_value = mock_issue

        args = argparse.Namespace(
            key="FOO-1",
            title=None,
            description=None,
            field=["Secret Field=x"],
            from_file=None,
            no_check=False,
            dry_run=False,
        )

        with patch("zaira.info.ensure_editmeta", return_value=None):
            with pytest.raises(SystemExit) as exc_info:
                edit_command(args)

        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert "blocked" in err
        assert "not editable" in err

    def test_no_check_skips_pre_write_hook(self, tmp_path, capsys, mock_jira) -> None:
        @hook(HookPoint.PRE_WRITE)
        def restrict(ctx: FieldWriteContext) -> Violation | None:
            return Violation("Secret Field", "hook", "not editable")

        mock_issue = MagicMock()
        mock_issue.fields.issuetype.name = "Story"
        mock_jira.issue.return_value = mock_issue

        args = argparse.Namespace(
            key="FOO-1",
            title="New title",
            description=None,
            field=None,
            from_file=None,
            no_check=True,
            dry_run=False,
        )

        with (
            patch("zaira.info.ensure_editmeta", return_value=None),
            patch("zaira.edit.get_jira_site", return_value="jira.example.com"),
        ):
            edit_command(args)

        assert "Updated FOO-1" in capsys.readouterr().out
