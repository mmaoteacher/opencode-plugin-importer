# Plugin Import 優化 實作計畫

- Spec：docs/superpowers/specs/2026-09-24-plugin-import-optimization-spec.md
- Branch：feature/plugin-import-optimization
- 執行方式：用 executing-plans skill，預設主 session 逐 task 執行

## Task 1：加入自動名稱修正（`--fix-names`）

- **估時**：`1h`
- **要動的檔案**：`skills/install-plugin/scripts/importer.py`、`tests/test_importer.py`
- **步驟**：
  1. 在 `importer.py` 新增 `normalize_name(value)`：把任意字串轉成合法名稱（`re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')`），若結果為空或超過 64 字元則截斷至 64 並去除尾端連字號，失敗時 `fail()`。
  2. 新增全域參數 `fix_names=False`，由 `valid_name` 的呼叫端傳入；`valid_name(value, fix=False)` 在名稱不合法時，若 `fix` 為真則改用 `normalize_name()` 並 `warn(f'Renamed {value!r} to {fixed!r}')`，否則維持現行 `fail()`。
  3. 修改 `discover()`（importer.py:217）、`entries()`（importer.py:244）、`mcp_entries()`（importer.py:277）、`build_payload()`（importer.py:458、473）四处名稱驗證，改為傳入 `fix_names`。
  4. `main()` 新增 `--fix-names`（`action='store_true'`，help：`Normalize lowercase invalid names instead of failing`），傳入 `install()` 與 `build_payload()` 鏈路。
  5. 保持 `valid_name()` 預設行為（不 fix）不變，以免影響 `check_owned()`（importer.py:529）對 manifest 所有權的嚴格驗證。
- **測試**：`tests/test_importer.py` 新增
  - `test_fix_names_normalizes_mcp_and_agent_names`：來源含 `GitLab` MCP 與 `My-Agent` skill，傳 `fix_names=True` 安裝成功，目的地出現 `mcp/demo-gitlab` 與 `skills/demo-my-agent`。
  - `test_fix_names_absent_still_fails`：同一來源不傳 `fix_names` 時 `im.install` 拋 `ValueError`，訊息含 `Invalid name`。
- **驗收方式**：執行 `.venv/bin/python -m unittest tests.test_importer.ImporterTests.test_fix_names_normalizes_mcp_and_agent_names tests.test_importer.ImporterTests.test_fix_names_absent_still_fails -v`，兩項 `OK`。
- **可平行**：否。後續 Task 依賴此名稱修正介面。

## Task 2：加入 `--skip-unsupported` 跳過不支援組件

- **估時**：`1h30m`
- **要動的檔案**：`skills/install-plugin/scripts/importer.py`、`tests/test_importer.py`
- **步驟**：
  1. 在 `build_payload()` 的 skills 迴圈（importer.py:457-470），當遇到 invocation/tool 限制（`disable-model-invocation`、`user-invocable: false`、`allowed-tools`）拋錯前，若 `skip_unsupported` 為真，改為 `warn(f'Skipping skill {name}: uses invocation/tool restrictions OpenCode cannot preserve.')` 並 `continue`。
  2. 在 `build_payload()` 的 agents 迴圈，將 `agent_convert(meta)` 包在 try/except `ImportErrorDetail`；`skip_unsupported` 為真時 `warn(f'Skipping agent {name}: {exc}')` 並 `continue`，否則照原樣拋出。
  3. 在 `mcp_entries()` 與 `mcp_convert()` 的失敗點，若 `skip_unsupported` 為真則略過該 server 條目並 `warn`，其餘條目繼續轉換。
  4. `main()` 新增 `--skip-unsupported`（`action='store_true'`，help：`Skip components OpenCode cannot represent instead of failing`），沿用 Task 1 的參數傳遞模式。
  5. 保持 `desired` 中不含被跳過項目，因此 `make_plan()` 對這些項目不產生變更，符合「分項更新不得變更未選元件資源快照」。
- **測試**：`tests/test_importer.py` 新增
  - `test_skip_unsupported_imports_remaining`：來源含一個正常 skill、一個帶 `allowed-tools` 的 skill、一個 `model: sonnet` 的 agent；`skip_unsupported=True` 安裝後只有正常 skill 與 agent 被匯入，`im.warn` 被 mock 且呼叫次數 ≥ 2。
  - `test_skip_unsupported_disabled_still_fails`：不傳 `skip_unsupported` 時拋 `ValueError`，訊息含 `invocation/tool restrictions` 或 `Model alias`。
- **驗收方式**：執行 `.venv/bin/python -m unittest tests.test_importer.ImporterTests.test_skip_unsupported_imports_remaining tests.test_importer.ImporterTests.test_skip_unsupported_disabled_still_fails -v`，兩項 `OK`。
- **可平行**：否。需 Task 1 的 `fix_names` 參數存在。

## Task 3：失敗時輸出手動遷移清單

- **估時**：`1h`
- **要動的檔案**：`skills/install-plugin/scripts/importer.py`、`tests/test_importer.py`
- **步驟**：
  1. 在 `importer.py` 新增全域清單 `MIGRATION_LOG = []`；`build_payload()` 中每個 `desired[f'{kind}/{name}']` 寫入時 append `(export, source_relative_path)`。
  2. `build_payload()` 開頭清空 `MIGRATION_LOG`，確保單次執行不累積。
  3. `main()` 的 `except` 區塊（importer.py:773-775）在印出 `Import failed: {exc}` 之後，若 `MIGRATION_LOG` 非空，逐項印出手動遷移建議：來源相對路徑 → 目的地 `~/.config/opencode` 相對路徑，並提示「手動複製後請自行合併 opencode.jsonc」。
  4. 保持失敗時不寫入任何目的地檔案（既有 `apply_transaction` 語意不變）。
- **測試**：`tests/test_importer.py` 新增
  - `test_failure_prints_manual_migration_list`：來源含一個正常 skill 與一個不支援 skill，不傳 `skip_unsupported`；斷言 `stderr` 捕獲（`contextlib.redirect_stderr`）含 `Manual migration list` 與該 skill 的來源路徑，且目的地未建立任何檔案。
- **驗收方式**：執行 `.venv/bin/python -m unittest tests.test_importer.ImporterTests.test_failure_prints_manual_migration_list -v`，`OK`。
- **可平行**：否。Task 3 會在 `build_payload()` 內新增 `MIGRATION_LOG` 寫入，與 Task 1、2 修改同一函式。

## Task 4：加入 `--manual-mode` 產出遷移腳本

- **估時**：`1h30m`
- **要動的檔案**：`skills/install-plugin/scripts/importer.py`、`tests/test_importer.py`
- **步驟**：
  1. `install()` 新增參數 `manual=False`；在 `install_lock()` 之前，若 `manual` 為真，直接從 `desired` 與 `MIGRATION_LOG` 產生 shell 腳本字串並 `print()`，然後 `return`，完全不呼叫 `state_read()`、`make_plan()` 或 `apply_transaction()`。
  2. 腳本內容：對每個 `skills/<name>` 產出 `mkdir -p "$DEST/skills/<name>"` + `cp -R "<source_path>/." "$DEST/skills/<name>/"`；對每個 `agents/<name>.md` 產出 `mkdir -p "$DEST/agent"` + `cp "<source_path>" "$DEST/agent/<name>.md"`；腳本開頭定義 `DEST="${1:-$HOME/.config/opencode}"`，結尾加註「MCP 設定請手動合併至 $DEST/opencode.jsonc 的 mcp 區塊」。
  3. `main()` 新增 `--manual-mode`（`action='store_true'`，help：`Print a copy script for manual migration without writing the destination`），與 `--dry-run`、`--list` 同樣不寫目的地。
  4. 將 `manual` 與 `Task 1` 的 `fix_names`、`Task 2` 的 `skip_unsupported` 一併納入參數鏈路。
- **測試**：`tests/test_importer.py` 新增
  - `test_manual_mode_prints_script_and_skips_writes`：傳 `manual=True`，斷言 stdout 含 `DEST=`、`cp -R`、skill 名稱與 agent 名稱，且 `self.dest` 不存在或為空。
  - `test_manual_mode_with_dry_run_flags`：同時傳 `manual=True, dry_run=True` 不拋錯，stdout 仍只含腳本不含 `Dry run:` 字樣（避免兩種模式語意混淆）。
- **驗收方式**：執行 `.venv/bin/python -m unittest tests.test_importer.ImporterTests.test_manual_mode_prints_script_and_skips_writes tests.test_importer.ImporterTests.test_manual_mode_with_dry_run_flags -v`，兩項 `OK`。
- **可平行**：否。整合 Task 1–3 的參數。

## Task 5：MCP 合併結果驗證與文件更新

- **估時**：`1h`
- **要動的檔案**：`skills/install-plugin/scripts/importer.py`、`tests/test_importer.py`、`docs/validation.md`、`skills/install-plugin/SKILL.md`
- **前置依賴**：Task 1、2、3、4 全部完成。
- **產出介面**：`--fix-names`、`--skip-unsupported`、`--manual-mode` 三個 CLI 選項與 `importer.MIGRATION_LOG` 全域清單。
- **步驟**：
  1. 在 `make_plan()` 寫入 `opencode.json` 前（importer.py:604-614），對 `updated_config` 執行 `config_read(root)` 相同路徑的 JSON 序列化驗證：`encoded(updated_config)` 必須可被 `json.loads` 解析，且 `updated_config['mcp']` 仍為 dict；否則 `fail('Merged MCP configuration is not valid OpenCode configuration.')`。
  2. 在 `install()` 成功訊息前，若 `'mcp' in kinds` 且 `updated_config` 有變更，額外印出 `MCP servers merged into <config_name>:` 與排序後的 server key 清單，讓使用者確認合併結果。
  3. 更新 `skills/install-plugin/SKILL.md`：新增 `--fix-names`、`--skip-unsupported`、`--manual-mode` 說明，並說明 MCP 寫入 `opencode.jsonc` 的 `mcp` 區塊（不產生獨立 `.json`）。
  4. 更新 `docs/validation.md` 的 Automated checks 段落，記錄新增的選項與對應測試。
- **測試**：`tests/test_importer.py` 新增
  - `test_mcp_merge_prints_server_names`：來源含一個 MCP server，安裝後 stdout 含 `MCP servers merged into` 與該 server 名稱。
  - `test_mcp_merge_result_is_valid_json`：安裝後 `json.loads((self.dest / 'opencode.json').read_text())['mcp']` 含該 server key。
- **驗收方式**：執行 `.venv/bin/python -m unittest discover -s tests -v`，全部測試 `OK`（既有 41 項 + 新增項皆通過）。
- **可平行**：否。整合所有 Task 的行為。

## 待辦事項

* [ ] `5h30m`: Plugin Import 優化
    * [ ] `1h`: Task 1 自動名稱修正
    * [ ] `1h30m`: Task 2 `--skip-unsupported`
    * [ ] `1h`: Task 3 手動遷移清單
    * [ ] `1h30m`: Task 4 `--manual-mode`
    * [ ] `1h`: Task 5 MCP 合併驗證與文件

### 預計總估時

`5h30m`
