# Agent Instructions

Guidelines for AI agents working on this codebase.

## Code Style

### Formatting

Use **ruff** for all code formatting:

```bash
ruff format .
```

Run this before committing any changes.

### Linting

Use **ruff** for linting:

```bash
ruff check .
```

Fix auto-fixable issues with:

```bash
ruff check --fix .
```

### Type Annotations

Add type annotations to all new code:

- Function parameters and return types are required
- Use `None` return type for functions that don't return a value
- Use `typing` module types when needed (`Optional`, `Union`, `TypedDict`, etc.)
- For Python 3.11+, prefer built-in generics (`list[str]` over `List[str]`)

Example:

```python
def get_tickets(project: str, limit: int = 100) -> list[dict]:
    ...

def export_ticket(ticket: dict, output_dir: Path) -> None:
    ...
```

### Import Order

Ruff handles import sorting. The order is:

1. Standard library
2. Third-party packages
3. Local imports

## Running Checks

Before committing:

```bash
ruff format .
ruff check .
```

## Releases

To publish a new release:

1. Create a GitHub release using `gh release create`
2. GitHub Actions will automatically update the version in `pyproject.toml` and publish to PyPI

Do NOT manually edit the version in `pyproject.toml` - it is managed by GitHub Actions.

```bash
gh release create v0.3.0 --title "v0.3.0" --notes "Release notes here"
```

Or use `--generate-notes` to auto-generate from commits:

```bash
gh release create v0.3.0 --generate-notes
```

## Project Structure

- `zaira/` - Main package
- `zaira/cli.py` - CLI entry point
- `zaira/jira_client.py` - Jira API client
- `zaira/export.py` - Ticket export functionality
- `zaira/config.py` - Configuration handling
