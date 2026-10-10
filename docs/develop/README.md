# 開發者文件

這個目錄給**要改原始碼**的人看：有原始碼目錄、能重啟服務、能對開發用資料庫下 SQL。
使用者手冊在 `docs/manual/`，安裝與維運在 `docs/install/`。

| 檔名 | 內容 |
|---|---|
| `custom_node.md` | 替流程設計器加一種新節點：13 層觸點、三個設計決定、逐層做法、完整的 `HttpRequest` 範例規格與驗收清單 |
| `custom_node_wait.md` | 第二篇：會等待的節點怎麼不卡死、免登入回呼端點的規則、替變數系統加前綴，以及 `ExternalWait` 完整規格（與 `HttpRequest` 成對完成 webhook 往返） |
