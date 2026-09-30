# Development Guide

## Scope

This tool imports skills, Markdown agents and MCP configuration from existing Claude Code,
Codex, agy and OpenCode repositories into OpenCode. Do not grow it into a package manager
for every agent, and do not modify the neighbouring open-design-plugin project.

## Invariants

- Develop against this checkout. Never use the user's daily ~/.config/opencode for testing.
- `--list` and `--dry-run` must not write the destination, and a preview must never require
  interactive input.
- Updates and removals only touch components that the manifest owns and that are not locally
  modified. `force` must not take over or overwrite local modifications.
- A partial update must not change the resource snapshot of unselected components; relative
  `scripts` / `references` / `assets` must be preserved.
- Never silently drop permission semantics that have no equivalent; the supported range and
  its limits must be documented.
- Catchable write failures must roll back; do not claim crash-atomicity across multiple
  files.
- Do not commit personal configuration, credentials, installation records, third-party
  plugin source content or local dependency environments.

## Verification

Python 3.9+, dependencies in skills/install-plugin/scripts/requirements.txt.

```bash
python -m unittest discover -s tests -v
bash -n skills/install-plugin/scripts/install-plugin.sh
python tests/check_opencode.py  # isolated discovery and MCP handshake when the OpenCode CLI is present
```

When changing a supported format, update the fixtures, the README and docs/validation.md.
Tests should assert user-observable behaviour, especially preview, source detection,
conversion, re-runs, partial updates, conflicts, failure recovery and removal scope.
