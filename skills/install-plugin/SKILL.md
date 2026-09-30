---
name: install-plugin
description: Import skills, Markdown agents, and MCP configuration from a local or remote Git plugin repository into OpenCode. Use for importing supported Claude Code, Codex, agy, or OpenCode components, listing them, and updating an existing importer-managed installation.
---

# Import a plugin into OpenCode

This skill includes `scripts/importer.py` and the compatible `scripts/install-plugin.sh`
entrypoint. Resolve paths from the directory containing this SKILL.md, not a hard-coded
user configuration path. Requires Python 3.9+, Git, and `scripts/requirements.txt`.

Use a Python environment with these dependencies. If needed, create a virtual environment
outside the imported skill snapshot (for example under the user's cache directory) and
install `scripts/requirements.txt` into it; do not modify a global Python installation.
Use that environment's Python for all commands below.

1. List the source before installing:
   `python "<skill-root>/scripts/importer.py" <repository-or-path> [ref] --list`.
   When there are multiple plugins, select the user's intended one with `--plugin <name>`.
2. Preview with `--dry-run`, preserving the selected ref/plugin and any component filters.
   A preview validates input but does not write the destination or ask interactive questions.
3. Execute without `--dry-run` to perform the requested import. Use `--config-dir <directory>`
   for a custom or test installation; default is `OPENCODE_CONFIG_DIR` or the XDG OpenCode
   configuration directory. Do not redirect to a different destination without the user's intent.
4. Report imported components and any unsupported features. Restart OpenCode to reload.
   If available, verify with `opencode debug skill`, `opencode debug agent <name>` and
   `opencode mcp list`; avoid claiming full workflow compatibility from file installation alone.

## Updates and conflicts

- Default sync adds/updates intact managed items and retains items removed upstream.
- `-i` prompts per change, including removal. Use only with an interactive terminal.
- `-f` also prunes intact managed items removed upstream. Use when the user requests pruning;
  it never takes over unmanaged files or overwrites locally modified imports.
- `--skills-only`, `--agents-only`, `--mcp-only` may be combined; unselected items stay on
  their previous source snapshot.
- Names use `<plugin>-<component>` (single hyphens) to match OpenCode skill naming rules.
  `--namespace` chooses a different valid prefix for a collision.

## Recovering from unsupported input

Default behavior is strict: any component OpenCode cannot represent aborts the run. When a
source contains a few unsupported pieces, offer these options and let the user choose:

- `--fix-names` normalizes invalid names to lowercase hyphenated form (for example an MCP
  server named `GitLab` becomes `demo-gitlab`) and reports every rename as a warning.
- `--skip-unsupported` skips only the components OpenCode cannot represent, warning per
  skipped item, and installs the rest. Skipped items are not recorded as managed, so a later
  run retries them.
- `--manual-mode` prints a reviewable `sh` copy script and writes nothing. Use it when the
  user wants to migrate by hand. The script copies original source files, so frontmatter
  conversion is not applied; MCP servers are listed as a comment to merge by hand.
- Without any of these options, a failure prints a manual migration list mapping each
  converted source path to its intended destination. Nothing is written on failure.

MCP servers are written into the `mcp` object of the existing `opencode.json` /
`opencode.jsonc`; the importer never creates a separate MCP JSON file in the destination.
The merged document is verified as loadable JSON before writing, and the installed server
names are printed so the user can confirm the merge.

If a conflict occurs, preserve the local changes and explain the conflicting path.
Legacy `.plugin-manifest.json` ownership is not automatically migrated; use an explicitly
chosen fresh destination or have the user back up and resolve the old installation.

## Boundaries

Supported components are skills, Markdown agents, and common local/remote MCP definitions.
Hooks, standalone commands, model aliases, restrictive skill invocation flags and agent
permissions with no supported mapping are not silently translated. Review warnings/errors
and narrow component filters only when that matches the user's request.

The importer retains source resources in versioned local snapshots so relative references
and plugin-root variables remain usable. It does not execute repository setup scripts,
install upstream dependencies, or make a host-specific setup workflow OpenCode-compatible.
Directory symlinks, external symlinks and broken symlinks are rejected; use an unconfigured
source checkout. Existing JSONC comments are normalized on MCP updates, with original
bytes saved in `.plugin-importer/backups/`.
