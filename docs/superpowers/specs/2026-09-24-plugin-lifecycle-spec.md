# Plugin Lifecycle Management: Uninstall, Rescue and Status

- Source: second-round code review and live investigation (branch
  `feature/plugin-import-optimization`)
- Date: 2026-09-24
- Branch: feature/plugin-lifecycle
- Previous spec: docs/superpowers/specs/2026-09-24-plugin-import-optimization-spec.md

## Background and problem

After round one added `--fix-names`, `--skip-unsupported`, `--manual-mode` and MCP merge
verification, this round investigated "second install" and "update" scenarios by actually
running the CLI rather than reading the code. Confirmed working:

- Re-running with no source change prints `No changes.` (idempotent).
- A source update correctly reports `UPDATE`/`ADD`, and both skill contents and MCP values
  are updated.
- Git sources track the new commit in the manifest `revision`.
- Components skipped by `--skip-unsupported` are not wrongly deleted by `--force` (round-one
  fix).

Live testing confirmed four gaps, all user-observable:

1. **Editing a file inside a snapshot is a permanent dead end.** After a user edits any file
   under `.plugin-importer/sources/<ns>/<key>/`, every later import fails at `Local snapshot
   modified or missing`, and neither `--force` nor `--skip-unsupported` can recover. The
   message only says "Preserve your changes before retrying", but no command can complete
   the flow.
2. **There is no uninstall path at all.** The file contains no `uninstall` or `--clean`. Once
   a plugin is installed it can only stay forever, even after the source is abandoned.
3. **Snapshots accumulate without bound.** Every source change creates a new snapshot
   directory and keeps the old ones; the README already states there is no automatic garbage
   collection. Three versions produced three directories.
4. **Installed state cannot be inspected.** `--list` requires a source, so users cannot see
   which plugins are installed, where they came from, at which revision, or which snapshot
   each item points at. When the source path changes (for example a moved repository) the
   import is hard-refused and the message only suggests using another namespace, while the
   old plugin still occupies the name and cannot be viewed or released.

## Goals

1. `--reset`: escape the snapshot dead end, listing the local files that will be discarded
   first.
2. `--uninstall`: remove manifest-owned, unmodified components and MCP entries; refuse and
   keep everything when a component was locally modified.
3. `--prune-snapshots`: delete snapshots no longer referenced by any manifest item.
4. `--status`: read-only listing of installed plugins, source, revision, components and
   snapshots, without requiring a source argument.

## Non-goals

- No fifth source format; source support stays Claude Code / Codex / agy / OpenCode.
- No change to existing update semantics (sync / `-i` / `-f`; a partial update must not
  change the snapshot of unselected components).
- Do not automatically resolve source path conflicts (a changed source still requires the
  user to pick a namespace).
- No cross-plugin dependency resolution or version conflict checking.
- No new Python dependencies.

## Current state analysis

- `check_owned()` (in `skills/install-plugin/scripts/importer.py`) compares the snapshot
  against the manifest's `snapshot_hash` with `tree_hash()` and calls `fail()` on a mismatch.
  This is the dead end: whether the check passes is independent of the import mode, so every
  flag stops here.
- `make_plan()`'s `selected` set is `set(desired) | {manifest items whose kind matches}`,
  and `mode` decides ADD/UPDATE/REMOVE/KEEP. Uninstall can reuse this structure by treating
  `desired` as empty and expressing it with a new mode.
- The snapshot path is `.plugin-importer/sources/<ns>/<key>`, and the key includes `kinds`,
  so a partial update creates another snapshot. "Still referenced" means appearing in the
  `snapshot` field of any plugin item.
- `main()`'s `mode` is a mutually exclusive group (`-i` / `-f`); new flags must account for
  that.

## Design

### `--reset` (with `--keep-local`)

`--reset` discards local modifications inside a snapshot and reinstalls:

1. Scan the target snapshot and list the relative paths of files that do not match
   `snapshot_hash`.
2. Print a `Will discard local modifications:` list (a dry-run style report, no prompts).
3. After the user decides, reconvert from the source and overwrite that snapshot.

`--keep-local` is a variant of `--reset`: it first writes the local differences to a unified
diff file, then resets, so the user can reapply them later. Both are explicit opt-ins and the
default behaviour is unchanged.

### `--uninstall`

Reuses `make_plan()`: `desired` is empty and a new `mode='uninstall'` is added.

- Remove manifest-owned skill/agent symlinks and MCP entries whose snapshot is unmodified.
- If a snapshot was modified or an MCP value was changed locally, refuse the whole operation,
  keep everything, and suggest `--reset`.
- After removal, delete the namespace record from the manifest; do not clean up snapshots
  automatically (leave that to `--prune-snapshots`).

### `--prune-snapshots`

Collect the `snapshot` values of all plugin items as the referenced set, then delete
directories under `.plugin-importer/sources/<ns>/` that are not in it. Only delete when no
item references a directory; never touch referenced or indeterminate entries. Afterwards,
remove the namespace directory if it is empty.

### `--status`

A read-only mode that reads the manifest and lists each namespace's source, plugin, ref and
revision, plus each item's kind, snapshot and whether it is still present in the destination.
It writes nothing and does not require a source argument.

## Decision log

| Decision | Options considered | Final decision | Rationale |
|---|---|---|---|
| How to escape the dead end | `--reset` overwrites / only improve the message / both modes | `--reset` + `--keep-local` | An overwrite needs a recoverable variant; `--keep-local` covers "inspect the difference first" |
| Safety boundary for reset | list files first / reset directly / confirm per file | List the files to be discarded first | Matches the AGENTS.md invariant that force must not take over or overwrite local modifications; the decision stays with the user |
| Uninstall scope | uninstall + prune together / one of them / prune only | Both | The user wants to be able to remove an installation and to reclaim disk in one go |
| Uninstall with local modifications | refuse and keep / always remove | Refuse and keep unless `--reset` is explicit | Consistent with existing protection; local data is not discarded by default |
| Source-change handling this round | both `--status` and better messages / `--status` only | `--status` only | Source changes need a cross-plugin naming strategy; that is a larger scope, left for the next round |
| How to query state | extend `--list` / add `--status` | Add `--status` | `--list` means "list the source contents"; extending it would confuse the meaning. `--status` describes the destination state. |

## Impact

- `skills/install-plugin/scripts/importer.py`: the relaxation point in `check_owned()`, a new
  uninstall mode in `make_plan()`, new paths through `build_payload()` / `install()`, and
  four new flags plus mutual-exclusion handling in `main()`.
- `tests/test_importer.py`: tests for each scenario.
- `README.md`, `skills/install-plugin/SKILL.md`, `docs/validation.md`: documentation for the
  new flags and the update/uninstall flow.

## Acceptance plan

### Static

- `.venv/bin/python -m unittest discover -s tests` all pass (the existing 54 tests must not
  regress).
- `bash -n skills/install-plugin/scripts/install-plugin.sh` passes.
- The new flags must not cause `--list` / `--dry-run` to write the destination.

### Live

The fixture reuses round one's cosmo case and adds a git source to verify revision tracking.

1. **Reset rescue**: install → modify `SKILL.md` inside the snapshot → re-run (should fail
   and name the modified file) → `--reset` (should list the files to be discarded first, then
   complete the install) → confirm the destination is updated and the manifest
   `snapshot_hash` matches the files.
2. **keep-local**: after `--reset --keep-local`, confirm a diff file is produced and the local
   content can be recovered.
3. **Clean uninstall**: install several components and an MCP entry → `--uninstall` →
   confirm the skills/agents symlinks disappear, the MCP entry is removed from
   `opencode.json`, and the manifest no longer contains the namespace.
4. **Uninstall with local modifications**: modify a file inside the snapshot first →
   `--uninstall` should refuse and **keep** every component (no partial removal); only after
   adding `--reset` may it proceed.
5. **Uninstall does not touch unmanaged files**: place a file in `skills/` that the manifest
   does not manage → after `--uninstall` the file is still there.
6. **prune-snapshots**: after three consecutive updates, `--prune-snapshots` keeps only
   referenced snapshots; a subsequent import still reports `No changes.`, proving nothing
   needed was deleted.
7. **status**: `--status` needs no source and lists namespace, source, revision and
   components; confirm it writes nothing by comparing destination state before and after.
8. **No regression**: first install, idempotent re-run, source update, git revision tracking,
   partial updates leaving unselected component snapshots alone, and all four round-one fixes
   (`--fix-names` / `--skip-unsupported` / `--manual-mode` / MCP merge verification) all
   still work.
9. **Isolation**: every run uses `--config-dir` pointing at a temporary directory;
   `~/.config/opencode` is never touched.

## Risks and open questions

- `--reset` discards local modifications inside a snapshot and is destructive. Mitigations:
  it requires an explicit opt-in, lists the files first, and never affects user files
  outside the snapshot.
- Snapshots are recorded as relative paths, so pruning must treat the manifest as the single
  source of truth; if the manifest is damaged it should stop rather than guess. This follows
  the existing `state_read()` failure strategy.
- Source changes (a moved repository) still require manually choosing a namespace and are
  not solved this round; `--status` at least lets the user see the conflicting namespace and
  source, which helps the decision.
- Where the `--keep-local` diff file should live (temporary directory vs destination) was
  undecided. Implementation follows "do not pollute the destination" and uses a temporary
  directory, printing the path.
- What to do with files left inside a snapshot when the source no longer contains them was
  undecided. Implementation does "only restore what the manifest references; do not delete
  other files in the snapshot" and records the residual risk.
