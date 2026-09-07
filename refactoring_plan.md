# Refactoring plan

Review date: 2026-09-07

Zaira has a solid foundation: feature-oriented modules and extensive tests make incremental refactoring practical. The main opportunity is to tighten internal boundaries while preserving the existing CLI API.

## Compatibility constraints

Preserve command names, arguments, aliases, defaults, argument ordering, dispatch, help text, stdout/stderr behavior, exit codes, and output formats during structural refactoring. Treat observable bug fixes as separate compatibility decisions rather than folding them into code moves.

## Recommended improvements

### 1. Separate API failures from empty results

Several helpers catch errors and return `[]`, `None`, or `False`. For example, `get_comments()` in [zaira/export.py](zaira/export.py) treats any exception as “no comments,” allowing an incomplete export to appear successful. Confluence folder lookups also return empty lists on HTTP failure, while folder resolution in [zaira/confluence_api.py](zaira/confluence_api.py) can interpret that as permission to create missing folders.

Introduce typed internal errors and handle them at command boundaries. The existing `ApplicationError` in [zaira/errors.py](zaira/errors.py) is a good starting point. Distinguish empty results, missing resources, and failed requests internally; preserve existing CLI behavior through boundary adapters until any behavior fixes are considered separately.

### 2. Protect the CLI contract before moving code

[zaira/cli.py](zaira/cli.py) contains roughly 1,560 lines, with parser construction embedded in `main()`. The review found no tests exercising that parser.

Extract `build_parser()` and feature-specific registration functions, preserving the existing parser contract. Add contract tests for commands, help, stdout/stderr, exit codes, and representative output formats. Use these tests to protect subsequent refactoring.

### 3. Split large modules by responsibility

[zaira/wiki.py](zaira/wiki.py) combines parsing, synchronization decisions, rendering, remote operations, and local writes; `_put_one_file()` alone spans hundreds of lines. [zaira/export.py](zaira/export.py) similarly mixes fetching, enrichment, formatting, attachments, and persistence.

Extract those responsibilities behind the existing command functions. In particular, make synchronization decisions a pure function that returns a plan, then execute that plan separately. Keep command handlers responsible for translating CLI input and presenting results.

### 4. Centralize Confluence transport and pagination

[zaira/confluence_api.py](zaira/confluence_api.py) repeats authentication and request handling throughout. Child and folder listing helpers consume only one response page, although recursive traversal in [zaira/wiki.py](zaira/wiki.py) promises all descendants.

Add an internal client with a reusable session, consistent errors, and pagination helpers. Keep explicit user-facing result limits intact. Introduce complete traversal as a separately tested correctness fix, with cases for multiple pages and failed intermediate requests.

### 5. Use structured operation results

`export_ticket()` in [zaira/export.py](zaira/export.py) returns either a boolean or an attachment list, forcing callers to use `result is not False`. `get_command()` in [zaira/get.py](zaira/get.py) counts exports but discards attachment download outcomes and returns normally after partial file-export failures.

Introduce an `ExportResult` containing status, path, pending attachments, and failures. This would make orchestration clearer and allow callers to distinguish complete, partial, and failed operations. Preserve existing CLI behavior during extraction; treat any exit-code correction as a separate compatibility decision.

### 6. Consolidate document parsing and file persistence

Front matter has three implementations: [create](zaira/create.py), [wiki](zaira/wiki.py), and [refresh](zaira/refresh.py). Their YAML handling and malformed-input behavior differ; refresh manually splits lines at colons.

Share parsing machinery with explicit policies for each existing format, validate that metadata is a mapping, and retain compatibility fixtures. Use UTF-8 consistently and atomic replacement for exports and schema cache writes in [zaira/info.py](zaira/info.py). Test that a failed write leaves the previous file intact.

### 7. Enforce documented checks in CI

[The test workflow](.github/workflows/test.yml) runs type checks and tests but omits Ruff.

Add lint and formatting checks, declare Ruff as a development dependency, and enable its import-sorting rule—the current configuration does not enable it. A Windows test job would also support the substantial Windows-specific credential and startup code.

Follow the repository's dependency and release rules: only commit `uv.lock` when dependencies change, keep its registry URLs public, and do not manually edit the package version.

## Suggested implementation order

1. Add CLI contract tests and extract parser construction.
2. Introduce internal error types and structured export/synchronization results behind compatibility adapters.
3. Split export and wiki synchronization logic into focused modules.
4. Centralize Confluence transport, document parsing, and file persistence.
5. Address pagination, partial failures, and other observable correctness changes separately, with explicit compatibility tests.
6. Add CI enforcement; the Ruff and Windows work can proceed independently of the larger module refactoring.

Keep each change small enough to review and validate independently. Avoid combining module moves with output or exit-code changes.

## Progress

- [x] Step 1a: Extract `build_parser()` from `main()` in [zaira/cli.py](zaira/cli.py) (parser construction now side-effect-free and testable). Merged: PR #8.
- [x] Step 1b: Add CLI contract tests ([tests/test_cli_parser.py](tests/test_cli_parser.py)) covering the full command/subcommand tree, help exit codes and stdout routing, `-V`, unknown-command and missing-argument exit codes/stderr routing, representative argument defaults, and `--format` choices. Merged: PR #8.
- [x] Step 2a: Introduce `ResourceFetchFailed` in [zaira/errors.py](zaira/errors.py) and split every "except Exception: return []/None" fetch helper matching that shape into a raising `_fetch_X()` plus a compatibility-adapter public function (no observable behavior change): `export.get_comments/get_linked_tests/get_issue_properties/get_pull_requests`, `confluence_api.get_space_root_folders/get_child_folders`, `boards.get_board_info`, `init.discover_components/discover_labels/discover_boards`. Merged: PR #9.
  - Deliberately left alone (different shape): `dashboard.py`'s per-gadget best-effort lookups and unused `get_dashboard_raw`; `info.get_field_name` (display fallback, not completeness).
  - Not yet done: making any boundary actually *act* on `ResourceFetchFailed` (e.g. `export_ticket` reporting a partial export, `resolve_folder_path` aborting instead of risking a duplicate folder) -- that's a separate, explicit behavior-fix per the plan's compatibility rule, and `resolve_folder_path`/`resolve_folder_path_from_parent` still can't see the distinction at all since they go through the overridable public functions to keep the test-injection seam working.
- [x] Step 2b: Introduced `ExportResult` (`status`, `path`, `pending_attachments`, `attachment_failures`) in [zaira/export.py](zaira/export.py); `export_ticket()` now returns it instead of `bool | list[PendingAttachment]`, and non-deferred downloads that fail are recorded in `attachment_failures` instead of being silently discarded. Updated all callers (`export_command`, `get.py`'s `get_command`, `refresh.py`, `report.py`) to check `.status == "success"` and consume `.pending_attachments`; no observable CLI behavior changed (same stdout, exit codes, download timing). `attachment_failures` is populated but not yet acted on by any caller -- that, and `get_command()`'s own discarding of its deferred-download outcomes, remain for section 5.
- [ ] Step 3: Split export and wiki synchronization logic into focused modules.
- [ ] Step 4: Centralize Confluence transport, document parsing, and file persistence.
- [ ] Step 5: Address pagination, partial failures, and other observable correctness changes separately.
- [ ] Step 6: Add CI enforcement (Ruff, Windows job).

## Review validation baseline

- Unit tests: 1,523 passed, one skipped using `.venv/bin/pytest -q -m 'not integration'`.
- Type checks: passed using `.venv/bin/ty check --python .venv`.
- Formatting: passed using `ruff format --check .`.
- Lint: `ruff check .` reported four issues in `tests/test_export.py`: one unused import and three missing return annotations.
- No live-service integration testing was performed.
- No implementation files were changed as part of the review.
