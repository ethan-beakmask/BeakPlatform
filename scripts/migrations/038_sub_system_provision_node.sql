-- 038: 子系統配置 Node Type + DcSubSystem schema 調整
-- 2026-03-12

BEGIN;

-- 1. group_unit_secure_code 改為 nullable（不再自動建立社群）
ALTER TABLE dc_sub_systems ALTER COLUMN group_unit_secure_code DROP NOT NULL;

-- 2. 新增 code 欄位（唯一識別碼，由 code generator 產生）
ALTER TABLE dc_sub_systems ADD COLUMN IF NOT EXISTS code VARCHAR(60);

-- 為已有資料補上 code（用 secure_code 前 8 碼作為暫時 code）
UPDATE dc_sub_systems SET code = UPPER(LEFT(secure_code, 8)) WHERE code IS NULL;

-- 加上唯一約束（同企業內唯一）
CREATE UNIQUE INDEX IF NOT EXISTS uix_dc_sub_systems_org_code
    ON dc_sub_systems (org_secure_code, UPPER(code))
    WHERE is_deleted = FALSE;

-- 3. 註冊 SubSystemProvision node type
INSERT INTO workflow_node_definitions (
    secure_code,
    node_type, is_active, scope, org_secure_code,
    category, display_name, description, icon,
    execution_handler,
    canvas_shape, canvas_color, canvas_width, canvas_height,
    max_input_connections, max_output_connections,
    config_schema, default_timeout_seconds, max_timeout_seconds,
    require_system_admin,
    created_at, updated_at, is_deleted
) VALUES (
    encode(gen_random_bytes(16), 'base64'),
    'SubSystemProvision', TRUE, 'SYSTEM', NULL,
    '整合', '子系統配置', '建立、停用或刪除子系統（含選單、開發者權限）', '/static/modules/form_workflow/icons/workflow/subsystemprovision.svg',
    'modules.form_workflow.services.node_handlers.sub_system_provision_handler.SubSystemProvisionHandler',
    'roundrectangle', '#8B5CF6', 180, 50,
    10, 10,
    '{
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "suspend", "delete"],
                "description": "動作類型"
            },
            "sub_system_name": {
                "type": "string",
                "description": "子系統名稱（支援變數替換，如 ${f.sub_system_name}）"
            },
            "sub_system_icon": {
                "type": "string",
                "description": "圖示 class（optional，如 bi-box-seam）"
            },
            "sub_system_developer": {
                "type": "string",
                "description": "開發者 user secure_code（支援變數替換，如 ${f.sub_system_developer}）"
            },
            "sub_system_code": {
                "type": "string",
                "description": "目標子系統 code（suspend/delete 用，支援變數替換）"
            }
        },
        "required": ["action"]
    }',
    300, 600,
    FALSE,
    NOW(), NOW(), FALSE
) ON CONFLICT (node_type) DO NOTHING;

COMMIT;
