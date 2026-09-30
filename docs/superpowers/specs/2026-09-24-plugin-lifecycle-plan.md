# Plugin Lifecycle Management Implementation Plan

- Spec: docs/superpowers/specs/2026-09-24-plugin-lifecycle-spec.md
- Branch: feature/plugin-lifecycle
- Execution: use the executing-plans skill; the main session runs each task in order

## Task 1: Add `--status` for read-only inspection of installed plugins

- **Estimate**: `1h`
- **Files to change**: `skills/install-plugin/scripts/importer.py`,
  `tests/test_importer.py`
- **Steps**:
  1. Add `print_status(root)` after `state_read()`. It resolves `root`, calls `state_read(root)`,
     prints `No plugins installed.` and returns when `state['plugins']` is empty; otherwise it
     iterates `sorted(state['plugins'].items())`.
  2. For each namespace print `PLUGIN <namespace>` (blank line separated), `  source: …`,
     `  plugin: …`, `  ref: <entry['ref'] or '(unpinned)'>` and
     `  revision: <entry['revision'] or '(local working copy)'>`.
  3. For each `sorted(entry['items'].items())` print
     `    <export> [<kind>] snapshot=<snapshot> present=<yes|no>`. `present` is
     `export[4:] in config.get('mcp', {})` for MCP items (call `config_read(root)` once before
     the loop and reuse it, never inside the loop) and `(root / export).is_symlink()` otherwise.
  4. In `main()`, change `source` to optional: `parser.add_argument('source', nargs='?')`. When
     `args.source` is None: if `args.status` then `print_status(args.config_dir)` and
     `return 0`; otherwise `parser.error('source is required unless --status is given')`.
  5. Add `--status` (`action='store_true'`, help: `Show installed plugins, source and
     revision without a source argument`).
  6. Confirm `print_status()` never calls `apply_transaction()` and writes nothing.
- **Tests**: add to `tests/test_importer.py`
  - `test_status_lists_namespace_source_and_revision`: after installing, run
     `im.main(['--config-dir', str(self.dest), '--status'])` and assert stdout contains
     `PLUGIN demo`, `source:`, `revision:` and `skills/demo-hello`.
  - `test_status_requires_no_source_and_writes_nothing`: install, capture `self.snapshot()`,
     run the same command, assert exit 0 and that the snapshot is unchanged.
  - `test_status_without_install_reports_empty`: assert exit 0 and
     `No plugins installed.` in stdout.
  - `test_source_still_required_without_status`: `im.main(['--config-dir', str(self.dest)])`
     raises `SystemExit` from `parser.error`.
- **Acceptance**: run `.venv/bin/python -m unittest tests.test_importer.ImporterTests.test_status_lists_namespace_source_and_revision tests.test_importer.ImporterTests.test_status_requires_no_source_and_writes_nothing tests.test_importer.ImporterTests.test_status_without_install_reports_empty tests.test_importer.ImporterTests.test_source_still_required_without_status -v`; all four report `OK`.
- **Parallelizable**: no. Tasks 3 and 4 build on the `main()` parameter structure from
  Task 1.

## Task 2: Add `--reset` and `--keep-local` to escape the snapshot dead end

- **Estimate**: `2h`
- **Depends on**: Task 1 (`main()` parameter structure).
- **Files to change**: `skills/install-plugin/scripts/importer.py`,
  `tests/test_importer.py`
- **Steps**:
  1. Add `snapshot_changes(root, old_items)`: walk the distinct `snapshot` paths across all
     manifest items, compare `tree_hash()` against each item's `snapshot_hash`, and return a
     list of `(snapshot relative path, [file relative paths])` for mismatches. The original
     source is not available here, so use "the tree hash differs, therefore list every file in
     that snapshot" and note in the label that this may include mtime-only changes.
  2. Add `reset=False` to `check_owned()`. In the branch where the directory is missing or the
     hash differs: if `reset` is false keep the current `fail()`; otherwise record the
     snapshot in the caller-provided `reset_needed` set and continue. The signature becomes
     `check_owned(root, export, old, config, checked, reset=False, reset_needed=None)`.
  3. Add `reset=False` and `reset_needed=None` to `make_plan()` and pass them to
     `check_owned()`. When `reset_needed` is non-empty, print
     `Will discard local modifications in snapshot(s):` followed by each file before
     returning. This also runs under `preview` (it is a dry-run style report).
  4. Add `reset=False` and `keep_local=False` to `install()`. When `reset` is set: call
     `snapshot_changes()` and print the list; if `keep_local` is set, write the diff with
     `difflib.unified_diff` comparing each snapshot file against its counterpart in `staging`
     (skipping unreadable/non-text files with a note) into
     `tempfile.mkdtemp(prefix='opencode-importer-local-')/<namespace>-local.patch` and print
     the path. When there is no difference, print `No local modifications to keep.`
  5. Allow overwriting an existing snapshot under `reset`: the current
     `fail('Snapshot path is occupied by modified or unrelated content.')` may only fire when
     `reset` is false. A modified snapshot has already been let through by `check_owned()`,
     so it is replaced with `changes.insert(0, (str(snapshot), ('tree', staging)))`.
  6. Add `--reset` (`action='store_true'`, help: `Discard local modifications inside managed
     snapshots and reinstall`) and `--keep-local` (`action='store_true'`, help: `With
     --reset, save local snapshot modifications as a patch before discarding`) to `main()`.
     Put both in the existing `mode` mutually exclusive group so they cannot be combined
     with `-i` / `-f`.
  7. Reject `--keep-local` without `--reset` via `parser.error`.
- **Tests**: add to `tests/test_importer.py`
  - `test_reset_lists_then_discards_snapshot_modification`: install → modify
     `.plugin-importer/sources/demo/<key>/skills/hello/SKILL.md` (read the key from the
     manifest) → re-running without the flag raises `Local snapshot modified or missing` →
     re-run with `reset=True`; stdout contains `Will discard local modifications` and the
     file content is restored from the source.
  - `test_reset_is_opt_in`: after modifying the snapshot, a re-run without `reset` must raise.
  - `test_keep_local_writes_patch`: with `reset=True, keep_local=True`, stdout contains
     `.patch`, the file exists, and its content contains `MY LOCAL EDIT`.
- **Acceptance**: run `.venv/bin/python -m unittest tests.test_importer.ImporterTests.test_reset_lists_then_discards_snapshot_modification tests.test_importer.ImporterTests.test_reset_is_opt_in tests.test_importer.ImporterTests.test_keep_local_writes_patch -v`; all three report `OK`.
- **Parallelizable**: no. Tasks 3 and 4 rely on the new `check_owned()` / `make_plan()`
  signatures.

## Task 3: Add `--uninstall` to remove an installed plugin

- **Estimate**: `1h30m`
- **Depends on**: Task 2 (new `check_owned()` / `make_plan()` signatures).
- **Files to change**: `skills/install-plugin/scripts/importer.py`,
  `tests/test_importer.py`
- **Steps**:
  1. Add `--uninstall` to `main()` (`action='store_true'`, help: `Remove a managed plugin and
     its MCP entries without touching unmanaged files`), in the `mode` mutually exclusive
     group.
  2. Add `uninstall=False` to `install()`. When set, run the removal path after
     `state_read(root)` without calling `build_payload()` (no reconversion needed):
     - `entry = state['plugins'].get(namespace)`; if None then
       `fail(f'Plugin is not installed: {namespace}')`.
     - `kinds` uses the passed value (all KINDS by default) so `--uninstall --skills-only`
       removes only skill items.
     - `retained, changes, merged = make_plan(root, state, namespace, {}, kinds, 'uninstall',
       preview, ask, frozenset(), reset)`.
  3. `make_plan()` supports `mode='uninstall'`: with `desired` empty, `selected` contains only
     existing manifest items, and `action = 'REMOVE'` already holds because `item is None`.
     `mode == 'interactive'` can still confirm per item.
  4. Keep locally modified components: `make_plan()` still calls `check_owned()` in uninstall
     mode, so a modified snapshot or MCP value still fails, matching the "refuse and keep"
     decision. `--uninstall` without `--reset` relaxes nothing.
  5. After removal, delete the namespace from the manifest with
     `state['plugins'].pop(namespace, None)`. Note the existing
     `if not changes and retained == (old or {}).get('items', {})` check: in uninstall mode
     `retained` is `{}` while `old['items']` is not, so it is not misreported as
     `No changes.`
  6. The success message becomes `Removed {namespace} from {root}.`; other modes keep
     `Installed ...`.
- **Tests**: add to `tests/test_importer.py`
  - `test_uninstall_removes_links_mcp_and_manifest`: install a skill, agent and MCP →
     `self.install(uninstall=True)` → assert `skills/` and `agents/` are empty or absent, the
     MCP key is gone from `opencode.json`, and the manifest `plugins` is an empty dict.
  - `test_uninstall_refuses_when_snapshot_modified`: after modifying a snapshot file,
     `self.install(uninstall=True)` raises `Local snapshot modified or missing` and the skill
     symlink still exists (no partial removal).
  - `test_uninstall_leaves_unmanaged_files`: place a file in `self.dest/'skills'` that the
     manifest does not manage; after `uninstall=True` it still exists.
  - `test_uninstall_with_reset_removes_modified`: after modifying the snapshot,
     `self.install(uninstall=True, reset=True)` succeeds.
- **Acceptance**: run `.venv/bin/python -m unittest tests.test_importer.ImporterTests.test_uninstall_removes_links_mcp_and_manifest tests.test_importer.ImporterTests.test_uninstall_refuses_when_snapshot_modified tests.test_importer.ImporterTests.test_uninstall_leaves_unmanaged_files tests.test_importer.ImporterTests.test_uninstall_with_reset_removes_modified -v`; all four report `OK`.
- **Parallelizable**: no. Shares the `check_owned()` signature with Task 2.

## Task 4: Add `--prune-snapshots` to reclaim unused snapshots

- **Estimate**: `1h`
- **Depends on**: Tasks 2 and 3.
- **Files to change**: `skills/install-plugin/scripts/importer.py`,
  `tests/test_importer.py`
- **Steps**:
  1. Add `prune_snapshots(root, preview=False)`: call `state_read(root)`, build
     `referenced = {v.get('snapshot') for entry … for v in entry['items'].values()}`, obtain a
     safe path with `destination_path()` for `.plugin-importer/sources`, and for each namespace
     directory that exists and is not a symlink, list its child directories. A child whose
     `f'.plugin-importer/sources/{namespace}/{child.name}'` is not in `referenced` is printed
     as `PRUNE <path>` and queued for deletion.
  2. When `preview` is set, print `Dry run: no snapshot removed.` and return. Otherwise
     `shutil.rmtree()` each queued path, then `rmdir()` the namespace directories if empty
     (ignoring `OSError`).
  3. Check `is_symlink()` on every target before deleting so a link cannot cause deletion
     outside the destination.
  4. Add `--prune-snapshots` (`action='store_true'`, help: `Delete managed snapshots no
     longer referenced by any installed item`) to `main()`, outside the mutually exclusive
     group so it can be combined with `--dry-run`.
  5. `--prune-snapshots` must work when `args.source` is None: order the no-source branches as
     `--status` → `--prune-snapshots` → `parser.error`.
  6. Confirm pruning never deletes a referenced snapshot: the manifest is the only source of
     truth.
- **Tests**: add to `tests/test_importer.py`
  - `test_prune_snapshots_removes_only_unreferenced`: install three times with different
     content (`self.skill('hello', body=…)`), confirm three directories under
     `sources/demo/`, call `im.prune_snapshots(self.dest)`, and confirm only the one referenced
     by the manifest remains.
  - `test_prune_snapshots_dry_run_keeps_everything`: as above but with `preview=True`; the
     directory count must not change.
  - `test_prune_then_rerun_reports_no_changes`: after pruning, `self.install()` must print
     `No changes.`, proving nothing needed was deleted.
- **Acceptance**: run `.venv/bin/python -m unittest tests.test_importer.ImporterTests.test_prune_snapshots_removes_only_unreferenced tests.test_importer.ImporterTests.test_prune_snapshots_dry_run_keeps_everything tests.test_importer.ImporterTests.test_prune_then_rerun_reports_no_changes -v`; all three report `OK`.
- **Parallelizable**: no. Requires the manifest-removal semantics settled in Task 3.

## Task 5: Update documentation and verify no regression

- **Estimate**: `1h`
- **Depends on**: Tasks 1-4 complete. Produces the five flags `--status`, `--reset`,
  `--keep-local`, `--uninstall` and `--prune-snapshots`, plus
  `check_owned(root, export, old, config, checked, reset=False, reset_needed=None)`,
  `make_plan(root, state, namespace, desired, kinds, mode, preview, ask, skipped, reset,
  reset_needed)`, `print_status(root)`, `snapshot_changes(root, old_items)` and
  `prune_snapshots(root, preview=False)`.
- **Files to change**: `README.md`, `skills/install-plugin/SKILL.md`, `docs/validation.md`
- **Steps**:
  1. Add a "Lifecycle" section to `README.md` covering: re-running (reporting
     `No changes.`), updating, `--status`, `--uninstall`, `--prune-snapshots` and `--reset`.
     State explicitly that `--reset` discards local modifications inside a snapshot and that
     `--keep-local` can save a patch first.
  2. Update the snapshot paragraph in `README.md`: replace "no automatic garbage collection"
     with a description of `--prune-snapshots` as the manual reclamation mechanism.
  3. Update the procedure in `skills/install-plugin/SKILL.md` with update and uninstall
     scenarios and guidance for a locally modified snapshot.
  4. Update the test count and new coverage list in `docs/validation.md`.
  5. Run the full verification: `.venv/bin/python -m unittest discover -s tests`,
     `bash -n skills/install-plugin/scripts/install-plugin.sh` and
     `.venv/bin/python tests/check_opencode.py` (needs the opencode CLI).
  6. Follow acceptance item 8 of the spec with the real CLI: first install → re-run (expect
     `No changes.`) → update the source → `--status` → `--uninstall`, always pointing
     `--config-dir` at a temporary directory, and confirm `~/.config/opencode` is untouched.
- **Tests**: this task adds no tests; it updates documentation and runs the full regression
  verification.
- **Acceptance**: `.venv/bin/python -m unittest discover -s tests` shows everything passing
  with a count no lower than the existing 54; `bash -n skills/install-plugin/scripts/install-plugin.sh`
  produces no output; `tests/check_opencode.py` prints `OpenCode discovered the imported
  skill and agent and connected to the synthetic MCP.`
- **Parallelizable**: no. Consolidates the documentation for all flags.

## Checklist

* [ ] `6h30m`: Plugin lifecycle management
    * [ ] `1h`: Task 1 `--status` read-only inspection
    * [ ] `2h`: Task 2 `--reset` and `--keep-local`
    * [ ] `1h30m`: Task 3 `--uninstall`
    * [ ] `1h`: Task 4 `--prune-snapshots`
    * [ ] `1h`: Task 5 documentation and regression verification

### Total estimate

`6h30m`
