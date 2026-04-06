/**
 * wf-core.js -- 核心初始化、事件綁定、工作流 CRUD (主檔索引)
 * 原始 3585 行已拆分為 7 個子模組
 *
 * 子模組載入順序 (HTML 中須依序載入):
 *   wf-cy-init.js      -- Cytoscape 初始化、樣式定義、修飾鍵監聽
 *   wf-events.js        -- bindEvents() 所有 Cytoscape 事件處理
 *   wf-relay.js         -- 中繼點 CRUD (折線編輯)
 *   wf-dnd-nodes.js     -- 拖放初始化、圖示對照表、節點/連線建立
 *   wf-workflow-ui.js   -- 分類折疊、介面鎖定/解鎖、流程資訊、設計模式
 *   wf-workflow-crud.js -- 儲存/關閉、版本管理、流程 CRUD、變更追蹤
 *   wf-render.js        -- 載入流程、渲染流程圖、節點類型標準化
 *
 * 依賴: workflow-main.js, wf-undo.js
 */
