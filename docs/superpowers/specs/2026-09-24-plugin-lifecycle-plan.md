# Plugin 生命週期管理 實作計畫

- Spec：docs/superpowers/specs/2026-09-24-plugin-lifecycle-spec.md
- Branch：feature/plugin-lifecycle
- 執行方式：用 executing-plans skill，預設主 session 逐 task 執行

## Task 1：新增 `--status` 唯讀查詢已安裝狀態

- **估時**：`1h`
- **要動的檔案**：`skills/install-plugin/scripts/importer.py`、`tests/test_importer.py`
- **步驟**：
  1. 在 `importer.py` 新增 `print_status(root)`，置於 `state_read()` 之後。邏輯：
     `root = Path(root).expanduser().resolve()`；`state = state_read(root)`；
     若 `state['plugins']` 為空則印 `No plugins installed.` 並 return；
     否則對每個 `(namespace, entry)` 以 `sorted(state['plugins'].items())` 處理。
  2. 對每個 namespace 印出：`PLUGIN <namespace>`（空行分隔）、`  source: <entry['source']>`、
     `  plugin: <entry['plugin']>`、`  ref: <entry['ref'] or '(unpinned)'>`、
     `  revision: <entry['revision'] or '(local working copy)'>`。
  3. 對每個 `sorted(entry['items'].items())` 印出
     `    <export> [<kind>] snapshot=<snapshot> present=<yes|no>`。
     `present` 判斷：kind 為 `mcp` 時用 `export[4:] in config.get('mcp', {})`（`config` 來自
     `config_read(root)`，`mcp` 不在 `entry` 中時需自行呼叫一次並容忍 `opencode.json`
     不存在）；否則用 `(root / export).is_symlink()`。
     避免在迴圈內重複呼叫 `config_read()`：在印出前呼叫一次並保存。
  4. `main()` 中將 `source` 從必填改為選填：`parser.add_argument('source', nargs='?')`。
     在 `main()` 開頭（`args = parser.parse_args(argv)` 之後）若 `args.source` 為 None：
     - 若 `args.status` 為真 → `print_status(args.config_dir)` 後 `return 0`；
     - 否則 `parser.error('source is required unless --status is given')`。
  5. `main()` 新增 `--status`（`action='store_true'`，help：
     `Show installed plugins, source and revision without a source argument`）。
  6. 確認 `print_status()` 全程不呼叫 `apply_transaction()`、不寫任何檔案。
- **測試**：`tests/test_importer.py` 新增
  - `test_status_lists_namespace_source_and_revision`：安裝後執行
    `im.main(['--config-dir', str(self.dest), '--status'])`，斷言 stdout 含
    `PLUGIN demo`、`source:`、`revision:`、`skills/demo-hello`。
  - `test_status_requires_no_source_and_writes_nothing`：`self.install()` 後以
    `before = self.snapshot()` 比對，`im.main(['--config-dir', str(self.dest), '--status'])`
    回傳 0 且 `self.snapshot() == before`。
  - `test_status_without_install_reports_empty`：`im.main(['--config-dir', str(self.dest), '--status'])`
    回傳 0 且 stdout 含 `No plugins installed.`。
  - `test_source_still_required_without_status`：`im.main(['--config-dir', str(self.dest)])`
    拋 `SystemExit`（argparse `parser.error`）。
- **驗收方式**：
  `.venv/bin/python -m unittest tests.test_importer.ImporterTests.test_status_lists_namespace_source_and_revision tests.test_importer.ImporterTests.test_status_requires_no_source_and_writes_nothing tests.test_importer.ImporterTests.test_status_without_install_reports_empty tests.test_importer.ImporterTests.test_source_still_required_without_status -v`
  四項全 `OK`。
- **可平行**：否。Task 3、4 的 `main()` 旗標定義需建立在 Task 1 的參數結構上。

## Task 2：新增 `--reset` 與 `--keep-local` 救援 snapshot 死鎖

- **估時**：`2h`
- **前置依賴**：Task 1（`main()` 參數結構）。
- **要動的檔案**：`skills/install-plugin/scripts/importer.py`、`tests/test_importer.py`
- **步驟**：
  1. 在 `importer.py` 新增 `snapshot_changes(root, old_items)`：走訪 manifest 中所有
     項目的 `snapshot` 路徑（去重），對每個存在的目錄計算 `tree_hash()` 並與該項
     `snapshot_hash` 比對。回傳 list of `(snapshot 相对路径, [被修改檔案的相对路径])`。
     檔案列舉需比對 snapshot 內實際檔案內容與 staging 不可得（來源可能已變），
     因此採用「以目錄 tree_hash 不符為準，再列出該目錄下所有相對檔案路徑」，
     並在標題說明為「可能包含僅 mtime 變動的檔案」。
  2. `check_owned()` 新增 `reset=False` 參數。在 `if not path.is_dir() or tree_hash(path) != old.get('snapshot_hash')`
     分支：若 `reset` 為真則不 `fail()`，改為將該 snapshot 標記為待重置（放入
     `reset_needed` 集合，由呼叫端傳入的 mutable set 收集）後繼續；
     否則維持現有 `fail()` 訊息。簽名改為
     `check_owned(root, export, old, config, checked, reset=False, reset_needed=None)`。
  3. `make_plan()` 新增 `reset=False`、`reset_needed=None` 參數，傳入 `check_owned()`。
     當 `reset_needed` 非空時，在回傳前印出：
     `Will discard local modifications in snapshot(s):` 與每個 snapshot 底下的檔案清單。
     此印出在 `preview` 下亦執行（dry-run 性質）。
  4. `install()` 新增 `reset=False`、`keep_local=False` 參數。當 `reset` 為真：
     - 呼叫 `snapshot_changes()` 取得差異；若有差異，印出上項的清單；
     - 若 `keep_local` 為真，寫出 diff：以 `difflib.unified_diff` 比較 snapshot 內每個
       檔案與 staging 對應檔案（僅針對文字檔，讀取失敗則跳過並註明），
       寫入 `tempfile.mkdtemp(prefix='opencode-importer-local-')` 下的
       `<namespace>-local.patch`，印出路徑。差異為空則印 `No local modifications to keep.`
     - 允許覆寫既有 snapshot：`install()` 中原本的
       `fail(f'Snapshot path is occupied by modified or unrelated content.')`
       在 `reset` 為真且 `tree_hash(snapshot_path) == old.get('snapshot_hash')`
       （即未修改，只是需要重寫）時允許替換；被修改者因 `check_owned` 已放行，
       直接以 `changes.insert(0, (str(snapshot), ('tree', staging)))` 覆寫。
  5. `main()` 新增 `--reset`（`action='store_true'`，help：
     `Discard local modifications inside managed snapshots and reinstall`）與
     `--keep-local`（`action='store_true'`，help：
     `With --reset, save local snapshot modifications as a patch before discarding`）。
     兩者放入既有 `mode` mutually exclusive group 以免與 `-i`／`-f` 併用。
  6. 確認 `keep_local` 未搭配 `reset` 時，argparse 直接拒絕（`parser.error`）。
- **測試**：`tests/test_importer.py` 新增
  - `test_reset_lists_then_discards_snapshot_modification`：安裝 → 修改
    `self.dest/.plugin-importer/sources/demo/<key>/skills/hello/SKILL.md`（key 由
    `im.state_read` 讀 manifest 取得）→ 不帶旗標重跑拋
    `Local snapshot modified or missing` → 帶 `reset=True` 重跑，斷言 stdout 含
    `Will discard local modifications`，且該檔案內容已還原為來源版本。
  - `test_reset_is_opt_in`：僅修改 snapshot 後重跑（不帶 `reset`）必須拋錯。
  - `test_keep_local_writes_patch`：帶 `reset=True, keep_local=True` 重跑，
    斷言 stdout 含 `.patch`，且該路徑存在、內容含 `MY LOCAL EDIT`。
- **驗收方式**：
  `.venv/bin/python -m unittest tests.test_importer.ImporterTests.test_reset_lists_then_discards_snapshot_modification tests.test_importer.ImporterTests.test_reset_is_opt_in tests.test_importer.ImporterTests.test_keep_local_writes_patch -v`
  三項全 `OK`。
- **可平行**：否。Task 3、4 需沿用 `check_owned()`／`make_plan()` 的新簽名。

## Task 3：新增 `--uninstall` 移除已安裝 plugin

- **估時**：`1h30m`
- **前置依賴**：Task 2（`check_owned()`／`make_plan()` 新簽名）。
- **要動的檔案**：`skills/install-plugin/scripts/importer.py`、`tests/test_importer.py`
- **步驟**：
  1. `main()` 新增 `--uninstall`（`action='store_true'`，help：
     `Remove a managed plugin and its MCP entries without touching unmanaged files`），
     放入 `mode` mutually exclusive group。
  2. `install()` 新增 `uninstall=False`。當 `uninstall` 為真時，於
     `state_read(root)` 之後直接執行移除流程，不呼叫 `build_payload()`
     （不需要重新轉換來源）：
     - `state = state_read(root)`；`entry = state['plugins'].get(namespace)`；
       若 `entry` 為 None 則 `fail(f'Plugin is not installed: {namespace}')`。
     - `kinds` 使用傳入值（預設全部 KINDS），使 `--uninstall --skills-only`
       僅移除 skill 項。
     - `retained, changes, merged = make_plan(root, state, namespace, {}, kinds,
     'uninstall', preview, ask, frozenset(), reset)`。
  3. `make_plan()` 支援 `mode='uninstall'`：因 `desired` 為空集，`selected` 只含
     manifest 既有項。移除 `mode == 'sync'` 的 KEEP 分支條件，改為
     `if item is None and mode == 'sync'`（保持不變），並讓
     `action = 'REMOVE'` 在 uninstall 模式下一律成立（既有邏輯已滿足，
     因 `item is None`）。`mode == 'interactive'` 仍可逐項確認。
  4. 遇本地修改時保留：`make_plan()` 呼叫 `check_owned()` 的環節在 uninstall 模式
     下同樣執行，因此 snapshot 被修改或 MCP 值遭改動時仍會 `fail()`，符合
     「拒絕並保留」決策。`--uninstall` 不搭配 `--reset` 時完全不放寬。
  5. 移除完成後自 manifest 刪除 namespace：`install()` 中當 `uninstall` 為真，
     將 `state['plugins'].pop(namespace, None)` 後寫入 `STATE`。
     需注意既有 `if not changes and retained == (old or {}).get('items', {})` 判斷：
     uninstall 時 `retained` 為 `{}` 而 `old['items']` 非空，故不會誤判為
     `No changes.`。
  6. 成功訊息改為 `Removed {namespace} from {root}.`（uninstall 時），
     其餘沿用 `Installed ...`。
- **測試**：`tests/test_importer.py` 新增
  - `test_uninstall_removes_links_mcp_and_manifest`：安裝含 skill、agent、MCP
    → `self.install(uninstall=True)` → 斷言 `skills/`、`agents/` 為空或不存在、
    `json.load(opencode.json)` 不含該 mcp key、manifest 的 `plugins` 為空 dict。
  - `test_uninstall_refuses_when_snapshot_modified`：修改 snapshot 內檔案後
    `self.install(uninstall=True)` 拋 `Local snapshot modified or missing`，
    並斷言 skill 連結仍存在（未被部分移除）。
  - `test_uninstall_leaves_unmanaged_files`：在 `self.dest/'skills'` 放一個
    非 manifest 管理的檔案，`uninstall=True` 後該檔案仍存在。
  - `test_uninstall_with_reset_removes_modified`：修改 snapshot 後
    `self.install(uninstall=True, reset=True)` 成功移除。
- **驗收方式**：
  `.venv/bin/python -m unittest tests.test_importer.ImporterTests.test_uninstall_removes_links_mcp_and_manifest tests.test_importer.ImporterTests.test_uninstall_refuses_when_snapshot_modified tests.test_importer.ImporterTests.test_uninstall_leaves_unmanaged_files tests.test_importer.ImporterTests.test_uninstall_with_reset_removes_modified -v`
  四項全 `OK`。
- **可平行**：否。與 Task 2 共用 `check_owned()` 簽名。

## Task 4：新增 `--prune-snapshots` 回收無用 snapshot

- **估時**：`1h`
- **前置依賴**：Task 2、Task 3。
- **要動的檔案**：`skills/install-plugin/scripts/importer.py`、`tests/test_importer.py`
- **步驟**：
  1. 在 `importer.py` 新增 `prune_snapshots(root, preview=False)`：
     - `state = state_read(root)`；`referenced = {v.get('snapshot') for entry in state['plugins'].values() for v in entry.get('items', {}).values()}`。
     - 對每個 namespace 目錄 `.plugin-importer/sources/<ns>/`（若存在且非 symlink，
       使用 `destination_path()` 取得安全路徑），列舉其子目錄；
       若子目錄名稱不在 `referenced` 中（`referenced` 存的是
       `.plugin-importer/sources/<ns>/<key>` 完整相對路徑，比較時以
       `f'.plugin-importer/sources/{namespace}/{child.name}'` 產生），
       印出 `PRUNE <path>` 並加入待刪除清單。
     - `preview` 為真時印 `Dry run: no snapshot removed.` 後 return。
     - 否則以 `shutil.rmtree()` 刪除，最後移除空的 namespace 目錄
       （僅在該目錄已空且非 symlink 時 `rmdir()`，失敗則忽略）。
     - 刪除前檢查每個目標 `is_symlink()` 為假，避免透過連結刪到目的地外。
  2. `main()` 新增 `--prune-snapshots`（`action='store_true'`，help：
     `Delete managed snapshots no longer referenced by any installed item`），
     不放入 mutually exclusive group（可與 `--dry-run` 併用）。
  3. `main()` 於 `args.source` 為 None 且 `--prune-snapshots` 未指定時，
     仍要求 `source`（維持 Task 1 的行為）。
  4. `--prune-snapshots` 需在 `args.source` 為 None 時也能執行：調整 Task 1 的
     無 source 分支順序為 `--status` → `--prune-snapshots` → `parser.error`。
  5. 確認 prune 不會刪除被任何項目引用的 snapshot：以 `retained` 與
     `state['plugins']` 為唯一真相來源。
- **測試**：`tests/test_importer.py` 新增
  - `test_prune_snapshots_removes_only_unreferenced`：連續三次不同內容安裝
    （每次 `self.skill('hello', body=...)` 改變來源）→ 確認 `sources/demo/` 下有 3 個
    目錄 → `im.prune_snapshots(self.dest)` → 確認僅剩 manifest 引用的 1 個。
  - `test_prune_snapshots_dry_run_keeps_everything`：同上，但
    `im.prune_snapshots(self.dest, preview=True)` 後目錄數不變。
  - `test_prune_then_rerun_reports_no_changes`：prune 後再次
    `self.install()` 必須印 `No changes.`（證明未誤刪使用中的 snapshot）。
- **驗收方式**：
  `.venv/bin/python -m unittest tests.test_importer.ImporterTests.test_prune_snapshots_removes_only_unreferenced tests.test_importer.ImporterTests.test_prune_snapshots_dry_run_keeps_everything tests.test_importer.ImporterTests.test_prune_then_rerun_reports_no_changes -v`
  三項全 `OK`。
- **可平行**：否。需 Task 3 的 manifest 移除語意已定案。

## Task 5：更新文件並驗證既有行為不退步

- **估時**：`1h`
- **前置依賴**：Task 1、2、3、4 全部完成。產出介面：
  `--status`、`--reset`、`--keep-local`、`--uninstall`、`--prune-snapshots`
  五個旗標；`check_owned(root, export, old, config, checked, reset=False, reset_needed=None)`、
  `make_plan(root, state, namespace, desired, kinds, mode, preview, ask, skipped, reset, reset_needed)`、
  `print_status(root)`、`snapshot_changes(root, old_items)`、`prune_snapshots(root, preview=False)`。
- **要動的檔案**：`README.md`、`skills/install-plugin/SKILL.md`、`docs/validation.md`
- **步驟**：
  1. `README.md` 新增「Lifecycle」小節，說明：
     重跑（`No changes.`）、更新、`--status` 查詢、`--uninstall` 解除安裝、
     `--prune-snapshots` 回收、`--reset` 救援本地修改。明確說明 `--reset` 會
     丟棄 snapshot 內本地修改，`--keep-local` 可先存成 patch。
  2. `README.md` 更新 snapshot 說明：舊說「no automatic garbage collection」改為
     說明 `--prune-snapshots` 為手動回收機制。
  3. `skills/install-plugin/SKILL.md` 更新流程步驟，加入更新與解除安裝情境，
     以及 snapshot 被本地修改時的處理指引。
  4. `docs/validation.md` 更新測試數量並列出本輪新增覆蓋項目。
  5. 執行完整驗證：`.venv/bin/python -m unittest discover -s tests`、
     `bash -n skills/install-plugin/scripts/install-plugin.sh`、
     `.venv/bin/python tests/check_opencode.py`（需 opencode CLI）。
  6. 依 spec 驗收計畫「實機驗收」第 8 項，用真實 CLI 走一次：首次安裝 → 重跑
     （應 `No changes.`）→ 改來源更新 → `--status` → `--uninstall`，
     全程以 `--config-dir` 指向暫存目錄，確認不影響 `~/.config/opencode`。
- **測試**：本 task 不新增測試，僅更新文件並做完整回歸驗證。
- **驗收方式**：
  `.venv/bin/python -m unittest discover -s tests` 顯示全部通過且數量 ≥ 既有 54 項；
  `bash -n skills/install-plugin/scripts/install-plugin.sh` 無輸出；
  `tests/check_opencode.py` 印出 `OpenCode discovered the imported skill and agent
  and connected to the synthetic MCP.`。
- **可平行**：否。整合全部旗標的文件說明。

## 待辦事項

* [ ] `6h30m`: Plugin 生命週期管理
    * [ ] `1h`: Task 1 `--status` 唯讀查詢
    * [ ] `2h`: Task 2 `--reset` 與 `--keep-local`
    * [ ] `1h30m`: Task 3 `--uninstall`
    * [ ] `1h`: Task 4 `--prune-snapshots`
    * [ ] `1h`: Task 5 文件與回歸驗證

### 預計總估時

`6h30m`
