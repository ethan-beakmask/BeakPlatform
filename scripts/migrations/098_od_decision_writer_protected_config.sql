-- 098: OpenDefense DecisionWriter 封鎖保護清單覆寫設定
-- 建立日期: 2026-08-13
-- 對應程式: modules/form_workflow/services/node_handlers/decision_writer_handler.py
--           modules/open_defense/services/decision_service.py
--
-- 將第一批 PF-83 服務層保護新增的 allow_protected_target / on_protected
-- 補進 DecisionWriter 的 config_schema,讓節點定義與 handler 實際讀取的 config 一致。
--
-- 注意（2026-08-13 實測）:config_schema 目前只被
-- GET /api/form-workflow/workflows/nodes/<type>/schema 讀取,而**前端沒有任何程式
-- 呼叫該 API**;流程設計器的節點屬性面板是 wf-node-*.js 的 switch 硬編碼分支,
-- DecisionWriter 沒有對應分支（該節點 require_system_admin=true,流程一向由腳本建置）。
-- 因此本 migration 目前沒有可見的 UI 效果,是為了讓 DB 定義完整、
-- 日後補屬性面板時有依據。實際設定這兩個 key 目前要改 graph JSON。

UPDATE workflow_node_definitions
SET config_schema = config_schema || '{
        "allow_protected_target": "boolean",
        "on_protected": "string"
    }'::jsonb,
    updated_at = NOW()
WHERE node_type = 'DecisionWriter'
  AND NOT (config_schema ? 'allow_protected_target');
