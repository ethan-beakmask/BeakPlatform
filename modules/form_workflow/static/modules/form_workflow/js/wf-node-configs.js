/**
 * wf-node-configs.js -- 節點類型配置（索引）
 * 原始 2150 行已拆分為 11 個獨立子模組：
 *
 *   wf-node-parallel-join.js   - ParallelJoin 並行匯合
 *   wf-node-field-write.js     - OP_FIELDWRITE 表單寫值
 *   wf-node-opset.js           - OPSET 變數設定
 *   wf-node-sql-executor.js    - SQLExecutor SQL 查詢
 *   wf-node-telegram.js        - Telegram + SYS_Telegram
 *   wf-node-email-relay.js     - EmailRelay 系統郵件
 *   wf-node-navbar-broadcast.js - NavbarBroadcast 跑馬燈廣播
 *   wf-node-alert-broadcast.js - AlertBroadcast 緊急廣播
 *   wf-node-email-adapter.js   - EmailAdapter 企業郵件
 *   wf-node-branch.js          - BRANCH 條件路由
 *   wf-node-form-adapter.js    - Assignee/FormAdapter 簽核
 *
 * 各子模組透過 workflow_designer.html 的 <script> 標籤載入，
 * 所有函數透過 window.xxx 匯出為全域可用。
 */
