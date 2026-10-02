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

## Inspecting, updating and removing

Re-running the same source is idempotent. Use these when the user asks about existing
installs rather than adding new ones:

- `--status` (no `source` needed) lists each installed namespace with its source, plugin,
  ref, revision and every managed item, including whether it is still present. Use it to
  answer "what is installed?" and to spot a namespace whose source has moved.
- Updating is simply re-running the same source and ref; the importer reports
  `ADD`/`UPDATE`/`KEEP` per component. A Git source records the new `revision`.
- `--uninstall` (no `source` needed) removes a managed plugin's symlinks and its MCP
  entries, and drops it from the manifest. It refuses and keeps everything when a component
  was locally modified; tell the user to decide on `--reset` rather than reaching for it.
  Add `--namespace`/`--plugin` when several plugins are installed. With a component filter
  (`--skills-only` and friends) only the selected kinds go; the manifest record is kept for
  the rest so a later `--uninstall` can finish, and the output lists what is still managed.
- `--prune-snapshots` (no `source` needed) deletes snapshots no installed item references.
  Snapshots accumulate across updates, so offer this after repeated updates. `--dry-run`
  works with it. If the manifest's snapshot record is damaged it stops with
  `Invalid snapshot ownership record` and deletes nothing; report that rather than
  suggesting `--reset`, which does not apply.

If an import stops with `Local snapshot modified or missing`, the user edited a file inside
a managed snapshot. The importer will not overwrite it. Report the affected snapshot and
offer `--reset` (which lists the files it will discard first) or `--reset --keep-local`
(which also writes a unified diff to a temporary path). Never pass `--reset` on the user's
behalf without an explicit decision.

## Recovering from unsupported input

Default behavior is strict: any component OpenCode cannot represent aborts the run. When a
source contains a few unsupported pieces, offer these options and let the user choose:

- `--fix-names` normalizes invalid names to lowercase hyphenated form (for example an MCP
  server named `GitLab` becomes `demo-gitlab`) and reports every rename as a warning.
- `--skip-unsupported` skips only the components OpenCode cannot represent, warning per
  skipped item, and installs the rest. Skipped items are not recorded as managed, so a later
  run retries them. A component skipped by one run is **not** removed even under `--force`;
  report it as kept-but-unsupported so the user knows it is still installed but stale.
- `--report <path>` writes a JSON report of every refused component, including repair
  candidates. It is written on success and on failure, so it also lists what a
  `--skip-unsupported` run left out. Use it before choosing between the options above.
- `--manual-mode` prints a reviewable `sh` copy script and writes nothing. Use it when the
  user wants to migrate by hand. The script copies original source files, so frontmatter
  conversion is not applied; MCP servers are listed as a comment to merge by hand, and every
  component that could not be converted is listed as a comment with its repair options rather
  than being silently absent.
- Without any of these options, a failure prints a manual migration list mapping each
  converted source path to its intended destination. Nothing is written on failure.

## Offering the user a repair choice

Do not resolve an unconvertible component on the user's behalf, and never edit the destination
to work around a refusal: installed components are symlinks into an importer-managed snapshot,
so hand edits there make every later run stop with `Local snapshot modified or missing`.

1. Re-run the refused import with `--report <path>` and read the report.
2. For each entry in `issues`, present the user with the component, the offending key and
   value, the reason, and the candidates from `repairs`. Each repair is one of:
   - `set` — the source frontmatter key takes the given value;
   - `drop` — remove that key from the source frontmatter;
   - `ask` — there is no portable replacement; ask the user for a value.
   Use the host's question tool with one option per repair, label the `ask` entry so the user
   can type their own value, and state which file will change before applying anything.
3. Apply the chosen repairs to `source_path` in the source repository, not to the destination.
   Keep every unrelated field untouched.
4. Re-run the same import. A repaired component installs normally and disappears from the
   report; anything still listed is still unresolved, so report it rather than retrying
   unchanged. One component can hide further problems: conversion stops at the first
   unconvertible field, so re-run after each fix and expect the next one to appear.
5. Verify with `opencode debug skill` and `opencode debug agent <name>`. A clean preview is not
   a load test: OpenCode validates fields the importer passes through, such as agent `color`.

Where a repair needs knowledge the importer does not have, say so instead of guessing. A third
party MCP server decides its own tool names, so mapping `mcp__<server>__<tool>` needs the
installed server's real tool list, and turning a model alias into `provider/model` needs a
provider the importer cannot see. Offer to inspect the destination's MCP configuration, or ask,
and treat the answer as the repair value.

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
