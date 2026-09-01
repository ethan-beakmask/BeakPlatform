-- 132_od_templates_cancel_to_detach.sql
--
-- PF-200（甲案，Ethan 2026-08-31 裁示）：End(finish_mode='cancel') 統一為「中止」語意，
-- 流程與表單自此記 CANCELLED。
--
-- 兩張資安事件處置流程範本（SOC 團隊版／小企業單人版）用 End(cancel) 只是
-- 「正常完工＋收掉 SLA 並行分支」，案子該記「已核准」。語意變更後若不改，
-- 每個正常結案的資安案件都會被記成「已取消」。改為 detach：
-- SLA 分支的 Delay 到期後會被 advance_workflow 的終態檢查擋住，不再有副作用。
--
-- 範圍：兩張模板的 graph 與 cytoscape_config、以及它們的發行快照
-- （快照是執行時實際讀的 graph，不改快照等於沒改）。
-- 產生器 scripts/examples/od_workflow_graphs.py 已同步改為 detach。
--
-- 冪等：重跑無害（replace 找不到目標字串即無變化）。

-- 模板（graph 與 cytoscape_config 兩欄都要改，引擎讀前者、設計器讀後者）
UPDATE fw_workflow_templates
SET graph = replace(graph::text, '"finish_mode": "cancel"', '"finish_mode": "detach"')::jsonb,
    cytoscape_config = CASE WHEN cytoscape_config IS NULL THEN NULL
        ELSE replace(cytoscape_config::text, '"finish_mode": "cancel"', '"finish_mode": "detach"')::jsonb END,
    revision = revision + 1,
    updated_at = (now() AT TIME ZONE 'UTC')
WHERE secure_code IN ('8bhmC3N-TDYYT7W5s0bYC3', '7LJRvpSPUYcmK1M1wcOTzY')
  AND is_deleted = false
  AND graph::text LIKE '%"finish_mode": "cancel"%';

-- 發行快照
UPDATE fw_published_form_workflows
SET workflow_snapshot = replace(workflow_snapshot::text,
        '"finish_mode": "cancel"', '"finish_mode": "detach"')::jsonb
WHERE source_workflow_template_secure_code IN ('8bhmC3N-TDYYT7W5s0bYC3', '7LJRvpSPUYcmK1M1wcOTzY')
  AND workflow_snapshot::text LIKE '%"finish_mode": "cancel"%';
