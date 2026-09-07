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
- [x] Step 2b: Introduced `ExportResult` (`status`, `path`, `pending_attachments`, `attachment_failures`) in [zaira/export.py](zaira/export.py); `export_ticket()` now returns it instead of `bool | list[PendingAttachment]`, and non-deferred downloads that fail are recorded in `attachment_failures` instead of being silently discarded. Updated all callers (`export_command`, `get.py`'s `get_command`, `refresh.py`, `report.py`) to check `.status == "success"` and consume `.pending_attachments`; no observable CLI behavior changed (same stdout, exit codes, download timing). `attachment_failures` is populated but not yet acted on by any caller -- that, and `get_command()`'s own discarding of its deferred-download outcomes, remain for section 5. Merged: PR #10.
- [~] Step 3: Split export and wiki synchronization logic into focused modules. Paused (function-level splits done; file-level module boundaries not attempted -- see below) to move to Step 4 per the plan's suggested order.
  - [x] Extracted the sync-decision logic out of `_put_one_file()` in [zaira/wiki.py](zaira/wiki.py) into a pure `compute_sync_state()` returning a `SyncState` (`local_hash`, `local_changed`, `remote_changed`, `stored_version`, `stored_image_hashes`). It takes the already-fetched `remote_version`/`sync_meta` as input and makes no Confluence API calls itself (only local image-hash reads via the existing `check_images_changed()`). `_put_one_file()` now calls it instead of inlining the local/remote diff math; no observable behavior changed. Added `TestComputeSyncState` unit tests covering no-metadata, in-sync, local-ahead, remote-ahead, conflict, and image-changed cases.
  - [x] Split `_put_one_file()`'s four mutually-exclusive branches out into their own functions: `_print_sync_status()` (--status), `_show_diff()` (--diff), `_pull_page()` (--pull), and `_push_page()` (default push: conflict/in-sync check, diagram rendering, image upload, title/folder-move resolution, label sync, sync-property write). `_put_one_file()` is now a thin dispatcher: fetch page, compute sync state, pick a branch function. No observable behavior changed -- verified by the existing `TestPutOneFile`/`TestPutOneFileStatusCases`/`TestPutCommand` suites (which exercise all four branches) passing unchanged.
  - [ ] `_push_page()` itself still mixes rendering, image sync, title/folder-move resolution, and label sync in one function -- further splitting (e.g. a pure "what changed" plan versus the calls that execute it) is possible but not done.
  - [x] Split `export_ticket()`/`export_to_stdout()`'s fetch/enrich/format/attachment/persist mixing in [zaira/export.py](zaira/export.py) into `_enrich_ticket()` (PR/test/property sections -- was duplicated verbatim between the two functions, now shared), `_prepare_pending_attachments()` (dedup + `PendingAttachment` construction, no download), `_write_ticket_file()` (md/json/ndjson persistence), and `_create_ticket_symlinks()` (by-component/by-parent symlinks). `export_ticket()` is now a short sequence of calls to these plus the attachment-download loop; no observable behavior changed -- verified by the existing `TestExportTicket`/`TestExportToStdout` suites passing unchanged.
  - [ ] Neither `wiki.py` nor `export.py` has been split into separate *module files* yet (parsing/sync-decision/rendering/remote-ops/local-writes for wiki; fetch/enrich/format/attachment/persist for export) -- so far this step has only split responsibilities into separate functions within the same file, which is lower-risk and independently valuable, but the plan's module-boundary goal remains. Function-level splits merged: PR #10.
- [~] Step 4: Centralize Confluence transport, document parsing, and file persistence. In progress.
  - [x] Added an internal `_request()` helper in [zaira/confluence_api.py](zaira/confluence_api.py) that centralizes auth resolution and the request timeout, and converted all ~20 call sites that followed the repeated `base_url, auth = _get_auth()` + `requests.<verb>(url, ..., auth=auth, timeout=...)` pattern to call it instead. Deliberately still a thin wrapper around the `requests.get/post/put/delete` module functions rather than a `requests.Session` -- the existing test suite patches those functions directly at ~40 call sites in `tests/test_confluence_api.py`, and switching to a session would require rewriting all of them to patch `requests.Session.get/etc.` instead for uncertain benefit (each CLI invocation is a short-lived process, so connection-reuse gains are minor). No observable behavior changed -- verified by the full `test_confluence_api.py` suite (72 tests) passing unchanged.
  - Deliberately left unconverted (different shape, would change behavior if routed through `_request()`): `download_attachment()` (takes a full external URL rather than an API path, and has its own auth construction plus 401-retry-via-API-gateway logic); `get_personal_space_key()` (calls `_get_auth()` *outside* its `try/except Exception: pass`, so a missing-credentials `ValueError` propagates to the caller today -- routing it through `_request()` would move that call inside the `try` and silently swallow it instead).
  - [ ] Pagination helpers not added yet -- `get_child_pages`/`get_space_root_pages`/`get_space_root_folders`/`get_child_folders`/`get_attachments`/`search_pages` still return only the first page. Per the plan, introducing multi-page traversal is a separately-tested correctness fix (section 5: "with cases for multiple pages and failed intermediate requests"), not part of this transport-centralization pass.
  - [x] Added `atomic_write_text()` in [zaira/util.py](zaira/util.py) (write to a temp file in the same directory, then `os.replace()` into place, cleaning up the temp file on any failure) and routed the ticket-export write in [zaira/export.py](zaira/export.py)'s `_write_ticket_file()` and every schema/editmeta cache write in [zaira/info.py](zaira/info.py) (`save_field_descriptions`, `save_schema`, `_fetch_and_save_editmeta`, `_learn_editmeta_from_file`, and the inline write in `learn_command`) through it. `info.py`'s cache writes previously used the platform-default encoding rather than explicit UTF-8 (unlike `export.py`/`wiki.py`, which already passed `encoding="utf-8"`); they now do, closing the gap the plan called out. New `TestAtomicWriteText` suite in [tests/test_util.py](tests/test_util.py) covers new-file writes, overwrites, no leftover temp file on success, and -- per the plan's explicit ask -- that a failed write (`os.replace` raising) leaves the previous file's contents completely intact with no temp-file residue, for both an existing target and a not-yet-created one. No observable CLI behavior changed; full suite (1,678 passed/1 skipped), `ty check`, and `ruff check`/`ruff format --check` all pass.
  - [ ] Front-matter parsing (create/wiki/refresh) deliberately NOT consolidated -- investigated and found genuinely incompatible, not just duplicated. `refresh.py`'s `parse_front_matter` doesn't use YAML at all (naive per-line `key: value` string splitting); switching it to real `yaml.safe_load` would change behavior for values PyYAML infers a type for -- e.g. `generated: 2024-01-15` currently stays the string `"2024-01-15"` (asserted by `tests/test_refresh.py::test_parses_simple_front_matter`) but `yaml.safe_load` would parse it as a `datetime.date`. Separately, `create.py`'s and `wiki.py`'s delimiter-splitting regexes (both real YAML) were compared against a battery of edge-case inputs and do diverge in practice: trailing whitespace/blank-line handling after the closing `---`, tolerance of a missing trailing newline, and treatment of a `----`-prefixed block -- consistent with their different domains (create.py requires front matter and fails loud via `ValueError`; wiki.py treats absence or malformed YAML as "no front matter" and fails soft, per `tests/test_wiki.py::test_invalid_yaml_returns_content`). Unifying either pair while preserving each one's tested behavior would mean re-deriving two implementations behind one name, not a real reduction in risk or duplication -- so, per the compatibility constraints, this was left alone rather than folded into a code-move. Remains open if a specific unification is wanted as an explicit, separately-reviewed behavior decision.
- [ ] Step 5: Address pagination, partial failures, and other observable correctness changes separately.
- [~] Step 6: Add CI enforcement (Ruff, Windows job). In progress.
  - [x] Declared `ruff` as a dev dependency, pinned an explicit rule `select` in [pyproject.toml](pyproject.toml) (`E4, E7, E9, F, I, ANN` -- previously relied on ruff's own default selection via `extend-select`, which proved non-deterministic across ruff versions/environments: this session's ambient ruff resolved a much broader implicit default and reported 519 findings before pinning it explicitly), and added `ruff check .` / `ruff format --check .` steps to [.github/workflows/test.yml](.github/workflows/test.yml). Enabling import-sorting (`I`) required an `--fix` pass across the whole codebase (import reordering only) plus manually fixing the 4 remaining issues in `tests/test_export.py`. Full suite/ty/ruff all pass.
  - [x] `uv.lock` updated and committed with `ruff` added, using public PyPI URLs. This environment's global uv config (`~/.config/uv/uv.toml`) points at a private corporate mirror (`pypi-mirror.services.basware.com`), so a plain local `uv lock`/`uv add`/`uv sync` here rewrites every package URL to that mirror instead of the public ones the committed lockfile uses -- exactly what the plan's dependency rules warn against ("keep its registry URLs public"). Fixed via `wazup fixup uv-lock` (rewrites the mirror URLs back to `pypi.org`/`files.pythonhosted.org` in the already-resolved lockfile, no network access to the public index needed) rather than by re-resolving from this sandbox. Verified with `uv sync --locked` (resolves cleanly once `UV_DEFAULT_INDEX` matches) and confirmed on real CI (GitHub Actions) via PR #10, which merged clean.
  - [ ] Windows test job: asked, deliberately skipped for now (CI cost/time, and Windows-specific behavior can't be verified from this environment). Can be added later if wanted. Ruff/CI enforcement and uv.lock fix merged: PR #10.

## Review validation baseline

- Unit tests: 1,523 passed, one skipped using `.venv/bin/pytest -q -m 'not integration'`.
- Type checks: passed using `.venv/bin/ty check --python .venv`.
- Formatting: passed using `ruff format --check .`.
- Lint: `ruff check .` reported four issues in `tests/test_export.py`: one unused import and three missing return annotations.
- No live-service integration testing was performed.
- No implementation files were changed as part of the review.
