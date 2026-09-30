# OpenCode Plugin Importer

Import **skills, Markdown agents and MCP configuration** from existing Claude Code,
Codex, agy or OpenCode repositories into OpenCode. No registry conversion is required.

Version **0.1.0** · macOS / Linux · Python **3.9+** · Git · MIT

This is a component importer, not a runtime emulator. Importing a skill does not make
its host-specific commands, hooks or setup workflow compatible with OpenCode.

## Quick start

```bash
git clone https://github.com/mmaoteacher/opencode-plugin-importer.git
cd opencode-plugin-importer
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r skills/install-plugin/scripts/requirements.txt

./skills/install-plugin/scripts/install-plugin.sh /path/to/plugin --list
./skills/install-plugin/scripts/install-plugin.sh /path/to/plugin --dry-run
./skills/install-plugin/scripts/install-plugin.sh /path/to/plugin
```

The shell entrypoint also works on macOS's bundled Bash; the implementation is Python.
Alternatively run `python skills/install-plugin/scripts/importer.py` directly.

To expose the bundled skill through a skill installer:

```bash
npx skills add mmaoteacher/opencode-plugin-importer --skill install-plugin -a opencode
```

The skill includes its scripts and dependency requirements. It explains how to use a
separate virtual environment; installing the skill alone does not install Python dependencies.

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
```

Default destination: `OPENCODE_CONFIG_DIR`, otherwise `$XDG_CONFIG_HOME/opencode`
(default `~/.config/opencode`). `--config-dir` takes precedence.
Preview/listing may clone Git into a temporary directory; **neither writes the destination**.
Embedded HTTPS credentials are rejected; use your existing Git credentials or SSH.

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
so a MCP-only update cannot silently modify installed skills. Old snapshots are retained;
there is no automatic garbage collection in this release.

## Conversion and failure behavior

- Local MCP: `command` + `args` → OpenCode `type: local`, command array.
- Remote MCP: HTTP/SSE URLs → `type: remote`; preserve supported headers/OAuth settings.
- `env` → `environment`; `${NAME}` → `{env:NAME}` in MCP values. Variable default expressions
  are unsupported. `${CLAUDE_PLUGIN_ROOT}`, `${CODEX_PLUGIN_ROOT}` and `${PLUGIN_ROOT}` point
  to the retained snapshot. Existing relative file arguments are resolved against that root.
- Agent tool lists become explicit permission allowlists; disallowed tools remain denied.
  `Write`, `Edit` and `MultiEdit` share OpenCode's `edit` permission. `model: inherit` uses the
  host default; other models must use `provider/model`, not Claude-specific aliases.
- Unsupported restriction mappings (such as skill `allowed-tools`, restrictive invocation
  flags or agent `permissionMode`) fail before installation. Nontranslated agent metadata
  produces warnings. Review source instructions for any other host-specific behavior.
- Strict mode is the default. `--fix-names` normalizes invalid names (an MCP server named
  `GitLab` is imported as `demo-gitlab`) and warns per rename; `--skip-unsupported` skips
  only the components OpenCode cannot represent, warns per skipped item, and installs the
  rest. Skipped items are not recorded as managed, so a later run retries them. A strict
  failure prints a manual migration list and writes nothing.
- `--manual-mode` prints a reviewable `sh` copy script without writing the destination. It
  copies original source files, so frontmatter conversion is not applied; MCP servers are
  listed as a comment to merge by hand.
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
