# Plugin Lifecycle Management Acceptance Report

- Spec: docs/superpowers/specs/2026-09-24-plugin-lifecycle-spec.md
- Plan: docs/superpowers/specs/2026-09-24-plugin-lifecycle-plan.md
- Branch: feature/plugin-lifecycle
- Date: 2026-09-24
- E2E: ➖ Not applicable (CLI tool, no front end or back end; user-observable behaviour is
  covered by real CLI runs)
- Overall result: ✅ Pass (1 CLI-layer defect found during acceptance; 2 data-loss paths
  found during code review and fixed)

## Automated checks

| Item | Command | Actual result | Result | Evidence / notes |
|---|---|---|---|---|
| Unit/integration tests | `.venv/bin/python -m unittest discover -s tests` | Ran 76 tests, OK | ✅ | 72 tests were green on entry with no regression; +2 after the acceptance fix and +2 after the code review fix |
| Shell syntax | `bash -n skills/install-plugin/scripts/install-plugin.sh` | No output, exit 0 | ✅ | |
| OpenCode live check | `.venv/bin/python tests/check_opencode.py` | Discovered the skill and agent, MCP handshake connected | ✅ | Isolated XDG environment, no model call |

## Functional acceptance matrix

Fixtures: `acc2` (two skills, one agent, one MCP), `cosmo` (reproduces round one's
unsupported case) and `git` (a git source for revision tracking). Every run points
`--config-dir` at a temporary directory.

| Spec item | Method | Action | Expected | Actual | Result | Evidence |
|---|---|---|---|---|---|---|
| Goal 1 `--reset` rescue | CLI | Install → edit `SKILL.md` inside the snapshot → re-run | Fails first | `Import failed: Local snapshot modified or missing: …`, message points at `--reset (optionally --keep-local)` | ✅ | |
| Goal 1 `--reset` takes effect | CLI | Same state plus `--reset` | Lists files, then completes the install | Prints `Will discard local modifications in snapshot(s) (may include mtime-only changes):` with the file list; content restored (`MY LOCAL EDIT` gone); prints `Installed` | ✅ | |
| Goal 1 importable after reset | CLI | Run again after the reset | `No changes.` | `No changes.` | ✅ | |
| Goal 2 `--keep-local` | CLI | Edit the snapshot, then `--reset --keep-local` | Produces a diff containing the local edit | Prints the patch path; patch contains `description: PRESERVE THIS` → `description: Alpha skill v1` and `-mine` / `+Alpha v1` | ✅ | |
| Goal 4 clean uninstall | CLI | Install 2 skills + agent + MCP, then `--uninstall` | Symlinks, MCP and manifest all cleared | Three `REMOVE` lines; `skills/` and `agents/` empty; `mcp` is `{}`; manifest `plugins` is `{}` | ✅ | |
| Goal 4 uninstall with local modification | CLI | Edit the snapshot, then `--uninstall` | Refuses and keeps everything | `Import failed: Local snapshot modified or missing…`; `skills/` still has `acc2-alpha` and `acc2-beta` (no partial removal) | ✅ | |
| Decision "proceeds only with `--reset`" | CLI | Same state with `--uninstall --reset` | Removal completes | All `REMOVE` lines and an empty manifest | ✅ | **Defect found during acceptance, see below** |
| Goal 4 unmanaged files untouched | CLI | Put `skills/MY-OWN.md` in place, then uninstall | The file remains | `MY-OWN.md` still contains `mine` | ✅ | |
| Goal 3 `--prune-snapshots` | CLI | Three consecutive updates, then prune | Keeps only the referenced snapshot | 3 → 1, prints `Removed 2 unreferenced snapshot(s).` | ✅ | |
| Goal 3 dry run | CLI | Same, plus `--dry-run` | Deletes nothing | Prints two `PRUNE` lines and `Dry run: no snapshot removed.`; count stays 3 | ✅ | |
| Goal 3 no over-deletion | CLI | Import again after pruning | `No changes.` | `No changes.` | ✅ | |
| Goal 4 `--status` | CLI | Without a source | Lists namespace, source, revision and components | Prints `PLUGIN acc2`, `source:`, `plugin: acc2`, `ref: (unpinned)`, `revision: (local working copy)` and four `present=yes` items | ✅ | |
| Goal 4 `--status` is read-only | CLI + read | Compare destination file hashes before and after | Writes nothing | Hashes identical before and after | ✅ | |
| Existing 1 first install | CLI | Fresh destination | ADD for all three component kinds | Normal | ✅ | |
| Existing 2 idempotent re-run | CLI | Re-run with no change | `No changes.` | `No changes.` | ✅ | |
| Existing 3 source update | CLI | Change the source | Correct UPDATE | Prints `UPDATE`, content updated | ✅ | |
| Existing 4 git revision tracking | CLI | Commit v2 in a git source, re-import | Revision updates | `rev1: d6a7b677d4` → `UPDATE skills/g-g` → `rev2: a1620c4a72` | ✅ | |
| Existing 5 `--fix-names` (round one) | CLI | `GitLab` MCP | Converted to lowercase with a warning | `Warning: Renamed 'GitLab' to 'gitlab'.`, installed as `cosmo-gitlab` | ✅ | |
| Existing 5 strict by default (round one) | CLI | Same fixture without the flag | Still fails | `Import failed: Skill bad uses invocation/tool restrictions…` | ✅ | |
| Existing 6 `--skip-unsupported` (round one) | CLI | Source containing unsupported items | Skips them, installs the rest | Skips `bad` and `aliased` with one warning each, installs `cosmo-ok` and `cosmo-gitlab` | ✅ | |
| Existing 6 skipped items not pruned by `-f` (round one) | CLI | Restrict an installed skill, then `-f --skip-unsupported` | Retained | `KEEP skills/o-s (skipped this run; unsupported upstream, not removed)`, file still present | ✅ | |
| Existing 7 `--manual-mode` (round one) | CLI | Run with the flag | Prints a script only | Prints `#!/bin/sh` and the conversion caveat | ✅ | |
| Existing 8 list/dry-run write nothing | CLI | `--list`, `--dry-run` | Destination not created | `ls` reports it does not exist | ✅ | |
| Isolation | Read | Inspect `~/.config/opencode` | Never written | The directory mtime predates this acceptance run; it was never touched | ✅ | |

## E2E

- Applicability: not applicable. This project is a Python CLI with no front-end pages or
  back-end APIs. User-observable behaviour is entirely command output and destination
  contents, both covered by the real runs above.
- Test basis: not applicable (no YouTrack issue; the requirement source is the live
  investigation from the round-one code review)
- Markdown report: none
- PDF report: none
- Summary: all 26 matrix items pass

## Failures and unverified items

No failing items. The following defect was found during acceptance and has been fixed.

### Defect found during acceptance: `--uninstall --reset` rejected by argparse

- **Symptom**: the spec decision explicitly requires "uninstall refuses locally modified
  components and keeps them unless `--reset` is given", but running `--uninstall --reset`
  produced `error: argument --reset: not allowed with argument --uninstall`. `--reset` had
  been placed in the `mode` mutually exclusive group.
- **Why the unit tests missed it**: the original
  `test_uninstall_with_reset_removes_modified` called `install(uninstall=True, reset=True)`
  directly, bypassing argparse, so it could not see that the flag combination is unusable at
  the CLI. This is exactly the "tested the API, not the CLI" blind spot.
- **Fix**: `--reset` was moved out of the mutually exclusive group (it is a modifier, not a
  mode, and may accompany `-f` or `--uninstall`), and two CLI-layer regression tests were
  added: `test_reset_combines_with_uninstall_on_cli` and
  `test_reset_combines_with_force_on_cli`. Both were negatively verified: putting `--reset`
  back into the exclusive group makes them fail.
- **Impact**: after the fix, the affected acceptance item ("proceeds only with `--reset`")
  passes.

## Post-acceptance fix (from code review)

Live testing during the code review found two data-loss paths this report did not cover;
both are fixed with new verification:

- `--prune-snapshots` deleted an in-use snapshot when the manifest was damaged, leaving an
  installed skill as a dangling symlink. Now every snapshot record is validated first, and a
  damaged manifest stops the command without deleting anything.
- `--uninstall --skills-only` unconditionally dropped the whole namespace record, so the
  agent symlink and MCP entry could never be removed by the tool again. The record for the
  remaining kinds is now kept and a follow-up `--uninstall` finishes the job.

See the code review report for details. After the fixes, the full verification was re-run:
76 tests pass and `check_opencode.py` passes.

## Requirement baseline differences

| Issue description | Spec decision | Impact | Open question |
|---|---|---|---|
| (no YouTrack issue) | `--uninstall` does not require a `source` argument | Implementation found that plan Task 1 only exempted `--status` and `--prune-snapshots`, so `--uninstall` still required a source and the primary scenario failed. Fixed together with a regression test. | None |
| (same) | The `--keep-local` diff lives in a temporary directory and its path is printed | Implemented in `tempfile.mkdtemp(prefix='opencode-importer-local-')`, not polluting the destination | The user must save it themselves; the system may clean the temporary directory. Documented in the README. |
| (same) | Files inside a snapshot are not proactively deleted when the source removed them | Not implemented this round; `--reset` overwrites the whole snapshot so leftovers disappear with it | If the source removed a file the user never modified, it disappears on the next update, matching upstream. Locally modified content is preserved by `--keep-local`. |
