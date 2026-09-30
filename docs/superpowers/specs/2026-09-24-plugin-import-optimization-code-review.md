# Code Review: Plugin Import Optimization

- Review scope: `bdadac8..bbbd54b` (5 feature commits plus 3 documentation commits)
- Main change: `skills/install-plugin/scripts/importer.py` (+146/-27),
  `tests/test_importer.py` (+96)
- Dimensions: Conventions / Architecture / Regression / Test / Performance

## Fix status

All three must-fix items were fixed on the same branch with regression tests added (see the
"✅ Fixed" markers below). Of the four suggested fixes, items 6 and 7 were adopted. Items 4
and 5 are structural preferences and were not changed, to avoid widening the diff while
fixing the data-loss defect. The remaining 💡 items were not implemented.

## 🚫 Must fix

### 1. ✅ Fixed — `--skip-unsupported` with `--force` deletes previously installed components (data loss)

`skills/install-plugin/scripts/importer.py:474-509`

A skipped component never enters `desired`, so the `selected` set in `make_plan()`
(importer.py:632) still contains the manifest-recorded old entry, which is treated as
"removed upstream" and removed under `--force`. Nothing was removed upstream; this run
simply could not convert it.

Reproduced (installed `skills/reg-safe`, then added `allowed-tools` upstream, re-ran):

```
$ importer.py <source> --skip-unsupported --force
Warning: Skipping skill safe: ...
REMOVE skills/reg-safe
$ ls dest/skills/          # empty, the component was deleted
```

Expected: skipping must not equal removal.

**Fix**: `build_payload()` takes a `skipped` parameter that collects the skipped exports;
`make_plan()` removes them from the selection (`selected -= skipped`), so skipping only
affects this run's additions and never an existing installation. Added
`test_skip_unsupported_force_keeps_installed_component` (which does fail when the fix is
reverted) and `test_skip_unsupported_sync_reports_skip_not_removal`. Also confirmed by hand
that a component genuinely removed upstream is still pruned, so the fix did not disable
`--force`.

### 2. ✅ Fixed — misleading message in sync mode

`skills/install-plugin/scripts/importer.py:640`

The same situation in default sync mode printed `KEEP skills/reg2-safe (removed upstream)`.
The component is still present upstream, so the message misled users into thinking the
source had deleted it.

**Fix**: a skipped component that is already installed is now reported as
`KEEP <export> (skipped this run; unsupported upstream, not removed)`.

### 3. ✅ Fixed — migration list leaked across runs

The original `MIGRATION_LOG` was module-level global state, cleared only at the start of
`build_payload()`. When a failure happened before `build_payload()` (for example
`Plugin not found`), `main()` still printed paths left over from a previous call. Live
testing showed `skills/leak-hello` being printed even though that source did not exist in
the second call.

**Fix**: the module-level global was removed in favour of a `migration_log` parameter owned
by the caller, with `main()` creating a fresh list per call. Added
`test_migration_log_not_stale_when_failure_precedes_build` (which does fail when the code is
restored to the original global design).

## ⚠️ Suggested fixes

### 4. `install()` already takes 11 parameters, none by keyword

`skills/install-plugin/scripts/importer.py:766-767`

`mode, preview, listing, ask, fix, skip, manual` are all positional, with a dense run of
boolean flags (three `True/False` in a row). `build_payload()` additionally receives `fix,
skip` positionally (importer.py:798), so inserting a parameter silently misaligns them.
Recommend passing `fix, skip` by keyword and possibly collapsing the booleans into a single
options object or named tuple.

**Not applied**: `build_payload()` already uses keywords for the new parameters, and a
larger refactor is out of scope for a data-loss fix.

### 5. Widening `make_plan()`'s return value affects its call site

`skills/install-plugin/scripts/importer.py:694`, `810`

The return value grew from a 2-tuple to a 3-tuple. There is only one call site in the
project and it was updated, so there is no real risk, but the function now carries four
responsibilities: planning, verifying the merged result, producing backup paths and
reporting. Consider extracting the MCP merge verification (importer.py:675-682) into its
own function so `make_plan()` keeps returning `(retained, changes)`. Not blocking; noted for
responsibility concentration.

### 6. ✅ Fixed — manual migration list wording was ambiguous

`skills/install-plugin/scripts/importer.py:868-876`

The list contains items that were converted successfully, but a user seeing `Import failed`
could think they had been installed.

**Fix**: the heading is now `Manual migration list (converted but not installed):`.

### 7. `--fix-names` normalization can collide; correctly blocked but the message is unclear

Live testing with both `GitLab` and `gitlab` present and different after conversion correctly
raised `Conflicting MCP definitions: gitlab`. The behaviour is right, but the message does
not indicate that `--fix-names` caused the collision.

**Not fixed**: the collision originates from two genuinely different definitions in the
source, and the message already names the conflicting key. Adding a `--fix-names` hint would
require threading the flag through `mcp_entries()`, which is unnecessary complexity;
evaluated and left as is.

## 💡 Optional improvements

### 8. `print_manual_script()` emits no paths for MCP items

`skills/install-plugin/scripts/importer.py:523-551`

MCP entries only produce a `# key` comment, so users still have to look up the source file
to know what to fill in. Consider also printing the source `.mcp.json` path for reference.

### 9. `normalize_name()` duplicates normalization already inline in `discover()`

`skills/install-plugin/scripts/importer.py:229` still embeds
`re.sub(r'[^a-z0-9]+', '-', ...)` — the same logic as the new `normalize_name()`
(importer.py:55) but without the 64-character truncation. It could simply call
`normalize_name()` to remove the duplication.

### 10. Variable naming in the walrus assignment

`skills/install-plugin/scripts/importer.py:868`

`im_migration` carries an `im_` prefix even though this is not a module reference, and the
name does not reflect "migration list" semantics. Suggest `pending_migrations`.

## Review dimensions in detail

### Conventions
- Naming follows snake_case verb/noun conventions; `normalize_name`,
  `print_manual_script` and `shell_quote` are semantically clear.
- `MIGRATION_LOG` correctly uses UPPER_SNAKE_CASE.
- This is a Python project, so most of the TypeScript and path-alias rules in the conventions
  document do not apply.
- No new dependencies were introduced, so technology selection carries no risk.
- The JSDoc and `TODO:` rules are satisfied by equivalent docstrings.

### Architecture
- All three new flags are opt-in and the strict default is unchanged, preserving the "never
  silently drop permission semantics" boundary. `check_owned()` deliberately does not
  receive `fix` (importer.py:556), so ownership validation stays strict — the right call.
- `print_manual_script()` and `make_plan()` are cleanly separated.
- No over-abstraction was introduced; `build_payload()` grew but stays maintainable.
- The module-level `MIGRATION_LOG` was the only cross-module shared state and is gone
  (item 3).

### Regression
- Behaviour without the new flags matches `bdadac8`; the 51 tests cover the original 41 and
  all pass.
- Partial-update snapshot behaviour was compared against a baseline worktree and confirmed
  not to be a regression.
- Items 1, 2 and 3 are real risks introduced by the new flags and must be fixed.
- Transaction boundaries are unchanged: `--manual-mode` returns before `install_lock()`, so
  it takes no lock and writes nothing; MCP merge verification happens before
  `apply_transaction()`, so a failure leaves the destination untouched.

### Test
- 10 new tests cover fix-names (success and default failure), skip-unsupported (skill, agent
  and MCP skipping plus default failure), the migration list, manual mode and merge JSON
  validity.
- Tests follow the existing `unittest` and `setUp` fixture conventions (`self.skill()`,
  `self.snapshot()`), and names describe behaviour, matching the project style.
- **Gap**: no test covers "a component installed earlier is removed by
  `--skip-unsupported --force`", which is the source of item 1. Two tests were added:
  - `test_skip_unsupported_force_keeps_installed_component`
  - `test_migration_log_not_stale_when_failure_precedes_build`
- No flakiness risk: tests do not depend on time or execution order, and temporary
  directories are cleaned up in `tearDown`.

### Performance
- `MIGRATION_LOG` only accumulates one string per component (O(n), n = component count), so
  the impact is negligible.
- `json.loads(encoded(updated_config))` is one extra serialization round trip, negligible at
  configuration-file scale, and buys assurance before writing.
- `print_manual_script()` uses `sorted(desired)`, O(n log n), with no nested loops.
- No database, network or concurrency concerns.
