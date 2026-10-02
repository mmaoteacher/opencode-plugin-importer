# OpenCode Plugin Importer

Import **skills, Markdown agents and MCP configuration** from existing Claude Code,
Codex, agy or OpenCode repositories into OpenCode. No registry conversion is required.

Version **0.3.0** · macOS / Linux · Python **3.9+** · Git · MIT

This is a component importer, not a runtime emulator. Importing a skill does not make
its host-specific commands, hooks or setup workflow compatible with OpenCode.

## Quick start

Install the skill, then set up a Python environment for it. The skill ships its scripts
and `requirements.txt`, but **it cannot install Python dependencies for you** — that step
is required before the first run.

```bash
# 1. Install the skill (copies SKILL.md and scripts/ into ~/.agents/skills/install-plugin)
npx skills add mmaoteacher/opencode-plugin-importer --skill install-plugin -a opencode

# 2. Create an environment for its dependencies. Keep it outside the skill directory so
#    it is not mistaken for skill content, and do not modify a global Python install.
python3 -m venv ~/cache/plugin-env
source ~/cache/plugin-env/bin/activate
python -m pip install -r ~/.agents/skills/install-plugin/scripts/requirements.txt

# 3. Preview, then import. Both previews are read-only and never write the destination.
SCRIPT=~/.agents/skills/install-plugin/scripts/importer.py
python "$SCRIPT" /path/to/plugin --list
python "$SCRIPT" /path/to/plugin --dry-run
python "$SCRIPT" /path/to/plugin
```

Skipping step 2 fails fast with a clear message rather than a traceback:

```
Missing PyYAML. Install scripts/requirements.txt in a Python virtual environment first.
```

Only `PyYAML` (and `tomli` on Python 3.10 and earlier) is required. Activate the
environment in each new shell, or call its interpreter by absolute path.

If a source contains features OpenCode cannot represent, a strict run stops with an error
listing every convertible path. See
[Conversion and failure behavior](#conversion-and-failure-behavior) for `--fix-names`,
`--skip-unsupported` and `--manual-mode`.

### Working from a clone

To read or modify the importer itself:

```bash
git clone https://github.com/mmaoteacher/opencode-plugin-importer.git
cd opencode-plugin-importer
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r skills/install-plugin/scripts/requirements.txt

./skills/install-plugin/scripts/install-plugin.sh /path/to/plugin --list
```

The shell entrypoint also works on macOS's bundled Bash; the implementation is Python.
Alternatively run `python skills/install-plugin/scripts/importer.py` directly.

## Sources and selection

```bash
# SSH / HTTPS Git source; optional branch, tag or commit SHA
./skills/install-plugin/scripts/install-plugin.sh git@github.com:owner/repo.git main
./skills/install-plugin/scripts/install-plugin.sh https://github.com/owner/repo.git v1.0.0

# Local working copy (includes current edits); a supplied ref uses an isolated clone
./skills/install-plugin/scripts/install-plugin.sh /path/to/repo
./skills/install-plugin/scripts/install-plugin.sh /path/to/repo <commit-sha>

# A repository containing several plugins requires an explicit selection
./skills/install-plugin/scripts/install-plugin.sh /path/to/marketplace --list
./skills/install-plugin/scripts/install-plugin.sh /path/to/marketplace --plugin my-plugin

# Use a different destination/prefix or select component types
./skills/install-plugin/scripts/install-plugin.sh /path/to/plugin --config-dir /tmp/opencode-preview --dry-run
./skills/install-plugin/scripts/install-plugin.sh /path/to/plugin --namespace my-team --skills-only --agents-only

# Machine-readable list of what could not be converted, with repair options
./skills/install-plugin/scripts/install-plugin.sh /path/to/plugin --report /tmp/import-report.json
```

Default destination: `OPENCODE_CONFIG_DIR`, otherwise `$XDG_CONFIG_HOME/opencode`
(default `~/.config/opencode`). `--config-dir` takes precedence.
Preview/listing may clone Git into a temporary directory; **neither writes the destination**.
Embedded HTTPS credentials are rejected; use your existing Git credentials or SSH.

`--report <path>` records every component refused as unsupported: the offending key and value,
the reason, and the repairs the importer could determine — set a key to a given value, drop it,
or `ask` when no portable answer exists. It is written on success and on failure, so it also
shows what a `--skip-unsupported` run left out. Repairs are applied to the **source**, never to
the destination, and the import is then re-run. A strict run collects every refused component
before aborting, so one report covers one decision per component; within a single component
conversion still stops at the first unconvertible field, so re-run after each fix. The importer
never guesses where guessing would be wrong: an MCP tool name depends on the installed server,
and a model alias needs a provider it cannot see, so those surface as `ask`.

### Source support

| Source | Discovery |
| --- | --- |
| Claude Code | `.claude-plugin/plugin.json`, root `skills/`, `agents/`, `.mcp.json`; legacy `.claude/` directories |
| Codex | `.codex-plugin/plugin.json`, root components; `.codex/skills/`, Markdown agents and `.codex/config.toml` MCP tables |
| agy | root `plugin.json`, `skills/`, `agents/`, `mcp_config.json`; `plugins/*` bundles |
| OpenCode | root or `.opencode/` skills/agents, `opencode.json` / `opencode.jsonc` MCP entries |
| Shared skills | `.agents/skills/` |
| Multi-plugin repositories | `plugins/*` and local entries in Claude/Codex marketplace files |

Manifest custom `skills`/`agents` paths and inline/file `mcpServers` are supported within
the plugin root. Remote marketplace entries are reported, not recursively downloaded.
Codex TOML-native agents, hooks, standalone slash commands and app integrations are not imported.

## Names, resources and updates

Names use **`<plugin>-<component>`**, for example `demo-reviewer`. Single hyphens follow
OpenCode's skill name rules. Names must be lowercase and at most 64 characters.
Collisions fail; use `--namespace` instead of overwriting an existing installation.

The importer stores versioned source snapshots under `.plugin-importer/sources/`, with
skills/agents exposed through symlinks. This keeps relative scripts, references and assets
available. Plugin-root tokens are expanded in the imported Markdown and MCP configuration.
Development directories `.git`, `.venv`, `node_modules` and `__pycache__` are excluded.
It does not execute source setup scripts or install source dependencies.

| Mode | Added/changed items | Removed upstream |
| --- | --- | --- |
| Default sync | Update intact managed items | Retain |
| `-i` / `--interactive` | Ask per change | Ask before removal |
| `-f` / `--force` | Update intact managed items | Prune intact managed items |

**Every mode protects unmanaged files and local modifications**, including modified MCP
entries and snapshots. Back up and resolve conflicts explicitly. `--force` means pruning,
not permission to overwrite user changes. Interactive preview never asks questions.

Component filters may be combined. Unselected components retain their previous snapshots,
so a MCP-only update cannot silently modify installed skills. Superseded snapshots are
retained until you run `--prune-snapshots`; there is no automatic garbage collection.

## Lifecycle

Re-running the same source is idempotent (`No changes.` when nothing moved). To inspect,
update, remove and reclaim:

```bash
# What is installed, from which source and revision, and is each item still present?
./skills/install-plugin/scripts/install-plugin.sh --status

# Update: re-run the same source/ref. Snapshots are content-addressed per run.
./skills/install-plugin/scripts/install-plugin.sh <source>

# Remove a managed plugin, its symlinks and its MCP entries (no source needed).
./skills/install-plugin/scripts/install-plugin.sh --uninstall
./skills/install-plugin/scripts/install-plugin.sh --uninstall --namespace my-team

# Reclaim snapshots no installed item references any more.
./skills/install-plugin/scripts/install-plugin.sh --prune-snapshots
```

`--status` and `--prune-snapshots` are read-only or destination-only, so they do not need a
`source` argument. `--uninstall` refuses when a component was locally modified and keeps
everything; add `--reset` only after you have decided those local changes may be discarded.

`--uninstall` accepts the component filters. A filtered uninstall removes only the selected
kinds and keeps the manifest record for the rest, so a later `--uninstall` can finish the
job; it reports what is still managed. `--prune-snapshots` validates every snapshot path in
the manifest first and stops on a malformed record rather than guessing which resource is
still in use.

### Recovering from local snapshot edits

Installed resources are symlinks into `.plugin-importer/sources/`. Editing a file inside
that snapshot makes the manifest hash disagree, and every later import stops with
`Local snapshot modified or missing` — by design, so importer-managed content is never
silently overwritten. Recover explicitly:

```bash
# Lists the files that will be discarded, then reinstalls from the source.
./skills/install-plugin/scripts/install-plugin.sh <source> --reset

# Same, but saves a unified diff of your local edits first and prints its path.
./skills/install-plugin/scripts/install-plugin.sh <source> --reset --keep-local
```

The discard list is conservative: it reports every file in a mismatching snapshot, which
can include files that only changed mtime or mode. `--keep-local` writes the patch to a
temporary directory and prints the path; review it before deleting anything.

## Conversion and failure behavior

- Local MCP: `command` + `args` → OpenCode `type: local`, command array.
- Remote MCP: HTTP/SSE URLs → `type: remote`; preserve supported headers/OAuth settings.
- `env` → `environment`; `${NAME}` → `{env:NAME}` in MCP values. Variable default expressions
  are unsupported. `${CLAUDE_PLUGIN_ROOT}`, `${CODEX_PLUGIN_ROOT}` and `${PLUGIN_ROOT}` point
  to the retained snapshot. Existing relative file arguments are resolved against that root.
- Agent tool lists become explicit permission allowlists; disallowed tools remain denied.
  `Write`, `Edit` and `MultiEdit` share OpenCode's `edit` permission. `model: inherit` uses the
  host default; other models must use `provider/model`, not Claude-specific aliases.
- Agent `color` must be a `#rrggbb` hex value or one of `primary`, `secondary`, `accent`,
  `success`, `warning`, `error`, `info`. CSS color names such as `orange` are rejected, because
  OpenCode refuses to load an agent whose color it does not accept — and it validates every agent
  file before loading any of them, so one bad value disables them all.
- Unsupported restriction mappings (such as skill `allowed-tools`, restrictive invocation
  flags or agent `permissionMode`) fail before installation. Nontranslated agent metadata
  produces warnings. Review source instructions for any other host-specific behavior.
- Strict mode is the default. `--fix-names` normalizes invalid names (an MCP server named
  `GitLab` is imported as `demo-gitlab`) and warns per rename; `--skip-unsupported` skips
  only the components OpenCode cannot represent, warns per skipped item, and installs the
  rest. Skipped items are not recorded as managed, so a later run retries them. A component
  skipped by one run is **not** removed even under `--force`; it is reported as
  `KEEP <item> (skipped this run; unsupported upstream, not removed)`. Only components
  actually removed upstream are pruned. A strict failure prints a manual migration list
  and writes nothing.
- `--manual-mode` prints a reviewable `sh` copy script without writing the destination. It
  copies original source files, so frontmatter conversion is not applied; MCP servers are
  listed as a comment to merge by hand. Components that could not be converted appear as
  comments naming the source path, the reason and the repair options, rather than being
  missing from the script.
- JSON and JSONC are accepted. MCP servers are merged into the `mcp` object of the existing
  `opencode.json` / `opencode.jsonc`; no separate MCP JSON file is created in the
  destination. Updates preserve unrelated configuration values, but normalize
  formatting/comments. The merged document is verified as loadable JSON before writing and
  the installed server names are printed. Original configuration bytes are saved with mode
  `0600` in `.plugin-importer/backups/`. Having both `opencode.json` and `opencode.jsonc` is
  ambiguous and causes an error.
- Inputs and conflicts are checked before writes. Files are staged, then replaced under a
  per-destination lock. Catchable write errors and KeyboardInterrupt roll back completed
  replacements. Abrupt process termination, power failure and external concurrent edits
  are **not** guaranteed to be recoverable transactions.
- Directory symlinks, external/broken symlinks and special files in source payloads are
  rejected. Internal file symlinks are retained and rebased.

The importer tracks ownership, source revision and content hashes in
`.plugin-importer/manifest.json`. It does **not** adopt the old personal script's
`.plugin-manifest.json`: use an explicitly chosen fresh destination and reconcile/back up
an existing installation before switching. Your normal OpenCode configuration is not
migrated automatically.

## Verification

```bash
python -m unittest discover -s tests -v
bash -n skills/install-plugin/scripts/install-plugin.sh

# Optional: requires OpenCode on PATH; isolated config and synthetic MCP
python tests/check_opencode.py
```

The OpenCode check discovers an imported skill and agent and performs a MCP handshake,
without model requests. See [validation results](docs/validation.md) and
[development notes](docs/development-plan.md).

`--list` and `--dry-run` report on what this importer converts; they do not ask OpenCode whether
it accepts the result. A preview that completes cleanly is not a load test. `tests/check_opencode.py`
is the check that starts OpenCode against a real install. Known gaps are tracked in
[docs/known-issues.md](docs/known-issues.md).

## Related projects

[Vercel skills](https://github.com/vercel-labs/skills) manages skills across agents;
[OpenPackage](https://github.com/enulus/OpenPackage) covers broader cross-agent packaging;
[opencode-claude-bridge](https://github.com/sjawhar/opencode-claude-bridge) bridges Claude
components through an OpenCode plugin. This project focuses on explicit Git-to-OpenCode
imports, destination previews and ownership-protected updates. It is independent of these
projects and does not claim unique capabilities or complete cross-host compatibility.

Format references: [OpenCode skills](https://opencode.ai/docs/skills/),
[agents](https://opencode.ai/docs/agents/), [MCP](https://opencode.ai/docs/mcp-servers/).

## License

MIT. Originated from the maintainer's personal OpenCode installer; the shell implementation
was replaced with a tested Python core. Third-party plugin content is not distributed here.
