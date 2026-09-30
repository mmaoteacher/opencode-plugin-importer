# Plugin Import Optimization

- Source: plugin-import-session.md (`../../lawsnote/whitephoenix/`)
- Date: 2026-09-24
- Branch: feature/plugin-import-optimization

## Background and problem
install-plugin is too strict when converting the 4 supported sources: a single unsupported
feature (add-source-id, the agent alias `sonnet`, the MCP name `GitLab`) blocks the whole
installation. There is no way to skip, no automatic correction, no manual fallback, and no
verification of the merged MCP configuration.

## Goals
1. Allow skipping a single unsupported component (`--skip-unsupported`)
2. Automatically correct invalid MCP/agent names (lowercase, hyphens) and report each change
3. Provide `--manual-mode` to emit a migration script (cp/mv commands)
4. On failure, print a manual migration list (converted and skipped paths)
5. Write MCP configuration into `opencode.jsonc` automatically and verify the merge result

## Non-goals
Not a universal converter (4 sources only); do not touch `~/.config/opencode`; no reverse
export formats.

## Acceptance plan
- Static: the existing 41 tests keep passing; new tests cover the new options.
- Live: `--list` / `--dry-run` do not write the destination; `--manual-mode` only prints a
  script; `--skip-unsupported` completes a partial migration and leaves unselected
  components' snapshots unchanged.

## Risks
Never take over locally modified files; `--force` does not overwrite them; catchable write
failures must roll back (no crash-atomicity claim).
