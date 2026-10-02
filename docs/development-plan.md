# Optimization Development Log

## Completed (0.1.0)

- [x] Replaced Bash string parsing with a Python core, keeping the original .sh entrypoint.
- [x] Explicit installation directory; temporary fixtures avoid touching daily OpenCode
      settings.
- [x] `--list` / `--dry-run` write neither the destination nor the manifest; interactive
      preview asks nothing.
- [x] Validation before writing, same-directory staging, an install lock and catchable
      failure rollback.
- [x] Protect user modifications and unmanaged files; force only prunes intact managed items
      removed upstream within the selected kinds.
- [x] Root, legacy directories, custom manifest paths and multi-plugin selection.
- [x] Retain a snapshot of the whole source; partial updates leave unselected components on
      their previous resources.
- [x] local/remote MCP formats, env, command, args, root variables and common OAuth settings.
- [x] JSON/JSONC reading and configuration merging; keep a backup of the original bytes.
- [x] Common Markdown agent tools/permission mapping; restrictions that cannot be preserved
      are reported explicitly.
- [x] sync/interactive/force update semantics, source revision and content hash records.
- [x] MIT license, README compatibility matrix, skill usage guide and CI.
- [x] 41 tests passing plus real OpenCode discovery/MCP handshake.

See the [validation record](validation.md).

## Completed (0.2.0)

- [x] `--fix-names` normalizes invalid names and reports every rename.
- [x] `--skip-unsupported` skips only unconvertible components; a skipped component is never
      pruned, even under `--force`.
- [x] A manual migration list on failure, with no cross-run leakage.
- [x] `--manual-mode` emits a reviewable copy script without writing.
- [x] MCP servers merged into the `mcp` block of `opencode.json(c)`, verified before writing
      and reported afterwards.
- [x] `--status` lists installed plugins, source, revision and item presence read-only.
- [x] `--reset` / `--keep-local` escape the local-snapshot dead end and can save a patch
      first.
- [x] `--uninstall` removes a managed plugin, refusing on local modifications unless
      `--reset` is given, and keeps the record for kinds left behind by a filter.
- [x] `--prune-snapshots` reclaims unreferenced snapshots and refuses to guess when the
      manifest is damaged.
- [x] 76 tests passing plus real OpenCode discovery/MCP handshake.

## Completed (0.3.0)

- [x] Agent `color` is validated against the values OpenCode accepts (`#rrggbb` or one of eight
      semantic names), measured against the CLI rather than assumed. A Claude Code color name
      used to import cleanly and then stop OpenCode from loading every agent.
- [x] `--report <path>` writes every refused component as JSON: export, kind, offending key and
      value, source path, reason and repair candidates. Written on success and on failure.
- [x] Repair candidates are deterministic rather than guessed — a replacement value, dropping
      the key, or `ask` where no portable answer exists.
- [x] A strict run collects every refused component before aborting, so one report covers one
      decision per component. It still writes nothing.
- [x] `--manual-mode` comments the components it refused instead of omitting them, which
      previously left out exactly the parts needing hand migration.
- [x] The skill documents the repair loop, including that repairs apply to the source and not
      to the destination.
- [x] `docs/known-issues.md` records defects found during a real import, with two still open.
- [x] 88 tests passing.

## Explicitly deferred

- Automatic manifest migration from the original personal install script: the old records
  lack sufficient integrity/ownership data, so takeover is conservatively refused.
- A user-facing command for restoring a previous source snapshot version.
- hooks, standalone commands, Codex TOML agents and permission semantics with no equivalent
  mapping.
- External/directory symlinks, recursive remote marketplace downloads and source dependency
  installation.
- In-place JSONC comment editing: the original bytes are backed up and the output is
  normalized JSON.
- A recovery journal for multi-file transactions across sudden power loss / SIGKILL.
- A same-source installation benchmark against tools such as OpenPackage; only a
  documentation-based feature comparison exists so far.
- Automatic model alias mapping (for example `sonnet`): mapping to a concrete provider would
  bind the result to that provider, which conflicts with the invariant against silently
  dropping semantics. Tracked as a separate discussion.

These limitations must not be described as supported. Any future extension must define
behaviour and tests before changing format conversion.
