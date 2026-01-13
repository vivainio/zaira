"""Dashboard operations."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from zaira.config import REPORTS_DIR
from zaira.jira_client import get_jira, get_jira_site
from zaira.types import Dashboard, DashboardGadget


def _get_owner_name(owner: dict | None) -> str:
    """Extract owner display name from owner dict."""
    if not owner:
        return ""
    return owner.get("displayName", owner.get("name", owner.get("accountId", "")))


def _dict_to_dashboard(d: dict) -> Dashboard:
    """Convert API response dict to Dashboard object."""
    return Dashboard(
        id=int(d["id"]),
        name=d.get("name", ""),
        description=d.get("description", ""),
        owner=_get_owner_name(d.get("owner")),
        view_url=d.get("view", ""),
        is_favourite=d.get("isFavourite", False),
    )


def get_dashboards(
    filter_text: str | None = None,
    owner: str | None = None,
    max_results: int = 50,
) -> list[Dashboard]:
    """Get dashboards, optionally filtered.

    Args:
        filter_text: Filter by dashboard name (case-insensitive contains)
        owner: Filter by owner account ID
        max_results: Maximum number of results to return

    Returns:
        List of Dashboard objects
    """
    jira = get_jira()
    try:
        params = {"maxResults": max_results}
        if filter_text:
            params["filter"] = filter_text
        if owner:
            params["owner"] = owner

        # Use search endpoint for filtering
        result = jira._get_json("dashboard/search", params=params)
        dashboards = result.get("values", [])
        return [_dict_to_dashboard(d) for d in dashboards]
    except Exception as e:
        print(f"Error fetching dashboards: {e}", file=sys.stderr)
        return []


def get_my_dashboards() -> list[Dashboard]:
    """Get dashboards owned by the current user."""
    jira = get_jira()
    try:
        result = jira._get_json("dashboard/search", params={"owner": "me"})
        dashboards = result.get("values", [])
        return [_dict_to_dashboard(d) for d in dashboards]
    except Exception as e:
        print(f"Error fetching dashboards: {e}", file=sys.stderr)
        return []


def get_dashboard(dashboard_id: int) -> Dashboard | None:
    """Get a specific dashboard by ID.

    Args:
        dashboard_id: The dashboard ID

    Returns:
        Dashboard object or None if not found
    """
    jira = get_jira()
    try:
        d = jira._get_json(f"dashboard/{dashboard_id}")
        return _dict_to_dashboard(d)
    except Exception as e:
        print(f"Error fetching dashboard {dashboard_id}: {e}", file=sys.stderr)
        return None


def get_dashboard_gadgets(dashboard_id: int, resolve_jql: bool = True) -> list[DashboardGadget]:
    """Get gadgets/items on a dashboard.

    Args:
        dashboard_id: The dashboard ID
        resolve_jql: Whether to fetch JQL from filters (slower but more useful)

    Returns:
        List of DashboardGadget objects
    """
    jira = get_jira()
    try:
        result = jira._get_json(f"dashboard/{dashboard_id}/gadget")
        gadgets_data = result.get("gadgets", [])

        gadgets = []
        for g in gadgets_data:
            gadget_id = str(g.get("id", ""))
            filter_id = None
            filter_name = None
            jql = None

            # Try to get gadget config for JQL/filter
            if resolve_jql and gadget_id:
                config = _get_gadget_config(dashboard_id, gadget_id)
                if config:
                    # Direct JQL in config
                    jql = config.get("jql")
                    # Or filter reference
                    filter_id = config.get("filterId")
                    if filter_id and not jql:
                        filter_info = _get_filter(filter_id)
                        if filter_info:
                            jql = filter_info.get("jql")
                            filter_name = filter_info.get("name")

            gadgets.append(
                DashboardGadget(
                    id=gadget_id,
                    title=g.get("title", ""),
                    gadget_type=_extract_gadget_type(g.get("uri", "") or g.get("moduleKey", "")),
                    position=(
                        g.get("position", {}).get("row", 0),
                        g.get("position", {}).get("column", 0),
                    ),
                    filter_id=filter_id,
                    filter_name=filter_name,
                    jql=jql,
                )
            )
        return gadgets
    except Exception as e:
        print(f"Error fetching gadgets for dashboard {dashboard_id}: {e}", file=sys.stderr)
        return []


def _get_gadget_config(dashboard_id: int, gadget_id: str) -> dict | None:
    """Get gadget configuration containing filter/JQL info."""
    jira = get_jira()
    try:
        result = jira._get_json(f"dashboard/{dashboard_id}/items/{gadget_id}/properties/config")
        return result.get("value", {})
    except Exception:
        return None


def _get_filter(filter_id: str) -> dict | None:
    """Get filter details including JQL."""
    jira = get_jira()
    try:
        return jira._get_json(f"filter/{filter_id}")
    except Exception:
        return None


def get_dashboard_raw(dashboard_id: int) -> dict | None:
    """Get raw dashboard data from API.

    Args:
        dashboard_id: The dashboard ID

    Returns:
        Raw API response dict or None
    """
    jira = get_jira()
    try:
        return jira._get_json(f"dashboard/{dashboard_id}")
    except Exception:
        return None


def _extract_gadget_type(uri_or_key: str) -> str:
    """Extract readable gadget type from URI or module key.

    Handles formats like:
    - 'rest/gadgets/1.0/g/com.atlassian.jira.gadgets:filter-results-gadget/...'
    - 'com.atlassian.jira.gadgets:filter-results-gadget'
    """
    if not uri_or_key:
        return "unknown"

    # Try to extract from URI format (contains 'gadgets:')
    if "gadgets:" in uri_or_key:
        # Extract the part after 'gadgets:' and before next '/'
        after_gadgets = uri_or_key.split("gadgets:")[-1]
        gadget_name = after_gadgets.split("/")[0]
        # Clean up: remove -gadget suffix and format nicely
        gadget_name = gadget_name.replace("-gadget", "").replace("-", " ").title()
        return gadget_name

    # Fallback: take the part after the last colon
    parts = uri_or_key.split(":")
    gadget_name = parts[-1] if parts else uri_or_key
    return gadget_name.replace("-gadget", "").replace("-", " ").title()


def generate_dashboard_markdown(
    dashboard: Dashboard,
    gadgets: list[DashboardGadget],
) -> str:
    """Generate markdown representation of a dashboard.

    Args:
        dashboard: Dashboard object
        gadgets: List of gadgets on the dashboard

    Returns:
        Markdown string
    """
    lines = ["---"]
    lines.append(f"title: {dashboard.name}")
    lines.append(f"dashboard_id: {dashboard.id}")
    lines.append(f"generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"refresh: zaira dashboard {dashboard.id}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {dashboard.name}")
    lines.append("")

    if dashboard.description:
        lines.append(f"_{dashboard.description}_")
        lines.append("")

    lines.append(f"**Owner:** {dashboard.owner}")
    lines.append(f"**URL:** {dashboard.view_url}")
    lines.append(f"**Favourite:** {'Yes' if dashboard.is_favourite else 'No'}")
    lines.append("")

    if gadgets:
        lines.append("## Gadgets")
        lines.append("")

        # Sort by position (row, column)
        for g in sorted(gadgets, key=lambda x: x.position):
            title = g.title or g.gadget_type
            lines.append(f"### {title}")
            lines.append("")
            lines.append(f"- **Type:** {g.gadget_type}")
            lines.append(f"- **Position:** row {g.position[0]}, column {g.position[1]}")
            if g.filter_name:
                lines.append(f"- **Filter:** {g.filter_name} (ID: {g.filter_id})")
            elif g.filter_id:
                lines.append(f"- **Filter ID:** {g.filter_id}")
            if g.jql:
                lines.append(f"- **JQL:** `{g.jql}`")
            lines.append("")
    else:
        lines.append("_No gadgets found on this dashboard._")
        lines.append("")

    # Summary of JQL queries for easy copying
    jql_gadgets = [g for g in gadgets if g.jql]
    if jql_gadgets:
        lines.append("## JQL Queries")
        lines.append("")
        lines.append("Copy these to use with `zaira report --jql`:")
        lines.append("")
        for g in jql_gadgets:
            name = g.filter_name or g.title or f"Gadget {g.id}"
            lines.append(f"### {name}")
            lines.append("")
            lines.append("```")
            lines.append(g.jql)
            lines.append("```")
            lines.append("")

    return "\n".join(lines)


def generate_dashboard_json(
    dashboard: Dashboard,
    gadgets: list[DashboardGadget],
) -> str:
    """Generate JSON representation of a dashboard."""
    gadget_list = []
    for g in gadgets:
        gadget_data = {
            "id": g.id,
            "title": g.title,
            "type": g.gadget_type,
            "position": {"row": g.position[0], "column": g.position[1]},
        }
        if g.filter_id:
            gadget_data["filter_id"] = g.filter_id
        if g.filter_name:
            gadget_data["filter_name"] = g.filter_name
        if g.jql:
            gadget_data["jql"] = g.jql
        gadget_list.append(gadget_data)

    data = {
        "id": dashboard.id,
        "name": dashboard.name,
        "description": dashboard.description,
        "owner": dashboard.owner,
        "view_url": dashboard.view_url,
        "is_favourite": dashboard.is_favourite,
        "generated": datetime.now().isoformat(timespec="seconds"),
        "gadgets": gadget_list,
    }
    return json.dumps(data, indent=2)


def dashboards_command(args: argparse.Namespace) -> None:
    """Handle dashboards subcommand - list dashboards."""
    if getattr(args, "mine", False):
        dashboards = get_my_dashboards()
    else:
        dashboards = get_dashboards(
            filter_text=getattr(args, "filter", None),
            max_results=getattr(args, "limit", 50),
        )

    if not dashboards:
        print("No dashboards found.")
        sys.exit(0)

    print(f"Found {len(dashboards)} dashboards:\n")
    print(f"{'ID':<8} {'Fav':<4} {'Owner':<25} {'Name'}")
    print("-" * 80)

    for d in dashboards:
        fav = "*" if d.is_favourite else ""
        owner = d.owner[:25] if len(d.owner) > 25 else d.owner
        name = d.name[:40] if len(d.name) > 40 else d.name
        print(f"{d.id:<8} {fav:<4} {owner:<25} {name}")

    jira_site = get_jira_site()
    print(f"\nView dashboard: https://{jira_site}/jira/dashboards/DASHBOARD_ID")


def dashboard_command(args: argparse.Namespace) -> None:
    """Handle dashboard subcommand - show/export a specific dashboard."""
    dashboard_id = args.id

    # Extract ID from URL if needed
    if isinstance(dashboard_id, str) and "/" in dashboard_id:
        # Handle URLs like https://company.atlassian.net/jira/dashboards/16148
        parts = dashboard_id.rstrip("/").split("/")
        dashboard_id = int(parts[-1])
    else:
        dashboard_id = int(dashboard_id)

    dashboard = get_dashboard(dashboard_id)
    if not dashboard:
        print(f"Dashboard {dashboard_id} not found.")
        sys.exit(1)

    gadgets = get_dashboard_gadgets(dashboard_id)

    fmt = getattr(args, "format", "md")
    to_stdout = getattr(args, "output", None) == "-" or not getattr(args, "output", None)

    if fmt == "json":
        output = generate_dashboard_json(dashboard, gadgets)
        ext = "json"
    else:
        output = generate_dashboard_markdown(dashboard, gadgets)
        ext = "md"

    if to_stdout:
        print(output)
    else:
        output_path = Path(args.output) if args.output else REPORTS_DIR / f"dashboard-{dashboard_id}.{ext}"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output)
        print(f"Saved to {output_path}")
