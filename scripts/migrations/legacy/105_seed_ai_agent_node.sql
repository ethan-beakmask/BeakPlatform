-- 105: 新增 AiAgent（AI 分析）流程節點定義
-- 對應 handler: modules/form_workflow/services/node_handlers/ai_agent_handler.py
-- 註冊於 node_handlers/factory.py。config_schema 僅供文件用途，
-- 屬性面板是 wf-node-configs.js 的硬編碼分支（見 CLAUDE.md FRONT-03 段）。
INSERT INTO workflow_node_definitions
    (secure_code, node_type, display_name, description, category, icon,
     config_schema, execution_handler, is_active, is_deleted, org_secure_code, created_at, updated_at)
SELECT
    substr(md5(random()::text || clock_timestamp()::text), 1, 22),
    'AiAgent', 'AI 分析',
    '把流程資料交給本機 CLI 型 LLM 分析，結果寫入流程變數並可插入簽核註記',
    '整合', '/static/modules/form_workflow/icons/workflow/aiagent.svg',
    '{"instruction":"string","payload_template":"string","result_var":"string","decode_payload":"boolean","write_approval_note":"boolean","timeout_seconds":"integer","model":"string","on_error":"string"}'::json,
    'modules.form_workflow.services.node_handlers.ai_agent_handler.AiAgentHandler',
    true, false,
    (SELECT secure_code FROM organizations WHERE domain_name = 'system.local' LIMIT 1),
    NOW(), NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM workflow_node_definitions WHERE node_type = 'AiAgent'
);
