# Plugin 生命週期管理：解除安裝、救援與狀態查詢

- 來源：第二輪 code review 與實測調查（branch `feature/plugin-import-optimization`）
- 日期：2026-09-24
- Branch：feature/plugin-lifecycle
- 前一輪 spec：docs/superpowers/specs/2026-09-24-plugin-import-optimization-spec.md

## 背景與問題

第一輪補上 `--fix-names`、`--skip-unsupported`、`--manual-mode` 與 MCP 合併驗證後，
本輪以實際執行（而非閱讀程式碼）調查「第二次安裝」與「更新套件」情境。已驗證可用的部分：

- 首次安裝後無變更重跑 → `No changes.`，冪等。
- 來源更新 → 正確 `UPDATE`／`ADD`，skill 內容與 MCP 值皆正確更新。
- Git 來源 → manifest `revision` 正確追蹤到新 commit。
- 被 `--skip-unsupported` 跳過的既有元件不會被 `--force` 誤刪（第一輪修正）。

但實測確認四項缺口，皆為使用者可觀察的行為：

1. **修改 snapshot 內檔案後永久死鎖。** 使用者編輯
   `.plugin-importer/sources/<ns>/<key>/` 內任一檔案後，所有後續匯入一律失敗於
   `Local snapshot modified or missing`，且 `--force`、`--skip-unsupported` 皆無法救回。
   錯誤訊息只說「Preserve your changes before retrying」，但沒有任何指令能走完流程。
2. **完全無解除安裝管道。** 全檔無 `uninstall`／`--clean`。plugin 一旦裝入只能永久保留，
   即使來源已廢棄。
3. **snapshot 無限累積。** 每次來源變更產生新 snapshot 目錄並保留舊有，README 已明言
   無自動回收；實測 3 版後累積 3 個目錄。
4. **無法查詢已安裝狀態。** `--list` 必須帶 source；使用者無法得知已裝哪些 plugin、
   來源為何、revision 為何、各元件指向哪個 snapshot。來源路徑改變時
   （如 repo 搬移）硬性拒絕，訊息僅建議改用其他 namespace，但舊 plugin 仍佔據名稱，
   無法查看或釋放。

## 目標

1. `--reset`：解除 snapshot 死鎖。移除前先列出將被丟棄的本地修改檔案。
2. `--uninstall`：移除 manifest 擁有且未修改的元件與 MCP 項；遇本地修改則拒絕並保留。
3. `--prune-snapshots`：清除不再被 manifest 任何項目引用的 snapshot。
4. `--status`：唯讀列出已安裝 plugin、來源、revision、元件與 snapshot，不需帶 source。

## 非目標

- 不新增第 5 種來源格式；來源支援範圍維持 Claude Code／Codex／agy／OpenCode。
- 不變更既有更新語意（sync／`-i`／`-f`、分項更新不動未選元件快照）。
- 不自動修改來源路徑衝突（來源改變仍需使用者指定 namespace）。
- 不做跨 plugin 的相依解析或版本衝突檢查。
- 不引入新的 Python 依賴。

## 現況分析

- `check_owned()`（`skills/install-plugin/scripts/importer.py`）以 `tree_hash()` 比對
  snapshot 與 manifest 記錄的 `snapshot_hash`，不一致即 `fail()`。此為死鎖來源：
  hash 檢查通過與否與匯入模式無關，所有旗標都會在此中止。
- `make_plan()` 的 `selected` 集合 = `set(desired) | {manifest 中 kind 符合的項}`，
  搭配 `mode` 決定 ADD／UPDATE／REMOVE／KEEP。解除安裝可沿用此結構，將 `desired`
  視為空集並以新 mode 表達。
- snapshot 路徑 `.plugin-importer/sources/<ns>/<key>`，key 含 `kinds`，
  故分項更新會另建 snapshot；「仍被引用」= 出現在任一 plugin 項目的 `snapshot` 欄位。
- `main()` 的 `mode` 為 mutually exclusive group（`-i` / `-f`），新旗標需注意互斥關係。

## 方案設計

### `--reset`（搭配 `--keep-local`）

`--reset` 放棄 snapshot 內的本地修改並重新安裝。流程：

1. 掃描目標 snapshot，列出與 `snapshot_hash` 不符的檔案相對路徑。
2. 印出 `Will discard local modifications:` 清單（dry-run 性質，不需互動）。
3. 使用者確認後，以來源重新轉換並覆寫該 snapshot。

`--keep-local` 為 `--reset` 的變體：先把本地差異輸出成 unified diff 存檔，再重置，
供使用者日後人工套用。兩者皆為明確 opted-in，預設行為不變。

### `--uninstall`

沿用 `make_plan()`：將 `desired` 視為空集，新增 `mode='uninstall'`。

- 移除 manifest 擁有且 snapshot 未修改的 skill／agent 連結與 MCP 設定項。
- 遇 snapshot 已修改或 MCP 值遭本地改動 → 拒絕整次操作並保留，提示改用 `--reset`。
- 移除後自 manifest 刪除該 namespace 記錄；不自動清除 snapshot（交由 `--prune-snapshots`）。
- 本地未由 manifest 管理的檔案一律不碰。

### `--prune-snapshots`

收集所有 plugin 項目的 `snapshot` 值為參考集合，刪除
`.plugin-importer/sources/<ns>/` 下未被參考的目錄。僅在無項目引用時刪除，
不碰被引用或無法判斷的項目。移除後清空可能不再需要的目錄。

### `--status`

唯讀模式，讀 manifest 後列出每個 namespace 的來源、plugin、ref、revision，
以及各項目的 kind、snapshot 與是否仍存在於目的地。不寫任何檔案，不需要 source 參數。

## 決策紀錄

| 決策 | 考慮過的選項 | 最終決定 | 理由 |
|---|---|---|---|
| 死鎖救援方式 | `--reset` 覆寫／只改訊息／雙模式 | `--reset` + `--keep-local` | 覆寫需可挽回的選項；`--keep-local` 補上「先看差異」的需求 |
| reset 的安全邊界 | 先列檔案再執行／直接重置／逐檔確認 | 先 dry-run 列出將丟棄的檔案 | 符合 AGENTS.md「force 不接管或覆寫本地修改」；決定權留給使用者 |
| 解除安裝範圍 | 同時做 uninstall+prune／只做其一／只做 prune | 兩者都做 | 使用者要能「裝了拿不掉」也能「磁碟會長」一次解決 |
| uninstall 遇本地修改 | 拒絕保留／一律移除 | 拒絕保留，除非明確加 `--reset` | 與既有保護一致，預設不丟使用者資料 |
| 本輪是否做來源變更 | `--status` 與來源改變訊息都做／只做 status | 只做 `--status` | 來源改變需跨 plugin 命名策略，範圍大，留下一輪 |
| 狀態查詢方式 | 擴充 `--list`／新增 `--status` | 新增 `--status` | `--list` 語意是「列來源內容」，擴充會混淆；`--status` 為目的地狀態 |

## 影響範圍

- `skills/install-plugin/scripts/importer.py`：`check_owned()` 放寬點、`make_plan()`
  新增 uninstall mode、`build_payload()`／`install()` 新增路徑、`main()` 新增 4 個旗標
  與互斥關係。
- `tests/test_importer.py`：新增各情境測試。
- `README.md`、`skills/install-plugin/SKILL.md`、`docs/validation.md`：說明新旗標與
  更新／解除安裝流程。

## 驗收計畫

### 靜態驗收

- `.venv/bin/python -m unittest discover -s tests` 全數通過（既有 54 項不得退步）。
- `bash -n skills/install-plugin/scripts/install-plugin.sh` 通過。
- 新增旗標不得使 `--list`／`--dry-run` 寫入目的地。

### 實機驗收

驗收 fixture 沿用第一輪 cosmo 案例，並額外建立 git 來源以驗證 revision 追蹤。

1. **reset 救援**：安裝 → 手動修改 snapshot 內 `SKILL.md` → 重跑匯入（應失敗並指出
   修改檔案）→ `--reset`（應先列出將丟棄的檔案，再完成安裝）→ 確認 destination
   更新且 manifest `snapshot_hash` 與檔案一致。
2. **keep-local**：`--reset --keep-local` 後確認 diff 檔案產出且本地修改內容可還原。
3. **uninstall 乾淨情境**：安裝多個元件與 MCP → `--uninstall` → 確認 skills/agents
   連結消失、MCP 項從 `opencode.json` 移除、manifest 不再含該 namespace。
4. **uninstall 遇本地修改**：先改 snapshot 內檔案 → `--uninstall` 應拒絕且**保留**
   全部元件（不得部分移除）；加 `--reset` 後才可進行。
5. **uninstall 不碰未管理檔案**：在 `skills/` 放一個非 manifest 管理的檔案 →
   `--uninstall` 後該檔案仍在。
6. **prune-snapshots**：連續 3 版更新後 `--prune-snapshots` → 確認只保留仍被引用的
   snapshot，被取代者移除；再執行一次匯入仍 `No changes.`（證明未誤刪）。
7. **status**：`--status` 不需 source，列出 namespace、來源、revision、元件；
   確認不寫入任何檔案（比對前後 snapshot）。
8. **既有行為不退步**：首次安裝、重跑冪等、來源更新、git revision 追蹤、
   分項更新不動未選元件快照、上一輪四項修正（fix-names／skip-unsupported／
   manual-mode／MCP 合併驗證）全數維持。
9. **隔離性**：全程僅用 `--config-dir` 指向暫存目錄，不操作 `~/.config/opencode`。

## 風險與未決事項

- `--reset` 會丟棄 snapshot 內本地修改，屬破壞性操作。緩解：必須明確 opt-in、
  先列出檔案、且不影響非 snapshot 的使用者檔案。
- snapshot 是相對路徑寫入，prune 需以 manifest 為唯一真相來源；若 manifest 損毀，
  應停止而非猜測。沿用既有 `state_read()` 的失敗策略。
- 來源改變（repo 搬移）仍需手動指定 namespace，本輪不解決；`--status` 讓使用者能看見
  衝突的 namespace 與來源，間接協助決策。
- `--keep-local` 產生的 diff 檔案放置位置（暫存目錄 vs 目的地）尚未決定，
  實作時依「不污染目的地」原則採暫存目錄並印出路徑。
- 覆寫 snapshot 時若來源已不存在該檔案，殘留的本地檔案該如何處理尚未決定；
  實作時採「僅還原 manifest 引用的項，不主動刪除 snapshot 內其他檔案」並記錄殘餘風險。
