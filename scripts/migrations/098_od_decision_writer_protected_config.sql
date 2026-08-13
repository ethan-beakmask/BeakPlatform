-- 098: OpenDefense DecisionWriter 封鎖保護清單覆寫設定
-- 建立日期: 2026-08-13
-- 對應程式: modules/form_workflow/services/node_handlers/decision_writer_handler.py
--           modules/open_defense/services/decision_service.py
--
-- 將第一批 PF-83 服務層保護新增的 allow_protected_target / on_protected
-- 節點設定補進流程設計器的 DecisionWriter config_schema,讓屬性面板可辨識。

UPDATE workflow_node_definitions
SET config_schema = config_schema || '{
        "allow_protected_target": "boolean",
        "on_protected": "string"
    }'::jsonb,
    updated_at = NOW()
WHERE node_type = 'DecisionWriter'
  AND NOT (config_schema ? 'allow_protected_target');
