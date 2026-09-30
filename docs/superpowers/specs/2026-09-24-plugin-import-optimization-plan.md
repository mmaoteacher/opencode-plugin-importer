# Plugin Import Optimization Implementation Plan

- Spec: docs/superpowers/specs/2026-09-24-plugin-import-optimization-spec.md
- Branch: feature/plugin-import-optimization
- Execution: use the executing-plans skill; the main session runs each task in order

## Task 1: Add automatic name correction (`--fix-names`)

- **Estimate**: `1h`
- **Files to change**: `skills/install-plugin/scripts/importer.py`, `tests/test_importer.py`
- **Steps**:
  1. Add `normalize_name(value)` to `importer.py`: coerce an arbitrary string into a legal
     name (`re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')`); truncate to 64 characters
     and strip trailing hyphens; `fail()` when the result is empty.
  2. Add a `fix=False` parameter to `valid_name`. When the name is invalid and `fix` is true,
     use `normalize_name()` and `warn(f'Renamed {value!r} to {fixed!r}')`; otherwise keep the
     current `fail()`.
  3. Pass the flag through the four name validations: `discover()` (importer.py:217),
     `entries()` (importer.py:244), `mcp_entries()` (importer.py:277) and `build_payload()`
     (importer.py:458, 473).
  4. Add `--fix-names` to `main()` (`action='store_true'`, help: `Normalize lowercase
     invalid names instead of failing`) and thread it through `install()` and
     `build_payload()`.
  5. Keep `valid_name()` strict by default so `check_owned()` (importer.py:529) keeps
     validating manifest ownership strictly.
- **Tests**: add to `tests/test_importer.py`
  - `test_fix_names_normalizes_mcp_and_agent_names`: a source with a `GitLab` MCP server and
    a `My-Agent` skill installs with `fix_names=True`, producing `mcp/demo-gitlab` and
    `skills/demo-my-agent`.
  - `test_fix_names_absent_still_fails`: the same source without `fix_names` raises
    `ValueError` containing `Invalid name`.
- **Acceptance**: run `.venv/bin/python -m unittest tests.test_importer.ImporterTests.test_fix_names_normalizes_mcp_and_agent_names tests.test_importer.ImporterTests.test_fix_names_absent_still_fails -v`; both report `OK`.
- **Parallelizable**: no. Later tasks depend on this name-correction interface.

## Task 2: Add `--skip-unsupported` to skip unconvertible components

- **Estimate**: `1h30m`
- **Files to change**: `skills/install-plugin/scripts/importer.py`, `tests/test_importer.py`
- **Steps**:
  1. In the skills loop of `build_payload()` (importer.py:457-470), when an invocation/tool
     restriction is found (`disable-model-invocation`, `user-invocable: false`,
     `allowed-tools`), warn and `continue` instead of failing when `skip_unsupported` is set.
  2. In the agents loop, wrap `agent_convert(meta)` in `try/except ImportErrorDetail`; warn and
     `continue` when `skip_unsupported` is set, otherwise re-raise.
  3. At the failure points of `mcp_entries()` and `mcp_convert()`, skip that server entry with
     a warning when `skip_unsupported` is set, and continue converting the rest.
  4. Add `--skip-unsupported` to `main()` (`action='store_true'`, help: `Skip components
     OpenCode cannot represent instead of failing`), following the Task 1 parameter pattern.
  5. Keep skipped items out of `desired` so `make_plan()` produces no changes for them, which
     satisfies "a partial update must not change the snapshot of unselected components".
- **Tests**: add to `tests/test_importer.py`
  - `test_skip_unsupported_imports_remaining`: a source with a normal skill, a skill using
    `allowed-tools`, and an agent with `model: sonnet`; with `skip_unsupported=True` only the
    convertible items are installed and `im.warn` is called at least twice.
  - `test_skip_unsupported_disabled_still_fails`: without the flag, raises `ValueError`
    containing `invocation/tool restrictions` or `Model alias`.
- **Acceptance**: run `.venv/bin/python -m unittest tests.test_importer.ImporterTests.test_skip_unsupported_imports_remaining tests.test_importer.ImporterTests.test_skip_unsupported_disabled_still_fails -v`; both report `OK`.
- **Parallelizable**: no. Requires the `fix_names` parameter from Task 1.

## Task 3: Print a manual migration list on failure

- **Estimate**: `1h`
- **Files to change**: `skills/install-plugin/scripts/importer.py`, `tests/test_importer.py`
- **Steps**:
  1. Add a module-level `MIGRATION_LOG = []` to `importer.py`; append `(export,
     source_relative_path)` whenever `build_payload()` writes a `desired` entry.
  2. Clear `MIGRATION_LOG` at the start of `build_payload()` so a single run never accumulates.
  3. In the `except` block of `main()` (importer.py:773-775), after printing
     `Import failed: {exc}`, print the converted paths mapped to their intended
     `~/.config/opencode` destinations, and tell the user to merge `opencode.jsonc` manually.
  4. Keep the existing behaviour that a failure writes nothing to the destination.
- **Tests**: add to `tests/test_importer.py`
  - `test_failure_prints_manual_migration_list`: a source with one normal and one unsupported
     skill, no `skip_unsupported`; captured `stderr` contains `Manual migration list` and the
     skill's source path, and no destination file is created.
- **Acceptance**: run `.venv/bin/python -m unittest tests.test_importer.ImporterTests.test_failure_prints_manual_migration_list -v`; it reports `OK`.
- **Parallelizable**: no. This task writes to `MIGRATION_LOG` inside `build_payload()`, the
  same function Tasks 1 and 2 modify.

## Task 4: Add `--manual-mode` to emit a migration script

- **Estimate**: `1h30m`
- **Files to change**: `skills/install-plugin/scripts/importer.py`, `tests/test_importer.py`
- **Steps**:
  1. Add `manual=False` to `install()`. Before `install_lock()`, when `manual` is set, build a
     shell script from `desired` and `MIGRATION_LOG`, print it and return without calling
     `state_read()`, `make_plan()` or `apply_transaction()`.
  2. Script content: for each `skills/<name>`, `mkdir -p "$DEST/skills/<name>"` plus
     `cp -R "<source_path>/." "$DEST/skills/<name>/"`; for each `agents/<name>.md`,
     `mkdir -p "$DEST/agent"` plus `cp "<source_path>" "$DEST/agent/<name>.md"`. Define
     `DEST="${1:-$HOME/.config/opencode}"` at the top and note at the end that MCP settings
     must be merged into the `mcp` block of `$DEST/opencode.jsonc` by hand.
  3. Add `--manual-mode` to `main()` (`action='store_true'`, help: `Print a copy script for
     manual migration without writing the destination`); like `--dry-run` and `--list` it
     must not write the destination.
  4. Thread `manual` alongside `fix_names` and `skip_unsupported`.
- **Tests**: add to `tests/test_importer.py`
  - `test_manual_mode_prints_script_and_skips_writes`: with `manual=True`, stdout contains
     `DEST=`, `cp -R`, the skill name and the agent name, and `self.dest` does not exist.
  - `test_manual_mode_with_dry_run_flags`: `manual=True, dry_run=True` does not raise and
     stdout still contains only the script, not `Dry run:`.
- **Acceptance**: run `.venv/bin/python -m unittest tests.test_importer.ImporterTests.test_manual_mode_prints_script_and_skips_writes tests.test_importer.ImporterTests.test_manual_mode_with_dry_run_flags -v`; both report `OK`.
- **Parallelizable**: no. Integrates the parameters from Tasks 1-3.

## Task 5: Verify the MCP merge result and update documentation

- **Estimate**: `1h`
- **Files to change**: `skills/install-plugin/scripts/importer.py`, `tests/test_importer.py`,
  `docs/validation.md`, `skills/install-plugin/SKILL.md`
- **Depends on**: Tasks 1-4 complete.
- **Produces**: the `--fix-names`, `--skip-unsupported` and `--manual-mode` options and the
  `importer.MIGRATION_LOG` list.
- **Steps**:
  1. Before writing `opencode.json` in `make_plan()` (importer.py:604-614), verify
     `updated_config` round-trips through `json.loads(encoded(...))` and that
     `updated_config['mcp']` is still a dict; otherwise `fail(...)`.
  2. Before the success message in `install()`, when `'mcp' in kinds` and the configuration
     changed, print `MCP servers merged into <config_name>:` with the sorted server keys.
  3. Update `skills/install-plugin/SKILL.md` with the three new options and state that MCP
     settings go into the `mcp` block of `opencode.jsonc` (no separate `.json` file).
  4. Update the Automated checks section of `docs/validation.md`.
- **Tests**: add to `tests/test_importer.py`
  - `test_mcp_merge_prints_server_names`: after installing a source with one MCP server,
     stdout contains `MCP servers merged into` and the server name.
  - `test_mcp_merge_result_is_valid_json`: after install,
     `json.loads((self.dest / 'opencode.json').read_text())['mcp']` contains the server key.
- **Acceptance**: run `.venv/bin/python -m unittest discover -s tests -v`; everything reports `OK` (the existing 41 tests plus the new ones).
- **Parallelizable**: no. Integrates the behaviour of all tasks.

## Checklist

* [ ] `5h30m`: Plugin import optimization
    * [ ] `1h`: Task 1 automatic name correction
    * [ ] `1h30m`: Task 2 `--skip-unsupported`
    * [ ] `1h`: Task 3 manual migration list
    * [ ] `1h30m`: Task 4 `--manual-mode`
    * [ ] `1h`: Task 5 MCP merge verification and documentation

### Total estimate

`5h30m`
