# Code Review：plugin-import 優化

- 審查範圍：`bdadac8..bbbd54b`（5 個功能 commit + 3 個 docs commit）
- 主要變更：`skills/install-plugin/scripts/importer.py`（+146/-27）、`tests/test_importer.py`（+96）
- 審查維度：Conventions / Architecture / Regression / Test / Performance

## 修正狀態

三項必須修正項目已於同一 branch 修正並補上回歸測試（詳見各節「✅ 已修正」）。
四項建議修正中，第 6、7 項採納；第 4、5 項為結構性偏好，未於本次變更，以避免在
修正資料遺失缺陷的同時擴大改動範圍。剩餘 💡 項目未實作。

## 🚫 必須修正

### 1. ✅ 已修正 — `--skip-unsupported` 搭配 `--force` 會刪除先前已安裝的元件（資料遺失）

`skills/install-plugin/scripts/importer.py:474-509`

被跳過的元件不會進入 `desired`，因此 `make_plan()` 的 `selected` 集合（importer.py:632）中
仍存在 manifest 記錄的舊項會被判定為「removed upstream」，在 `--force` 模式下遭到
`REMOVE`。但上游並未移除該元件，只是本次無法轉換。

實測（已安裝 `skills/reg-safe`，再於來源加上 `allowed-tools`，重跑）：

```
$ importer.py <source> --skip-unsupported --force
Warning: Skipping skill safe: ...
REMOVE skills/reg-safe
$ ls dest/skills/          # 空，元件被刪除
```

預期行為：跳過不應等同移除。

**修正**：`build_payload()` 新增 `skipped` 參數收集被跳過的 export，
`make_plan()`（`selected -= skipped`）將其排除於選取集合外，因此跳過只影響本次新增，
不影響既有安裝。已補 `test_skip_unsupported_force_keeps_installed_component`
（還原修正後該測試確實失敗）與 `test_skip_unsupported_sync_reports_skip_not_removal`。
另實測確認真正於上游移除的元件仍會被 `--force` prune，修正未使 force 失效。

### 2. ✅ 已修正 — 同步模式下的誤導訊息

`skills/install-plugin/scripts/importer.py:640`

同上情境在預設 sync 模式會印出 `KEEP skills/reg2-safe (removed upstream)`。元件實際仍在
上游，訊息會誤導使用者以為來源已刪除該元件。

**修正**：跳過且已安裝的元件改以
`KEEP <export> (skipped this run; unsupported upstream, not removed)` 呈現。

### 3. ✅ 已修正 — 遷移清單跨呼叫殘留

原 `MIGRATION_LOG` 為模組級全域，僅在 `build_payload()` 開頭清除。若失敗發生在其之前
（例如 `Plugin not found`），`main()` 仍會印出上一次呼叫殘留的路徑。實測曾印出
`skills/leak-hello`，而該來源在第二次呼叫中並不存在。

**修正**：移除模組級全域，改為 `install()` 呼叫端持有的 `migration_log` 參數，由
`main()` 每次呼叫建立。已補 `test_migration_log_not_stale_when_failure_precedes_build`
（還原為原本的全域設計後該測試確實失敗）。

## ⚠️ 建議修正

### 4. `install()` 參數已達 11 個且未使用關鍵字

`skills/install-plugin/scripts/importer.py:766-767`

`mode, preview, listing, ask, fix, skip, manual` 皆為位置參數，且布林旗標密集
（3 個 `True/False` 連續）。`build_payload()` 另以位置方式傳入 `fix, skip`
（importer.py:798），一旦插入參數即會靜默錯位。建議將 `build_payload()` 的
`fix, skip` 改為關鍵字傳遞，並考慮將三個布林收斂為單一 options 物件或命名tuple。

### 5. `make_plan()` 回傳值擴充影響呼叫點

`skills/install-plugin/scripts/importer.py:694`、`810`

回傳值由 2 tuple 擴為 3 tuple。專案內僅一處呼叫，已同步更新，無實際風險；但此函式
已承擔「規劃 + 驗證合併結果 + 產生備份路徑 + 回報」四項職責。可考慮將 MCP 合併驗證
（importer.py:675-682）獨立成函式，回傳布林或拋錯，讓 `make_plan` 維持回傳
`(retained, changes)`。此非阻擋項，僅指出職責集中。

### 6. ✅ 已修正 — 手動遷移清單在部分進度下語意不明

`skills/install-plugin/scripts/importer.py:868-876`

清單列出的是「已轉換成功」的項目，但使用者看到 `Import failed` 時可能誤以為這些項目
已安裝。

**修正**：標題改為 `Manual migration list (converted but not installed):`。

### 7. `--fix-names` 的正規化可能產生碰撞，已正確阻擋但訊息不明確

實測 `GitLab` 與 `gitlab` 同時存在且轉換後不同，正確拋出
`Conflicting MCP definitions: gitlab`。行為正確，但錯誤訊息未指出是
`--fix-names` 造成的碰撞，使用者不易理解。

**未修正**：碰撞源自來源本身存在兩個不同定義，錯誤訊息已指名衝突的 key。追加
`--fix-names` 線索需在 `mcp_entries()` 額外傳遞修正旗標，屬非必要複雜度，評估後
維持現狀。

## 💡 優化建議

### 8. `print_manual_script()` 對 MCP 項不做路徑輸出，資訊量有限

`skills/install-plugin/scripts/importer.py:523-551`

MCP 僅輸出 `# key` 註解，使用者仍需自行查閱來源檔案才知道要填什麼。可考慮一併輸出
來源 `.mcp.json` 路徑，讓使用者能對照原始設定手動合併。

### 9. `normalize_name()` 與既有 `discover()` 內的正規化重複

`skills/install-plugin/scripts/importer.py:229` 仍內嵌
`re.sub(r'[^a-z0-9]+', '-', ...)`，與新增的 `normalize_name()`（importer.py:55）
邏輯相同但未截斷至 64 字元。可直接改用 `normalize_name()`，消除重複實作。

### 10. `if im_migration := MIGRATION_LOG:` 變數命名

`skills/install-plugin/scripts/importer.py:868`

`im_migration` 帶有 `im_` 前綴但此處並非 module 引用，且名稱未反映「遷移清單」
語意。建議改為 `pending_migrations`。

## 審查維度細則

### Conventions
- 命名符合 snake_case 動詞/名詞慣例；`normalize_name`、`print_manual_script`、
  `shell_quote` 語意明確。
- 常數 `MIGRATION_LOG` 使用 UPPER_SNAKE_CASE 正確。
- 本專案為 Python，conventions 文件中多數 TypeScript／path alias 規則不適用。
- 未引入新套件，技術選型無風險。
- JSDoc／`TODO:` 規則以 docstring 等價物滿足。

### Architecture
- 三個新旗標皆為 opt-in，預設嚴格行為未變，維持「不悄悄移除權限語意」的邊界；
  `check_owned()` 刻意不傳 `fix`（importer.py:556），所有權驗證仍嚴格，設計正確。
- `print_manual_script()` 與 `make_plan()` 分離，職責清楚。
- 未引入過度抽象；`build_payload()` 略微膨脹但仍在可維護範圍。
- 全域 `MIGRATION_LOG` 是本次唯一跨越模組邊界的共享狀態，見第 3 點。

### Regression
- 預設路徑（無新旗標）行為與 `bdadac8` 一致，51 項測試涵蓋原有 41 項且全數通過。
- 已於基準版 worktree 比對分項更新的快照行為，確認非本次迴歸。
- 第 1、2、3 點為本次新旗標引入的實際風險，須修正。
- 交易邊界未變動：`--manual-mode` 在 `install_lock()` 之前 return，不取得鎖也不寫入；
  MCP 合併驗證在 `apply_transaction()` 之前，失敗時目的地未變動。

### Test
- 新增 10 項測試，涵蓋 fix-names（成功與預設失敗）、skip-unsupported
  （skill/agent/MCP 各自跳過與預設失敗）、遷移清單、manual-mode、合併 JSON 有效性。
- 測試沿用既有 `unittest` 與 `setUp` fixture 慣例（`self.skill()`、`self.snapshot()`），
  命名描述行為，符合專案風格。
- **缺口**：無測試涵蓋「已安裝元件在 `--skip-unsupported --force` 下遭移除」，
  這是第 1 點的缺陷來源。建議補兩項：
  - `test_skip_unsupported_force_keeps_installed_component`
  - `test_migration_log_not_stale_when_failure_precedes_build`
- 無 flaky 風險：測試不依賴時間或執行順序，暫存目錄於 `tearDown` 清理。

### Performance
- `MIGRATION_LOG` 僅累積元件數量級字串（O(n)，n 為元件數），無實質影響。
- `json.loads(encoded(updated_config))` 為額外一次序列化往返，配置檔規模下可忽略；
  換取寫入前保險，屬合理取捨。
- `print_manual_script()` 走 `sorted(desired)`，O(n log n)，無巢狀迴圈。
- 無資料庫、無網路呼叫、無平行化問題。
