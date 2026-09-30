# Plugin Import 優化 驗收報告

- Spec：docs/superpowers/specs/2026-09-24-plugin-import-optimization-spec.md
- Plan：docs/superpowers/specs/2026-09-24-plugin-import-optimization-plan.md
- Branch：feature/plugin-import-optimization
- 驗收日期：2026-09-24
- E2E：➖ 不適用（CLI 工具，無前後端；功能驗收以實際 CLI 執行涵蓋）
- 整體結果：✅ 通過

## 自動化檢查

| 項目 | 指令 | 實際結果 | 結果 | 證據／備註 |
|---|---|---|---|---|
| 單元／整合測試 | `.venv/bin/python -m unittest discover -s tests` | Ran 54 tests，OK | ✅ | 基準 41 項全數保留，新增 13 項（末 3 項為 code review 修正後補的回歸測試） |
| Shell 語法 | `bash -n skills/install-plugin/scripts/install-plugin.sh` | 無輸出，exit 0 | ✅ | |
| OpenCode 實機 | `.venv/bin/python tests/check_opencode.py` | 發現 skill 與 agent，MCP 握手 connected | ✅ | 隔離 XDG 環境，未呼叫模型，未動 `~/.config/opencode` |

## 功能驗收矩陣

驗收 fixture 重現 `plugin-import-session.md` 的 cosmo 實際案例：帶 `allowed-tools` 的
`add-source-id` skill、`model: sonnet` 的 agent、命名為 `GitLab` 的 MCP server。

| Spec 項目 | 驗證方式 | 操作 | 預期 | 實際 | 結果 | 證據 |
|---|---|---|---|---|---|---|
| 目標 1 跳過不支援組件 | CLI | 對含三種不支援特性的 plugin 執行安裝 | 單一不支援項不阻擋整體 | 2 個可轉換項安裝成功，2 個不支援項各印 Warning 後跳過，exit 0 | ✅ | `ADD mcp/cosmo-gitlab`、`ADD skills/cosmo-commit`；warnings 分別指出 `zz-add-source-id` 與 `model: sonnet` |
| 目標 1 附帶條件 | CLI + 讀檔 | 檢查 manifest | 跳過項不得記為 managed | `managed items: ['mcp/cosmo-gitlab', 'skills/cosmo-commit']` | ✅ | 無 `add-source-id` 記錄，後續執行可重試 |
| 目標 2 自動名稱修正 | CLI | 同上 fixture，帶 `--fix-names` | `GitLab` 轉小寫合法名 | `Warning: Renamed 'GitLab' to 'gitlab'.`，落地為 `cosmo-gitlab` | ✅ | |
| 目標 2 預設嚴格 | CLI | 同 fixture 不帶選項 | 仍失敗且不寫目的地 | `Import failed: ... Invalid name 'GitLab'`，`dest` 不存在 | ✅ | |
| 目標 3 手動遷移清單 | CLI | 嚴格模式且部分已轉換 | 失敗時列出來源→目的地路徑，不寫任何檔案 | 印出 `Manual migration list` 與 `.../skills/commit -> skills/cosmo-commit`；`dest` 不存在 | ✅ | |
| 目標 3 失敗語意 | CLI | 嚴格模式 | exit code 非 0 | exit 1 | ✅ | |
| 目標 4 `--manual-mode` | CLI | 帶 `--manual-mode` | 只輸出腳本，不寫目的地 | 輸出 `#!/bin/sh`…`DEST="${1:-$HOME/.config/opencode}"`、`cp -R`、`mkdir -p`、MCP 合併註解；目的地無檔案 | ✅ | |
| 目標 4 轉換限制揭露 | CLI | 檢視腳本開頭 | 說明未套用 frontmatter 轉換 | 腳本明載 "frontmatter conversion … is NOT applied" | ✅ | |
| 目標 5 MCP 合併入 opencode.jsonc | CLI + 讀檔 | 安裝含 MCP 的 plugin | 寫入 `opencode.json` 的 `mcp`，不產生獨立 json | `mcp` 內含 `cosmo-gitlab`（`type: local`、`command: ['glab','api']`）；目錄無 `mcp-*.json` | ✅ | |
| 目標 5 合併結果回報 | CLI | 同上 | 印出合併的 server 名稱 | `MCP servers merged into opencode.json: cosmo-gitlab` | ✅ | |
| 目標 5 合併前驗證 | 自動化 | `test_mcp_merge_result_is_valid_json` | 合併後文件可解析 | 通過 | ✅ | |
| 重跑不變 | CLI | 對已安裝 plugin 重跑 | `No changes.` | `No changes.`，exit 0 | ✅ | |
| `--list` 不寫目的地 | CLI | `--list --fix-names --skip-unsupported` | 只列元件 | 列出 skills/agents/mcp；`dest2` 未建立 | ✅ | |
| `--dry-run` 不寫目的地 | CLI | `--dry-run` | 不寫、不互動 | 失敗路徑印 "nothing was written"；`dest2` 未建立 | ✅ | |
| 未選元件快照不變 | CLI + 讀檔 | 全量安裝後執行 `--skills-only` | 未選的 MCP 項快照與設定值不變 | MCP 項仍指向原快照 `de8a0ce…`，`opencode.json` 的 mcp 值未變 | ✅ | 已用 `git worktree` 於基準版 bdadac8 比對，行為一致，非本次迴歸 |
| 跳過不影響既有安裝（code review 補驗） | CLI | 已安裝 skill，來源改為不支援，重跑 `--skip-unsupported --force` | 既有元件保留，不被當成上游移除 | `KEEP skills/reg-safe (skipped this run; unsupported upstream, not removed)`，元件仍在 | ✅ | 修正前此情境會 `REMOVE` 並刪除檔案（資料遺失），已由 `test_skip_unsupported_force_keeps_installed_component` 覆蓋 |
| 真正移除仍會被 prune（code review 補驗） | CLI | 來源刪除一個 skill，另一個加上限制，重跑 `--skip-unsupported --force` | 僅真正移除者被刪 | `REMOVE skills/reg3-drop` 被刪；`KEEP skills/reg3-keep` 保留 | ✅ | 確認修正未使 `--force` 失效 |
| 失敗清單不跨執行殘留（code review 補驗） | 自動化 | 先跑一次會轉換的匯入，再跑一次早期失敗的匯入 | 第二次不印出第一次的路徑 | 輸出不含 `Manual migration list` | ✅ | 修正前會印出前次殘留路徑，由 `test_migration_log_not_stale_when_failure_precedes_build` 覆蓋 |
| 不動日常設定 | 全程 | 所有執行 | 未寫入 `~/.config/opencode` | 全部使用 `--config-dir` 指向暫存目錄 | ✅ | |

## E2E（適用時）

- 適用性：不適用。本專案為 Python CLI，無前端頁面與後端 API；使用者可觀察行為完全由
  命令列輸出與目的地面板內容構成，已由上表實際執行涵蓋。
- 測試依據：不適用（無 YouTrack issue，需求來源為 `plugin-import-session.md`）
- Markdown 報告：無
- PDF 報告：無
- 結果摘要：功能矩陣 20 項全數通過（17 項初驗 + 3 項 code review 修正後補驗）

## 未通過與未驗證項目

無。

## 驗收後修正（code review 產出）

code review 階段實測發現一項本報告初驗未覆蓋的缺陷：已安裝元件若在後續執行中被跳過，
`--force` 會將其誤判為「上游已移除」而刪除（資料遺失）。此缺陷不在初驗矩陣範圍內
（初驗僅涵蓋首次安裝），已修正並補 3 項驗證（見上表末三列）。修正後重跑完整驗證：
54 項測試通過、`check_opencode.py` 通過、上表 20 項全數通過。

補充說明（非缺陷）：`--skills-only` 等分項更新會建立新的 snapshot 目錄（snapshot key 含
`kinds`），此為 bdadac8 起的既有設計，舊快照保留且未選元件仍指向原快照。已於基準版
worktree 驗證行為一致，故不列為未通過。

## 需求基準差異

無 YouTrack issue。`plugin-import-session.md` 的 6 項迭代建議與 spec 目標對應如下：

| 來源建議 | Spec 決定 | 影響 | 待確認事項 |
|---|---|---|---|
| `--skip-unsupported` / `--continue-on-error` | 實作 `--skip-unsupported` | 已涵蓋，未加 `--continue-on-error`（語意相近且更精確） | 無 |
| 名稱自動修正 | 實作 `--fix-names` | 已涵蓋，且預設仍嚴格，需顯式 opted-in | 無 |
| model alias 自動映射 | **未實作** | 維持拒絕 + 明確錯誤訊息 | 若要自動映射 `sonnet` → `anthropic/claude-sonnet-4`，會綁定特定 provider，與「不悄悄移除權限語意」的不變條件張力，建議另開議題討論 |
| 失敗時輸出手動遷移清單 | 實作（`Manual migration list`） | 已涵蓋 | 無 |
| MCP 寫入 opencode.jsonc 並驗證 | 實作目標 5 | 已涵蓋 | 無 |
| `--manual-mode` 產出 cp/mv 腳本 | 實作 `--manual-mode` | 已涵蓋，輸出 `cp` 指令（無需 `mv`） | 無 |
