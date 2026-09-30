# Plugin Import Optimization Acceptance Report

- Spec: docs/superpowers/specs/2026-09-24-plugin-import-optimization-spec.md
- Plan: docs/superpowers/specs/2026-09-24-plugin-import-optimization-plan.md
- Branch: feature/plugin-import-optimization
- Date: 2026-09-24
- E2E: ➖ Not applicable (CLI tool, no front end or back end; functional acceptance is
  covered by real CLI runs)
- Overall result: ✅ Pass

## Automated checks

| Item | Command | Actual result | Result | Evidence / notes |
|---|---|---|---|---|
| Unit/integration tests | `.venv/bin/python -m unittest discover -s tests` | Ran 54 tests, OK | ✅ | All 41 baseline tests retained, 13 added (the last 3 are regression tests added after the code review fix) |
| Shell syntax | `bash -n skills/install-plugin/scripts/install-plugin.sh` | No output, exit 0 | ✅ | |
| OpenCode live check | `.venv/bin/python tests/check_opencode.py` | Discovered the skill and agent, MCP handshake connected | ✅ | Isolated XDG environment, no model call, `~/.config/opencode` untouched |

## Functional acceptance matrix

The fixture reproduces the real cosmo case from `plugin-import-session.md`: an
`add-source-id` skill using `allowed-tools`, an agent with `model: sonnet`, and an MCP
server named `GitLab`.

| Spec item | Method | Action | Expected | Actual | Result | Evidence |
|---|---|---|---|---|---|---|
| Goal 1 skip unsupported | CLI | Install a plugin with three unsupported features | One unsupported item does not block the rest | 2 convertible items installed, 2 unsupported items warned and skipped, exit 0 | ✅ | `ADD mcp/cosmo-gitlab`, `ADD skills/cosmo-commit`; warnings name `zz-add-source-id` and `model: sonnet` |
| Goal 1 side condition | CLI + read | Inspect the manifest | Skipped items are not recorded as managed | `managed items: ['mcp/cosmo-gitlab', 'skills/cosmo-commit']` | ✅ | No `add-source-id` record, so a later run retries it |
| Goal 2 name correction | CLI | Same fixture with `--fix-names` | `GitLab` becomes a legal lowercase name | `Warning: Renamed 'GitLab' to 'gitlab'.`, installed as `cosmo-gitlab` | ✅ | |
| Goal 2 strict by default | CLI | Same fixture without the flag | Still fails and writes nothing | `Import failed: ... Invalid name 'GitLab'`, `dest` absent | ✅ | |
| Goal 3 manual migration list | CLI | Strict mode with partial progress | Failure lists source→destination paths, writes nothing | Prints `Manual migration list` and `.../skills/commit -> skills/cosmo-commit`; `dest` absent | ✅ | |
| Goal 3 failure semantics | CLI | Strict mode | Non-zero exit code | exit 1 | ✅ | |
| Goal 4 `--manual-mode` | CLI | Run with `--manual-mode` | Prints a script only, writes nothing | Prints `#!/bin/sh`…`DEST="${1:-$HOME/.config/opencode}"`, `cp -R`, `mkdir -p` and an MCP merge note; destination has no files | ✅ | |
| Goal 4 conversion caveat | CLI | Inspect the script header | States that frontmatter conversion is not applied | Script states "frontmatter conversion … is NOT applied" | ✅ | |
| Goal 5 MCP merged into opencode.jsonc | CLI + read | Install a plugin with MCP | Written into `mcp` of `opencode.json`, no separate json | `mcp` contains `cosmo-gitlab` (`type: local`, `command: ['glab','api']`); no `mcp-*.json` in the directory | ✅ | |
| Goal 5 merge reporting | CLI | Same | Prints the merged server names | `MCP servers merged into opencode.json: cosmo-gitlab` | ✅ | |
| Goal 5 pre-write verification | Automated | `test_mcp_merge_result_is_valid_json` | Merged document parses | Passes | ✅ | |
| Idempotent re-run | CLI | Re-run over an installed plugin | `No changes.` | `No changes.`, exit 0 | ✅ | |
| `--list` writes nothing | CLI | `--list --fix-names --skip-unsupported` | Lists components only | Lists skills/agents/mcp; `dest2` not created | ✅ | |
| `--dry-run` writes nothing | CLI | `--dry-run` | No writes, no prompts | Failure path prints "nothing was written"; `dest2` not created | ✅ | |
| Unselected component snapshot unchanged | CLI + read | Full install then `--skills-only` | The unselected MCP item's snapshot and value are unchanged | The MCP item still points at the original snapshot `de8a0ce…` and the `mcp` value is unchanged | ✅ | Compared against baseline bdadac8 in a `git worktree`; behaviour matches, so not a regression |
| Skipping does not affect an existing install (added in review) | CLI | Install a skill, restrict it upstream, re-run `--skip-unsupported --force` | The existing component survives | `KEEP skills/reg-safe (skipped this run; unsupported upstream, not removed)`, component still present | ✅ | Before the fix this printed `REMOVE` and deleted the file (data loss); covered by `test_skip_unsupported_force_keeps_installed_component` |
| Genuinely removed components are still pruned (added in review) | CLI | Delete one skill upstream, restrict another, re-run `--skip-unsupported --force` | Only the genuinely removed one is deleted | `REMOVE skills/reg3-drop` deleted; `KEEP skills/reg3-keep` retained | ✅ | Confirms the fix did not disable `--force` |
| Failure list does not leak across runs (added in review) | Automated | Run one converting import, then one that fails early | The second run does not print the first run's paths | Output contains no `Manual migration list` | ✅ | Before the fix it printed stale paths; covered by `test_migration_log_not_stale_when_failure_precedes_build` |
| Daily configuration untouched | Throughout | All runs | `~/.config/opencode` is never written | Every run used `--config-dir` pointing at a temporary directory | ✅ | |

## E2E

- Applicability: not applicable. This project is a Python CLI with no front-end pages or
  back-end APIs. User-observable behaviour is entirely command output and destination
  contents, both covered by real runs above.
- Test basis: not applicable (no YouTrack issue; the requirement source is
  `plugin-import-session.md`).
- Markdown report: none
- PDF report: none
- Summary: all 20 matrix items pass (17 initial + 3 added after the code review fix)

## Failures and unverified items

None.

## Post-acceptance fix (from code review)

Live testing during the code review found a defect this report's initial matrix did not
cover: when an installed component is skipped during a later run, `--force` treats it as
"removed upstream" and deletes it (data loss). The initial matrix only covered a first
install, so it could not catch this. It has been fixed and covered by 3 additional
verifications (the last three rows above). After the fix, the full verification was re-run:
54 tests pass, `check_opencode.py` passes, and all 20 matrix items pass.

Additional note (not a defect): a partial update such as `--skills-only` creates a new
snapshot directory because the snapshot key includes `kinds`. This is pre-existing design
since bdadac8: old snapshots are retained and unselected components still point at the
original snapshot. Verified against a baseline worktree, so it is not reported as a failure.

## Requirement baseline differences

No YouTrack issue. The six iteration suggestions in `plugin-import-session.md` map to the
spec goals as follows:

| Source suggestion | Spec decision | Impact | Open question |
|---|---|---|---|
| `--skip-unsupported` / `--continue-on-error` | Implemented `--skip-unsupported` | Covered; `--continue-on-error` not added (similar semantics, less precise) | None |
| Automatic name correction | Implemented `--fix-names` | Covered; strict by default and must be opted in explicitly | None |
| Automatic model alias mapping | **Not implemented** | Keeps rejecting with a clear error message | Mapping `sonnet` → `anthropic/claude-sonnet-4` automatically would bind to a specific provider, which conflicts with the "never silently drop permission semantics" invariant. Suggested as a separate issue. |
| Manual migration list on failure | Implemented (`Manual migration list`) | Covered | None |
| Write MCP into opencode.jsonc and verify | Implemented as goal 5 | Covered | None |
| `--manual-mode` producing cp/mv commands | Implemented `--manual-mode` | Covered; emits `cp` commands (no `mv` needed) | None |
