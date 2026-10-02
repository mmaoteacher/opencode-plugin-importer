# Validation

Validated on 2026-09-21 using macOS, Python 3.9.6 and OpenCode 1.18.31.

## Automated checks

**79 unit/integration tests passed** with:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Coverage includes:

- Root and legacy source layouts, custom skill directories and multi-plugin selection.
- Git revision imports without modifying the original checkout; URL-derived names.
- JSONC, YAML, Codex TOML MCP configuration and duplicate definitions.
- Local/remote MCP conversion, environment/root variables, agent permission mapping.
- Initial installation, repeat runs, selected-component updates and all update modes.
- List/dry-run without destination writes or manifest changes.
- Unmanaged-file collisions, edited snapshots/MCP, source ownership and legacy manifests.
- External/nested symlink rejection and rebased internal file links.
- Simulated write failures after partial installation, restoring the original destination.
- Original JSONC backups and exclusion of development dependency directories.
- `--fix-names` renaming invalid skill and MCP names, and strict failure without it.
- `--skip-unsupported` skipping restricted skills, aliased agents and invalid MCP entries
  while keeping the convertible ones, and strict failure without it.
- The manual migration list printed on failure, with no destination files created.
- Components skipped by `--skip-unsupported` are not pruned from an existing installation,
  including under `--force`, while genuinely upstream-removed components still are.
- The manual migration list is not carried over from a previous run when a run fails
  before any component is converted.
- Agent `color` values: a `#rrggbb` hex or one of the eight semantic names is imported, a CSS
  color name such as `orange` fails before installation, and `--skip-unsupported` skips that
  agent while installing the rest. The accepted set was measured against OpenCode rather than
  assumed; see [known issues](known-issues.md).
- `--manual-mode` printing a copy script for skills, agents and MCP without writing.
- The merged MCP document being valid JSON and the installed server names being reported.
- `--status` reporting installed namespaces, source, revision and item presence without a
  source argument and without writing anything.
- `--reset` listing then discarding local snapshot modifications, staying opt-in, and
  leaving a later plain import reporting `No changes.`
- `--keep-local` writing a unified diff containing the user's edits before discarding them.
- `--uninstall` removing symlinks, MCP entries and the manifest record while leaving
  unmanaged files, refusing on local modifications unless `--reset` is given, and working
  without a source argument.
- `--prune-snapshots` removing only unreferenced snapshots, honouring dry run, and leaving
  a later import reporting `No changes.`
- `--prune-snapshots` refusing to delete anything when a manifest snapshot record is
  malformed, leaving the live snapshot and its symlink intact.
- Filtered `--uninstall` keeping the namespace record for the remaining kinds so a later
  full uninstall can still remove them.

## Actual OpenCode check

```bash
.venv/bin/python tests/check_opencode.py
```

Passed: OpenCode discovered the imported skill, resolved the imported agent and connected
to a synthetic stdio MCP server. This used temporary XDG and OpenCode configuration directories;
no model request or source setup script was executed. The temporary environment was removed.

## Existing repository discovery

Read-only scans recognized:

- `mmaoteacher/open-design-plugin`: root manifests and setup skill.
- This repository: the bundled install-plugin skill.
- `vercel-labs/agent-skills` over HTTPS: nine skills at the time of validation.

These checks establish discovery only. They do not establish OpenCode compatibility of
host-specific setup workflows or every upstream skill. No upstream content is included in this repo.
Related-tool comparisons in README are based on those projects' documentation, not a
head-to-head installation benchmark.

## CI and limits

GitHub Actions runs the automated suite on macOS and Linux with Python 3.9 and 3.12.
The optional OpenCode smoke test is separate because it requires the OpenCode binary.
Local checks do not prove that every source repository, remote authentication method or
OpenCode version is supported. See README for unsupported mappings and transaction limits.
