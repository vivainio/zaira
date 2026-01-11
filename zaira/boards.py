"""Board and sprint operations."""

import sys

from zaira.jira_client import get_jira, get_jira_site


def get_boards(project: str | None = None) -> list[dict]:
    """Get boards, optionally filtered by project."""
    jira = get_jira()
    try:
        if project:
            boards = jira.boards(projectKeyOrID=project)
        else:
            boards = jira.boards()

        return [
            {
                "id": b.id,
                "name": b.name,
                "type": b.type,
                "location": getattr(b.location, "displayName", "") if hasattr(b, "location") else "",
            }
            for b in boards
        ]
    except Exception as e:
        print(f"Error fetching boards: {e}")
        return []


def get_sprints(board_id: int, state: str | None = None) -> list[dict]:
    """Get sprints for a board."""
    jira = get_jira()
    try:
        sprints = jira.sprints(board_id, state=state)
        return [
            {
                "id": s.id,
                "name": s.name,
                "state": s.state,
            }
            for s in sprints
        ]
    except Exception as e:
        print(f"Error fetching sprints: {e}")
        return []


def get_board_info(board_id: int) -> dict | None:
    """Get board details."""
    jira = get_jira()
    try:
        # Use the raw API to get board details
        board = jira._get_json(f"board/{board_id}", base=jira.AGILE_BASE_URL)
        return board
    except Exception:
        return None


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
        return f"project = {project} ORDER BY updated DESC"

    return None


def get_sprint_issues_jql(sprint_id: int) -> str:
    """Get JQL for sprint issues."""
    return f"sprint = {sprint_id}"


def boards_command(args):
    """Handle boards subcommand."""
    boards = get_boards(args.project)

    if not boards:
        print("No boards found.")
        sys.exit(0)

    print(f"Found {len(boards)} boards:\n")
    print(f"{'ID':<6} {'Type':<8} {'Name':<40} {'Location'}")
    print("-" * 80)

    for b in boards:
        board_id = b.get("id", "?")
        board_type = b.get("type", "?")
        name = str(b.get("name", "?"))[:40]
        location = b.get("location", "")
        print(f"{board_id:<6} {board_type:<8} {name:<40} {location}")

    jira_site = get_jira_site()
    print(f"\nView board: https://{jira_site}/jira/software/c/projects/PROJECT/boards/BOARD_ID")
