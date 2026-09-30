# Code Review: Plugin Lifecycle Management

- Review scope: `main..7662337` (round two, covering all round-one changes)
- Main change: `skills/install-plugin/scripts/importer.py` (+392/-39, now 1108 lines),
  `tests/test_importer.py` (+314)
- Dimensions: Conventions / Architecture / Regression / Test / Performance
- Acceptance state: 74 tests pass, `check_opencode.py` passes, 26 functional matrix items
  pass

## Fix status

Both must-fix items were fixed on the same branch with regression tests added (see the
"✅ Fixed" markers below). Suggested items 3, 4 and 5 were also adopted. Item 6 is a
documentation addition, covered in the README. Items 7 and 9 are structural preferences and
were not changed this round.

## 🚫 Must fix

### 1. ✅ Fixed — `--prune-snapshots` deletes an in-use snapshot based on a damaged manifest (data loss)

`skills/install-plugin/scripts/importer.py:626-651`

`prune_snapshots()` treats the manifest's `snapshot` value as the only source of truth for
"still referenced", but `state_read()` (importer.py:674-685) only validates `version` and
that `plugins` is a dict — it does **not** validate the `snapshot` field format. Format
validation exists only in `check_owned()` (importer.py:735), which pruning does not go
through.

Reproduced by corrupting the manifest's `snapshot` to `"BOGUS"` and then pruning:

```
PRUNE .plugin-importer/sources/rv/76c9a3f92ea618318c74988c
Removed 1 unreferenced snapshot(s).
$ ls dest/skills/     → rv3-a.md became a dangling symlink
$ ls dest/.plugin-importer/sources/rv/  → No such file or directory
```

The spec's "Risks and open questions" explicitly required "if the manifest is damaged, stop
rather than guess", which was not implemented. Any manifest damage (manual edit, disk
failure, abnormal termination) leads to **deleting a resource that is in use**.

**Suggestion**: validate each snapshot record before pruning and `fail()` on a malformed
one instead of guessing. Reuse `check_owned()`'s prefix check, or extract a
`validate_snapshot_record(snapshot)` shared by both.

**Fix**: extracted `validate_snapshot_record(root, snapshot)`, which validates the prefix,
`..` path segments and symlinks together. `prune_snapshots()` calls it per item and
`check_owned()` now shares the same function. Added
`test_prune_refuses_when_snapshot_record_malformed` (which does fail when the fix is
reverted), and confirmed that with a damaged manifest the live snapshot and its symlink are
both preserved. The prune call was also moved inside `main()`'s exception handling, replacing
a traceback with a clear `Import failed:` message.

### 2. ✅ Fixed — `--uninstall` with a component filter creates permanent orphans

`skills/install-plugin/scripts/importer.py:1005-1015` (`state['plugins'].pop(target, None)`
in `uninstall_plugin()`)

`uninstall_plugin()` unconditionally removes the whole namespace from the manifest, but
`make_plan()` only removes items whose `kinds` match. So `--uninstall --skills-only` removes
the skill but keeps the agent symlink and the MCP entry, while deleting the namespace record
entirely.

Reproduced with `--uninstall --skills-only` on a source containing a skill, an agent and
MCP:

```
REMOVE skills/rv3-s
manifest → {"plugins": {}, "version": 1}
dest/agents/rv3-a.md  → still present (dangling or valid)
opencode.json mcp     → still contains rv3-api
re-run --uninstall    → Import failed: Plugin is not installed. Installed: (none).
```

The result is that the agent symlink and MCP entry can **never be removed by the tool
again** (the manifest no longer has a record, so `check_owned()` treats them as unmanaged
and never adopts them), and the user can only delete them by hand. This directly violates the
reversibility promised by the spec's "remove manifest-owned and unmodified components", and
conflicts with the project's model where manifest ownership is the single source of truth.

**Suggestion**: only `pop` the namespace when `retained` is empty; otherwise keep the
namespace and update its `items` to the remaining entries so a later `--uninstall` can
finish.

**Fix**: when `retained` is non-empty the namespace is kept and its `items` replaced with the
remaining entries; the output becomes
`Removed selected <ns> items from <root>; still managed: …` and tells the user to re-run
`--uninstall`. Added `test_uninstall_with_filter_keeps_namespace_record` (which does fail
when the fix is reverted), and confirmed by hand that a second `--uninstall` completes the
cleanup, removing both the agent symlink and the MCP entry.

## ⚠️ Suggested fixes

### 3. ✅ Fixed — `install()` and `main()` take two divergent paths for uninstall

`skills/install-plugin/scripts/importer.py:917` and `importer.py:1067-1080`

When `source is None`, `main()` called `uninstall_plugin()` directly, while a path with a
source reached the same function through `install()`. The error handling and return-value
handling differ between the two paths (the former wraps its own try/except printing
`Import failed`). They currently behave the same, but the duplication means a future change
to one is easy to miss in the other.

**Fix**: `main()` no longer calls `uninstall_plugin()` itself; it sets `args.source` and
goes through `install()`, leaving a single path for error handling and return values.

### 4. ✅ Fixed — unused variable in `save_local_patch()`

`skills/install-plugin/scripts/importer.py:602`

`fresh = root / snapshot` was assigned and never used (the next line recomputes `old_path`).
Removed.

### 5. ✅ Fixed — `prune_snapshots()` always returns `True`

`skills/install-plugin/scripts/importer.py:618-655`

Every path returns `True`, but `main()` used `return 0 if prune_snapshots(...) else 1` to
decide the exit code. The boolean interface is therefore meaningless and implies a failure
path that does not exist.

**Fix**: it now returns `None` and `main()` returns `0` directly; real failures are
expressed by raising.

### 6. `--keep-local` temporary directory is left behind

`skills/install-plugin/scripts/importer.py:598`

The directory and patch created by `tempfile.mkdtemp()` persist indefinitely in the system
temporary area. This is reasonable for "preserve the user's data" (it must not be
auto-cleaned), but the README should tell users explicitly that the patch is not deleted
automatically and must be saved. The README now describes the path and notes that it is not
removed automatically.

## 💡 Optional improvements

### 7. `check_owned()` and `make_plan()` now take 9-10 parameters

`skills/install-plugin/scripts/importer.py:727`, `760`

`make_plan()` has 10 parameters, many passed positionally or defaulted. Continued growth
raises the risk of misalignment (round one already had a positional-argument bug in
`build_payload()`). Consider collapsing `reset` / `skipped` / `reset_needed` into a single
options object or `NamedTuple`.

### 8. The file list from `snapshot_changes()` is a conservative approximation

`skills/install-plugin/scripts/importer.py:568-585`

The original source is unavailable for comparison, so the whole snapshot is listed. The
docstring and output message honestly say "may include mtime-only changes", which is
acceptable. Making it exact would require storing the source path and a baseline hash in the
manifest, which is more expensive.

### 9. `importer.py` has reached 1108 lines

A single module now carries source discovery, conversion, planning, transactions, lifecycle
management and the CLI. Consider extracting the lifecycle functions (`print_status`,
`prune_snapshots`, `snapshot_changes`, `save_local_patch`, `uninstall_plugin`) into a
separate module. A structural preference, not blocking.

## Review dimensions in detail

### Conventions
- Naming follows snake_case verb/noun conventions; `uninstall_plugin`, `prune_snapshots`,
  `snapshot_changes`, `save_local_patch` and `print_status` are semantically clear.
- `MIGRATION_LOG` was made caller-owned in round one, so there is no module-level mutable
  state.
- Constants use UPPER_SNAKE_CASE correctly; no new magic numbers this round.
- Python project, so the TypeScript and path-alias rules in the conventions document do not
  apply.
- No new dependencies (`difflib` is standard library), so technology selection carries no
  risk.

### Architecture
- The new functions each have a single responsibility; `print_status` and `prune_snapshots`
  state their read-only or scoped nature explicitly.
- `uninstall` correctly reuses the existing `make_plan()` and `check_owned()` rather than
  creating a parallel flow, and naturally refuses when a component is locally modified,
  matching the "refuse and keep" decision.
- Default paths stay strict and all new flags are opt-in, satisfying the AGENTS.md
  invariants.
- The split path in item 2 and the parameter growth in item 7 are the main structural risks.
- It reuses `destination_path()` for path safety checks instead of concatenating paths
  itself, which is the right direction.

### Regression
- All four round-one fixes are retained (confirmed by the live acceptance matrix).
- Default behaviour is unchanged: without new flags it matches the `main` version, and the
  74 tests cover the original 54.
- Items 1 and 2 are real data-loss paths introduced by this round's new features and must be
  fixed.
- Transaction boundaries are untouched: `uninstall_plugin()` runs under `install_lock()` and
  `prune_snapshots()` either takes no writes or deletes only; `--dry-run` was verified by
  hand to write nothing.
- `apply_transaction()` is unchanged, so rollback semantics are identical.

### Test
- 20 new tests (54 → 74) cover the success, failure and edge paths of all five flags.
- Acceptance added the CLI-layer tests (`test_reset_combines_with_uninstall_on_cli` and
  others), closing round one's "only test the API, not argparse" blind spot.
- **Gap 1**: no test covered `--prune-snapshots` behaviour when the manifest `snapshot` field
  is damaged, which is the source of item 1. Added
  `test_prune_refuses_when_snapshot_record_malformed`.
- **Gap 2**: no test covered `--uninstall` combined with a component filter, which is the
  source of item 2. Added `test_uninstall_with_filter_keeps_namespace_record`.
- Test names describe behaviour, fixtures follow the existing `self.skill()` / `self.json()`
  conventions, and there is no flakiness risk.

### Performance
- `prune_snapshots()` iterates directories twice, O(n) in the number of namespaces, which is
  negligible.
- `snapshot_changes()` calls `tree_hash()` (O(files)) per snapshot, duplicating work already
  done by `check_owned()`. It only runs under `--reset` at skill-tree scale, so it is
  acceptable; if optimizing, pass the result along the chain.
- `save_local_patch()` calls `read_text()` per file, only under `--keep-local`.
- No database, network or concurrency concerns.
- Import cost for a 1108-line `importer.py` is negligible (standard library plus PyYAML).
