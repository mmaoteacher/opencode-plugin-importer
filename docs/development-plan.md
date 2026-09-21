# 優化開發紀錄

## 已完成（0.1.0）

- [x] 以 Python 核心取代 Bash 字串解析，保留原 .sh 入口。
- [x] 明確指定安裝目錄；使用暫存 fixtures，避免修改日常 OpenCode 設定。
- [x] --list／--dry-run 不寫目的地或 manifest；互動預覽不提問。
- [x] 寫入前驗證、同目錄 staging、安裝鎖與 catchable 失敗復原。
- [x] 保護使用者修改與未管理檔案；force 只清除選取類別中被來源移除的完整管理項目。
- [x] 根目錄、舊式目錄、custom manifest 路徑與多 plugin 選取。
- [x] 保留整個來源資源快照，分項更新不影響未選元件的舊版資源。
- [x] local／remote MCP 格式、env、command、args、root 變數及常見 OAuth 設定。
- [x] JSON／JSONC 讀取與設定合併；保留原始設定 bytes 備份。
- [x] Markdown agent 常見 tools／permission 對應；無法保留的限制明確報錯。
- [x] sync／interactive／force 更新語意、來源 revision 與內容 hash 記錄。
- [x] MIT 授權、README 相容性矩陣、skill 使用指引與 CI。
- [x] 41 項測試與實際 OpenCode 探索／MCP 握手通過。

詳見 [驗證紀錄](validation.md)。

## 明確延後

- 原個人安裝腳本的 manifest 自動遷移：舊紀錄沒有足夠的完整性／所有權資料，先保守拒絕接管。
- 舊來源快照自動回收與使用者介面的版本還原命令。
- hooks、獨立 commands、Codex TOML agents 與不能等價映射的權限語意。
- 外部／目錄符號連結、遠端 marketplace 遞迴下載及原始碼依賴安裝。
- JSONC 註解原位修改：目前保留原始 bytes 備份，輸出正規化 JSON。
- 突然斷電／SIGKILL 的多檔交易復原日誌。
- 與 OpenPackage 等工具的同一組來源安裝 benchmark；目前只完成公開文件的功能比較。

上述限制不應被描述為已支援。後續擴充需先定義行為與測試，再更改格式轉換。
