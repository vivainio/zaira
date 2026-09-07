"""Board and sprint operations."""

import argparse
import sys

from zaira.errors import ResourceFetchFailed
from zaira.jira_client import format_jira_error, get_jira, get_jira_site
from zaira.types import Board, Sprint


def get_boards(project: str | None = None) -> list[Board]:
    """Get boards, optionally filtered by project."""
    jira = get_jira()
    try:
        if project:
            boards = jira.boards(projectKeyOrID=project)
        else:
            boards = jira.boards()

        return [
            Board(
                id=b.id,
                name=b.name,
                type=b.type,
                location=getattr(b.location, "displayName", "")
                if hasattr(b, "location")
                else "",
            )
            for b in boards
        ]
    except Exception as e:
        print(f"Error fetching boards: {format_jira_error(e)}")
        return []


def get_sprints(board_id: int, state: str | None = None) -> list[Sprint]:
    """Get sprints for a board."""
    jira = get_jira()
    try:
        sprints = jira.sprints(board_id, state=state)
        return [
            Sprint(
                id=s.id,
                name=s.name,
                state=s.state,
            )
            for s in sprints
        ]
    except Exception as e:
        print(f"Error fetching sprints: {format_jira_error(e)}")
        return []


def get_board_info(board_id: int) -> dict | None:
    """Get board details.

    Returns None both when the board doesn't exist and when fetching it
    failed -- see _fetch_board_info for the distinction available
    internally.
    """
    try:
        return _fetch_board_info(board_id)
    except Exception:
        return None


def _fetch_board_info(board_id: int) -> dict | None:
    """Fetch board details from the raw Agile API.

    Raises ResourceFetchFailed on any JIRAError (a 404 for a nonexistent
    board included, since the Agile API doesn't distinguish "gone" from
    other failures here) instead of the blind None this used to return.
    """
    from jira.exceptions import JIRAError

    jira = get_jira()
    try:
        return jira._get_json(f"board/{board_id}", base=jira.AGILE_BASE_URL)
    except JIRAError as e:
        raise ResourceFetchFailed(
            f"could not fetch board {board_id}: {format_jira_error(e)}"
        ) from e


def get_board_issues_jql(board_id: int) -> str | None:
    """Get JQL for board issues based on board's project."""
    board = get_board_info(board_id)
    if not board:
        return None

    # Extract project key from location (e.g., "AP&P Common (AC)" -> "AC")
    location = board.get("location", {})
    if isinstance(location, dict):
        location = location.get("displayName", "")

    if "(" in location and ")" in location:
        project = location.split("(")[-1].rstrip(")")
        return f'project = "{project}" ORDER BY updated DESC'

    return None


def get_sprint_issues_jql(sprint_id: int) -> str:
    """Get JQL for sprint issues."""
    return f"sprint = {sprint_id}"


def boards_command(args: argparse.Namespace) -> None:
    """Handle boards subcommand."""
    boards = get_boards(args.project)

    if not boards:
        print("No boards found.")
        sys.exit(0)

    print(f"Found {len(boards)} boards:\n")
    print(f"{'ID':<6} {'Type':<8} {'Name':<40} {'Location'}")
    print("-" * 80)

    for b in boards:
        name = b.name[:40] if len(b.name) > 40 else b.name
        print(f"{b.id:<6} {b.type:<8} {name:<40} {b.location}")

    jira_site = get_jira_site()
    print(
        f"\nView board: https://{jira_site}/jira/software/c/projects/PROJECT/boards/BOARD_ID"
    )
