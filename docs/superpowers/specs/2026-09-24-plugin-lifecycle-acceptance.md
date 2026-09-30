# Plugin 生命週期管理 驗收報告

- Spec：docs/superpowers/specs/2026-09-24-plugin-lifecycle-spec.md
- Plan：docs/superpowers/specs/2026-09-24-plugin-lifecycle-plan.md
- Branch：feature/plugin-lifecycle
- 驗收日期：2026-09-24
- E2E：➖ 不適用（CLI 工具，無前後端；使用者可觀察行為由實際 CLI 執行涵蓋）
- 整體結果：✅ 通過（驗收中發現並修正 1 項 CLI 層缺陷）

## 自動化檢查

| 項目 | 指令 | 實際結果 | 結果 | 證據／備註 |
|---|---|---|---|---|
| 單元／整合測試 | `.venv/bin/python -m unittest discover -s tests` | Ran 74 tests，OK | ✅ | 進場時 72 項全綠且未退步；驗收中修正後新增 2 項共 74 項 |
| Shell 語法 | `bash -n skills/install-plugin/scripts/install-plugin.sh` | 無輸出，exit 0 | ✅ | |
| OpenCode 實機 | `.venv/bin/python tests/check_opencode.py` | 發現 skill 與 agent，MCP 握手 connected | ✅ | 隔離 XDG 環境，未呼叫模型 |

## 功能驗收矩陣

驗收 fixture：`acc2`（兩個 skill、一個 agent、一個 MCP），`cosmo`（重現第一輪的不支援
案例），`git`（git 來源追蹤 revision）。全程以 `--config-dir` 指向暫存目錄。

| Spec 項目 | 驗證方式 | 操作 | 預期 | 實際 | 結果 | 證據 |
|---|---|---|---|---|---|---|
| 目標 1 `--reset` 救援 | CLI | 安裝 → 改 snapshot 內 `SKILL.md` → 重跑 | 先失敗 | `Import failed: Local snapshot modified or missing: …`，訊息含 `--reset (optionally --keep-local)` 指引 | ✅ | |
| 目標 1 `--reset` 生效 | CLI | 同上狀態加 `--reset` | 先列檔案再完成安裝 | 印 `Will discard local modifications in snapshot(s) (may include mtime-only changes):` 及檔案清單，內容還原（`MY LOCAL EDIT` 消失），印 `Installed` | ✅ | |
| 目標 1 復原後可再更新 | CLI | reset 後再跑一次 | `No changes.` | `No changes.` | ✅ | |
| 目標 2 `--keep-local` | CLI | 改 snapshot 後 `--reset --keep-local` | 產生含本地修改的 diff | 印 patch 路徑；patch 內容含 `description: PRESERVE THIS` → `description: Alpha skill v1` 與 `-mine`／`+Alpha v1` | ✅ | |
| 目標 4 uninstall 乾淨情境 | CLI | 安裝 2 skill＋agent＋MCP → `--uninstall` | 連結、MCP、manifest 全清 | 3 個 `REMOVE`；`skills/` 與 `agents/` 空；`mcp` 為 `{}`；manifest `plugins` 為 `{}` | ✅ | |
| 目標 4 uninstall 遇本地修改 | CLI | 改 snapshot 後 `--uninstall` | 拒絕且完整保留 | `Import failed: Local snapshot modified or missing…`；`skills/` 仍有 `acc2-alpha`、`acc2-beta`（未部分移除） | ✅ | |
| 決策「加 `--reset` 後才可進行」 | CLI | 同上狀態 `--uninstall --reset` | 可完成移除 | 全部 `REMOVE` 並清空 manifest | ✅ | **驗收中發現缺陷並修正，見下** |
| 目標 4 不碰未管理檔案 | CLI | 事先放入 `skills/MY-OWN.md` → uninstall | 該檔案保留 | `MY-OWN.md` 內容仍為 `mine` | ✅ | |
| 目標 3 `--prune-snapshots` | CLI | 連續 3 版更新後 prune | 僅保留被引用者 | 3 → 1，印 `Removed 2 unreferenced snapshot(s).` | ✅ | |
| 目標 3 dry-run | CLI | 同上但加 `--dry-run` | 不刪除 | 印 `PRUNE` 兩筆與 `Dry run: no snapshot removed.`；數量仍為 3 | ✅ | |
| 目標 3 未誤刪 | CLI | prune 後再匯入 | `No changes.` | `No changes.` | ✅ | |
| 目標 4 `--status` | CLI | 不帶 source | 列出 namespace／來源／revision／元件 | 輸出 `PLUGIN acc2`、`source:`、`plugin: acc2`、`ref: (unpinned)`、`revision: (local working copy)`、4 個 `present=yes` 項 | ✅ | |
| 目標 4 `--status` 唯讀 | CLI + 讀檔 | 執行前後比對目的地檔案 shasum | 完全未寫入 | 前后 shasum 相同 | ✅ | |
| 既有 1 首次安裝 | CLI | 全新目的地 | ADD 三類元件 | 正常 | ✅ | |
| 既有 2 重跑冪等 | CLI | 無變更重跑 | `No changes.` | `No changes.` | ✅ | |
| 既有 3 來源更新 | CLI | 改來源內容 | 正確 UPDATE | 印 `UPDATE`，內容更新 | ✅ | |
| 既有 4 git revision 追蹤 | CLI | git 來源 commit v2 後重匯 | revision 更新 | `rev1: d6a7b677d4` → `UPDATE skills/g-g` → `rev2: a1620c4a72` | ✅ | |
| 既有 5 `--fix-names`（第一輪） | CLI | `GitLab` MCP | 轉小寫並警告 | `Warning: Renamed 'GitLab' to 'gitlab'.`，落地 `cosmo-gitlab` | ✅ | |
| 既有 5 預設嚴格（第一輪） | CLI | 同 fixture 不帶旗標 | 仍失敗 | `Import failed: Skill bad uses invocation/tool restrictions…` | ✅ | |
| 既有 6 `--skip-unsupported`（第一輪） | CLI | 含不支援項 | 跳過並安裝其餘 | 跳過 `bad` 與 `aliased`（各一 Warning），安裝 `cosmo-ok` 與 `cosmo-gitlab` | ✅ | |
| 既有 6 跳過項不被 `-f` 誤刪（第一輪） | CLI | 已安裝 skill 加限制後 `-f --skip-unsupported` | 保留 | `KEEP skills/o-s (skipped this run; unsupported upstream, not removed)`，檔案仍在 | ✅ | |
| 既有 7 `--manual-mode`（第一輪） | CLI | 帶該旗標 | 只輸出腳本 | 輸出 `#!/bin/sh` 與轉換限制說明 | ✅ | |
| 既有 8 list/dry-run 不寫入 | CLI | `--list`、`--dry-run` | 目的地未建立 | `ls` 報不存在 | ✅ | |
| 隔離性 | 讀檔 | 檢查 `~/.config/opencode` | 未被寫入 | 該目錄 mtime 為驗收前時間，本次驗收未觸碰 | ✅ | |

## E2E（適用時）

- 適用性：不適用。本專案為 Python CLI，無前端頁面與後端 API。使用者可觀察行為完全由
  命令列輸出與目的地面板內容構成，已由上表實際執行涵蓋。
- 測試依據：不適用（無 YouTrack issue；需求來源為第一輪 code review 的實測調查）
- Markdown 報告：無
- PDF 報告：無
- 結果摘要：功能矩陣 26 項全數通過

## 未通過與未驗證項目

無未通過項目。以下為驗收中發現並已修正的缺陷。

### 驗收中發現的缺陷：`--uninstall --reset` 被 argparse 拒絕

- **現象**：spec 決策明確要求「uninstall 遇到本地修改則拒絕並保留，除非明確加 `--reset`」，
  但實際執行 `--uninstall --reset` 得到
  `error: argument --reset: not allowed with argument --uninstall`。
  原因是 `--reset` 被放進 `mode` 的 mutually exclusive group。
- **為何單元測試沒抓到**：原測試 `test_uninstall_with_reset_removes_modified` 直接呼叫
  `install(uninstall=True, reset=True)`，繞過了 argparse，因此無法發現旗標組合在
  CLI 層不可用。這正是「只測 API 不測 CLI」的盲點。
- **修正**：將 `--reset` 移出 mutually exclusive group（它是修飾語而非模式，可與 `-f`
  或 `--uninstall` 併用），並補兩項 CLI 層回歸測試
  `test_reset_combines_with_uninstall_on_cli`、`test_reset_combines_with_force_on_cli`。
  兩者皆經負向驗證：把 `--reset` 放回 exclusive group 後確實失敗。
- **影響**：修正後重新執行受影響的驗收項目（決策「加 `--reset` 後才可進行」）通過。

## 需求基準差異

| Issue 描述 | Spec 決定 | 影響 | 待確認事項 |
|---|---|---|---|
| （無 YouTrack issue） | `--uninstall` 不需 `source` 參數 | 實作中發現 plan Task 1 僅列 `--status`／`--prune-snapshots` 免除 source，`--uninstall` 仍要求而無法使用主要情境。已一併修正並補測試 | 無 |
| （同上） | `--keep-local` diff 存放於暫存目錄並印出路徑 | 已實作，落在 `tempfile.mkdtemp(prefix='opencode-importer-local-')`，不污染目的地 | 使用者需自行保存，暫存目錄可能由系統清理；已於 README 說明 |
| （同上） | 來源已刪除檔案時不主動刪除 snapshot 內其他檔案 | 本輪未實作此情境；`--reset` 以整個 snapshot 覆寫，殘餘檔案隨覆寫消失 | 若來源移除檔案且使用者從未本地修改該檔案，該檔案會在下次更新時消失（與上游一致）。本地修改者則由 `--keep-local` 保留差異 |
