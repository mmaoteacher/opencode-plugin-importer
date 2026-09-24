# Plugin Import 優化

- 來源：plugin-import-session.md（`../../lawsnote/whitephoenix/`）
- 日期：2026-09-24
- Branch：feature/plugin-import-optimization

## 背景與問題
install-plugin 對 4 來源轉換過於嚴格，單一不支援特性（add-source-id、agent alias `sonnet`、MCP 名稱 `GitLab`）即阻擋整體安裝，缺跳過機制、自動修正、手動備案與 MCP 自動合併驗證。

## 目標
1. 允許跳過單一不支援組件（`--skip-unsupported`）
2. 自動修正不合法 MCP/agent 名稱（小寫、連字號）並提示
3. 提供 `--manual-mode` 產出遷移腳本（cp/mv 指令）
4. 失敗時輸出手動遷移清單（已成功/已跳過路徑）
5. MCP 設定自動寫入 `opencode.jsonc` 並驗證合併結果

## 非目標
不擴成通用轉換器（僅 4 來源）；不操作 `~/.config/opencode`；不新增反向輸出格式。

## 驗收計畫
- 靜態：現有 41 測試通過；新增測試驗證新選項。
- 實機：`--list` / `--dry-run` 不寫目的地；`--manual-mode` 僅輸出腳本；`--skip-unsupported` 完成部分遷移並保留未選元件快照。

## 風險
不接管本地已修改檔案；force 不覆寫；寫入失敗需復原（不可聲稱原子性）。
