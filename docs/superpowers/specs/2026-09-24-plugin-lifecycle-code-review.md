# Code Review：plugin 生命週期管理

- 審查範圍：`main..7662337`（第二輪，涵蓋第一輪全部變更）
- 主要變更：`skills/install-plugin/scripts/importer.py`（+392/-39，現 1108 行）、`tests/test_importer.py`（+314）
- 審查維度：Conventions / Architecture / Regression / Test / Performance
- 驗收狀態：74 測試通過，`check_opencode.py` 通過，26 項功能矩陣通過

## 修正狀態

兩項必須修正已於同一 branch 修正並補回歸測試（詳見各節「✅ 已修正」）。建議項 3、4、5
一併採納。第 6 項為文件補充，已於 README 說明。第 7、9 項屬結構性偏好，未於本次變更。

## 🚫 必須修正

### 1. ✅ 已修正 — `--prune-snapshots` 依損毀的 manifest 刪除使用中的 snapshot（資料遺失）

`skills/install-plugin/scripts/importer.py:626-651`

`prune_snapshots()` 以 manifest 的 `snapshot` 值為「仍被引用」的唯一真相來源，但
`state_read()`（importer.py:674-685）只驗證 `version` 與 `plugins` 為 dict，**不驗證
`snapshot` 欄位格式**。格式驗證只存在於 `check_owned()`（importer.py:735），而 prune 不經過它。

實測：把 manifest 的 `snapshot` 竄改為 `"BOGUS"` 後執行 prune：

```
PRUNE .plugin-importer/sources/rv/76c9a3f92ea618318c74988c
Removed 1 unreferenced snapshot(s).
$ ls dest/skills/     → rv3-a.md 變成 dangling symlink
$ ls dest/.plugin-importer/sources/rv/  → No such file or directory
```

spec 的「風險與未決事項」已明確要求「若 manifest 損毀，應停止而非猜測」，目前未做到。
任何 manifest 欄位損毀（手改、disk 損壞、異常中斷）都會導致**刪除正在使用的資源**。

**建議**：prune 前逐項驗證 snapshot 記錄，格式非法即 `fail()` 而非猜測。可重用
`check_owned()` 的前綴檢查，或抽出 `validate_snapshot_record(snapshot)` 供兩處共用。

**修正**：抽出 `validate_snapshot_record(root, snapshot)`，同時驗證前綴、`..` 路徑與
symlink；`prune_snapshots()` 逐項呼叫，`check_owned()` 改為共用同一函式。已補
`test_prune_refuses_when_snapshot_record_malformed`（還原修正後確實失敗），並確認
damaged manifest 下 live snapshot 與 symlink 皆保留。prune 呼叫亦移入 `main()` 的
例外處理，改以清楚的 `Import failed:` 訊息取代 traceback。

### 2. ✅ 已修正 — `--uninstall` 搭配 component filter 會產生永久孤兒檔案

`skills/install-plugin/scripts/importer.py:1005-1015`（`uninstall_plugin()` 的
`state['plugins'].pop(target, None)`）

`uninstall_plugin()` 無條件將整個 namespace 自 manifest 移除，但 `make_plan()` 只移除
`kinds` 符合的項目。因此 `--uninstall --skills-only` 會：移除 skill，但保留 agent 連結與
MCP 設定，並把 namespace 記錄整個刪除。

實測（`--uninstall --skills-only`，來源含 skill + agent + MCP）：

```
REMOVE skills/rv3-s
manifest → {"plugins": {}, "version": 1}
dest/agents/rv3-a.md  → 仍在（dangling 或有效）
opencode.json mcp     → 仍含 rv3-api
再次 --uninstall       → Import failed: Plugin is not installed. Installed: (none).
```

結果是 agent 連結與 MCP 項**永遠無法再被工具清除**（manifest 已無記錄，
`check_owned()` 會視為未管理檔案而永不接管），使用者只能手動刪除。這直接違反 spec
「移除 manifest 擁有且未修改的元件」的可逆性，也與專案「manifest 擁有權為唯一事實來源」
的模型衝突。

**建議**：僅當 `retained` 為空時才 `pop` namespace；否則保留 namespace 並更新其
`items` 為剩餘項目，讓後續 `--uninstall` 能完成清理。

**修正**：`retained` 非空時保留 namespace 並以剩餘項目更新其 `items`，輸出改為
`Removed selected <ns> items from <root>; still managed: …`，提示重跑 `--uninstall`。
已補 `test_uninstall_with_filter_keeps_namespace_record`（還原修正後確實失敗），
並實測確認第二次 `--uninstall` 能完成清理，agent 連結與 MCP 項皆移除。

## ⚠️ 建議修正

### 3. ✅ 已修正 — `install()` 與 `main()` 對 uninstall 走兩條分歧路徑

`skills/install-plugin/scripts/importer.py:917` 與 `importer.py:1067-1080`

`main()` 在 `source is None` 時直接呼叫 `uninstall_plugin()`，有 source 時則經由
`install()` 轉呼叫同一函式。兩條路徑的錯誤處理與回傳值處理不同（前者自行 try/except
印 `Import failed`）。目前行為一致，但屬重複邏輯，未來修改其一容易漏掉另一處。
**修正**：`main()` 不再自行呼叫 `uninstall_plugin()`，改為設定 `args.source` 後統一經由
`install()` 進入，錯誤處理與回傳值只剩一條路徑。

### 4. ✅ 已修正 — `save_local_patch()` 有未使用變數

`skills/install-plugin/scripts/importer.py:602`

`fresh = root / snapshot` 賦值後從未使用（下一行重新計算 `old_path`）。已刪除。

### 5. ✅ 已修正 — `prune_snapshots()` 回傳值恆為 `True`

`skills/install-plugin/scripts/importer.py:618-655`

函式所有路徑都 `return True`，但 `main()` 以 `return 0 if prune_snapshots(...) else 1`
決定退出碼。此布林介面目前無意義，且暗示存在失敗路徑。已改為回傳 `None`，
`main()` 直接 `return 0`；真實失敗以例外表達。

### 6. `--keep-local` 的暫存目錄會留存

`skills/install-plugin/scripts/importer.py:598`

`tempfile.mkdtemp()` 建立的目錄與 patch 永久留存於系統暫存區。對「保留使用者資料」
而言這是合理的。已於 README 說明路徑並強調 patch 不會被自動刪除、需自行保存。

## 💡 優化建議

### 7. `check_owned()` 與 `make_plan()` 的參數已達 9-10 個

`skills/install-plugin/scripts/importer.py:727`、`760`

`make_plan()` 現有 10 個參數且大量使用位值或預設值。新增旗標時持續增長會提高錯位風險
（第一輪已發生過 `build_payload()` 位置傳參的問題）。建議將 `reset`／`skipped`／
`reset_needed` 收斂為單一 options 物件或 `NamedTuple`。

### 8. `snapshot_changes()` 產生的檔案清單為保守近似

`skills/install-plugin/scripts/importer.py:568-585`

無法取得原始來源比對，因此列出整個 snapshot 的所有檔案。docstring 與輸出訊息已誠實
標註「may include mtime-only changes」，可接受。若要精確需在 manifest 保留來源路徑
與基準 hash，成本較高。

### 9. `importer.py` 已達 1108 行

單一模組承載來源探索、轉換、規劃、交易、生命週期管理與 CLI。可考慮將生命週期相關
函式（`print_status`、`prune_snapshots`、`snapshot_changes`、`save_local_patch`、
`uninstall_plugin`）拆至獨立模組。屬結構性偏好，非阻擋項。

## 審查維度細則

### Conventions
- 命名符合 snake_case 動詞/名詞慣例；`uninstall_plugin`、`prune_snapshots`、
  `snapshot_changes`、`save_local_patch`、`print_status` 語意明確。
- `MIGRATION_LOG` 已於第一輪改為呼叫端持有，無模組級 mutable 狀態。
- 常數使用 UPPER_SNAKE_CASE 正確；本輪無 magic number 新增。
- Python 專案，conventions 文件的 TypeScript／path alias 規則不適用。
- 未引入新依賴（`difflib` 為標準庫），技術選型無風險。

### Architecture
- 新增函式皆為單一職責，`print_status`／`prune_snapshots` 明示唯讀或範圍。
- `uninstall` 正確複用既有 `make_plan()` 與 `check_owned()`，未另立平行流程；
  本地修改時自然被拒，符合「拒絕並保留」決策。
- 預設路徑維持嚴格，新旗標皆為 opt-in，符合 AGENTS.md 不變條件。
- 第 2 點的分歧路徑與第 7 點的參數膨脹是主要結構風險。
- 沿用 `destination_path()` 做路徑安全檢查，未自行拼接路徑，方向正確。

### Regression
- 第一輪四項修正全數維持（已於驗收矩陣實測確認）。
- 預設行為未變：無新旗標時與 `main` 版本一致，74 項測試涵蓋原有 54 項。
- 第 1、2 點為本輪新功能引入的實際資料遺失路徑，須修正。
- 交易邊界未動：`uninstall_plugin()` 與 `prune_snapshots()` 各自在
  `install_lock()` 保護下或於無寫入時執行；`--dry-run` 已實測不寫入任何檔案。
- `apply_transaction()` 未改動，rollback 語意不變。

### Test
- 新增 20 項測試（54 → 74），涵蓋五個旗標的成功、失敗與邊界路徑。
- 驗收階段已補上 CLI 層測試（`test_reset_combines_with_uninstall_on_cli` 等），
  補足第一輪「只測 API 不測 argparse」的盲口。
- **缺口 1**：無測試涵蓋 manifest `snapshot` 欄位損毀時 `--prune-snapshots` 的行為
  （即第 1 點缺陷來源）。建議補 `test_prune_refuses_when_snapshot_record_malformed`。
- **缺口 2**：無測試涵蓋 `--uninstall` 搭配 component filter 的行為
  （即第 2 點缺陷來源）。建議補 `test_uninstall_with_filter_keeps_namespace_record`。
- 測試命名描述行為，fixture 沿用既有 `self.skill()`／`self.json()` 慣例，無 flaky 風險。

### Performance
- `prune_snapshots()` 兩次 `iterdir()` 為 O(n)，n 為 namespace 數，可忽略。
- `snapshot_changes()` 對每個 snapshot 呼叫 `tree_hash()`（O(檔案數)），
  與既有 `check_owned()` 的檢查重複計算一次。因僅在 `--reset` 時執行且資料量為
  skill 樹規模，可接受；若要優化可將結果沿鏈傳遞。
- `save_local_patch()` 逐檔呼叫 `read_text()`，僅在 `--keep-local` 時執行。
- 無資料庫、無網路、無平行化問題。
- `importer.py` 1108 行於啟動時的 import 成本極低（僅標準庫 + PyYAML）。
