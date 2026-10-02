# Known issues

Defects observed while importing a real plugin into OpenCode. Each entry records what the user
sees, why the current behaviour produces it, and the smallest change that would remove it.
Nothing here is fixed yet unless the entry says so.

## 1. Agent `color` is passed through without validating its value

**Status** fixed on `fix/opencode-load-validation`

`agent_convert` keeps `color` among the frontmatter keys it preserves (the literal set in the
`result = {...}` comprehension) but never checks the value. Claude Code accepts CSS colour names,
so a source plugin may legitimately contain `color: orange`. OpenCode does not:

```
Configuration is invalid at ~/.config/opencode/agents/cosmo-committer.md
↳ Expected a string matching the RegExp ^#[0-9a-fA-F]{6}$, got "orange" color
↳ Expected "primary" | "secondary" | "accent" | "success" | "warning" | "error" | "info", got "orange" color
```

Measured against OpenCode: a `#rrggbb` hex string or exactly one of the eight semantic names is
accepted, comparison is case sensitive, and arbitrary colour names such as `orange` or `purple`
are rejected.

This is worse than a cosmetic mismatch. OpenCode validates every agent file eagerly, so one
invalid `color` makes the whole agent configuration fail to load, including agents that were
imported perfectly. In the observed import, all eight agents were unusable because two of them
carried a Claude Code colour name.

The fix validates `color` in `agent_convert`, so the failure happens at import time with the
usual "adapt it explicitly" wording and `--skip-unsupported` can skip the agent instead of
aborting the plugin.

## 2. A successful `--dry-run` does not mean OpenCode can load the result

`--dry-run` and `--list` report on what this importer converts. They never ask OpenCode whether
it accepts the output. Any field that passes through unvalidated — `color` before the fix above,
and any other frontmatter key OpenCode happens to tighten later — produces a green preview and a
broken OpenCode startup afterwards.

The `--dry-run` output reads as an install plan, so the gap is easy to miss, and the failure only
appears after restarting OpenCode.

Two things would narrow it: validating every preserved frontmatter field against the values
OpenCode documents, and stating plainly in the README that a preview is not a load test and that
`tests/check_opencode.py` is the check that actually starts OpenCode.

## 3. `--manual-mode` omits exactly the components that could not be converted

**Status** fixed on `fix/opencode-load-validation`

In `build_payload`, a component that is skipped under `--skip-unsupported` is `continue`d before
`migration_log.append(...)` runs, and `print_manual_script` iterates `desired`. The manual script
therefore contained only the components that converted cleanly — the incompatible ones were
missing.

That is the opposite of what "manual migration" suggests. A user who ran
`--skip-unsupported --manual-mode` to hand-finish the awkward parts got a script for the parts
that needed no work, and no pointer to the parts that did.

The script now comments each refused component with its source path, the reason and its repair
options, so the file is usable for the purpose its name implies. The candidates come from the
same data `--report` emits.

## 4. Agents are written to `agents/` while OpenCode also reads `agent/`

The importer creates `agents/<name>.md`. OpenCode loads agents from both `agents/` and `agent/`;
verified by moving an installed agent from one to the other and reading it back with
`opencode debug agent`.

So this is not a failure today, but it is an unexplained choice: documentation and most
existing setups use the singular `agent/`, and a user who greps their config for the directory
they were told about finds nothing. Either pick the singular form or state in the README why the
plural one is used.

## Observations, not defects

**No per-item compatibility policy.** Every incompatible component is treated identically: strict
mode aborts the whole plugin, `--skip-unsupported` drops all of them. There is no way to say
"repair this one and skip that one". This is a deliberate choice — fail rather than guess — but
it means a single unconvertible agent can block an otherwise usable plugin unless the user
reaches for `--skip-unsupported` and accepts losing components.

**MCP tool names are never mapped.** `TOOLS` covers only the fifteen Claude Code built-in tool
names. Any `mcp__<server>__<tool>` entry in an agent's `tools:` list fails with
`Unknown agent tool`, because the importer refuses to guess how a third-party server names its
tools. Content that referenced those tools has to be rewritten in the source, which is why the
imported cosmo skills carry `gitlab_*` and `youtrack_*` names in their prose.

**Skill and agent prose is not rewritten.** Only `${PLUGIN_ROOT}` and its aliases are expanded.
Tool names, slash-command syntax and host-specific workflows written in Markdown bodies survive
untouched and have to be corrected in the source plugin.