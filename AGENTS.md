# 開發指引

## 範圍

本工具將既有 Claude Code、Codex、agy、OpenCode repository 的 skills、Markdown agents、MCP 匯入 OpenCode。
不要擴成所有 agent 的套件管理器，也不要修改相鄰的 open-design-plugin 專案。

## 不變條件

- 開發來源是本 checkout，禁止用使用者日常 ~/.config/opencode 做測試。
- --list 與 --dry-run 不寫目的地；預覽不要求互動輸入。
- 更新與刪除只處理 manifest 擁有、且本地未修改的元件。force 不接管或覆寫本地修改。
- 分項更新不得變更未選元件的資源快照；保留相對 scripts／references／assets。
- 不把無法對應的權限語意悄悄移除；支援範圍與限制需有文件。
- Catchable 寫入失敗需復原；不可聲稱跨多檔更新具備斷電原子性。
- 不提交個人設定、憑證、安裝紀錄、第三方 plugin 原始內容或本地依賴環境。

## 驗證

Python 3.9+，依賴位於 skills/install-plugin/scripts/requirements.txt。

```bash
python -m unittest discover -s tests -v
bash -n skills/install-plugin/scripts/install-plugin.sh
python tests/check_opencode.py  # 有 OpenCode CLI 時執行隔離探索與 MCP 握手
```

修改支援格式時更新 fixtures、README 及 docs/validation.md。測試應檢查使用者可觀察行為，
特別是預覽、來源偵測、轉換、重跑、分項更新、衝突、失敗復原與移除範圍。
