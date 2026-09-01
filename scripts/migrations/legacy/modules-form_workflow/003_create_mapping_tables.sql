-- FormWorkflow Module - 資料庫遷移腳本
-- 版本: 003
-- 說明: 建立表單流程配對相關資料表
-- 執行方式: psql -U beakplatform -d beakplatform_dev -f 003_create_mapping_tables.sql

-- ============================================================================
-- 表單-流程配對表 (fw_form_workflow_mappings)
-- ============================================================================
CREATE TABLE IF NOT EXISTS fw_form_workflow_mappings (
    -- 基礎欄位 (BaseModel)
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP,

    -- 多租戶欄位
    org_secure_code VARCHAR(100) NOT NULL,

    -- 表單資訊
    form_template_id BIGINT NOT NULL,
    form_template_secure_code VARCHAR(32) NOT NULL,
    form_template_code VARCHAR(100),
    form_template_version VARCHAR(10),

    -- 流程資訊
    workflow_template_id BIGINT NOT NULL,
    workflow_template_secure_code VARCHAR(32) NOT NULL,
    workflow_template_code VARCHAR(100),
    workflow_template_version VARCHAR(10),

    -- 狀態
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    priority INTEGER NOT NULL DEFAULT 0,

    -- 發行狀態
    is_published BOOLEAN NOT NULL DEFAULT FALSE,
    publish_at TIMESTAMP,

    -- 條件觸發（可選）
    trigger_condition JSONB,

    -- 備註
    description VARCHAR(500)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_fw_fwm_org ON fw_form_workflow_mappings(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_fwm_form_id ON fw_form_workflow_mappings(form_template_id);
CREATE INDEX IF NOT EXISTS idx_fw_fwm_form_code ON fw_form_workflow_mappings(form_template_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_fwm_workflow_id ON fw_form_workflow_mappings(workflow_template_id);
CREATE INDEX IF NOT EXISTS idx_fw_fwm_workflow_code ON fw_form_workflow_mappings(workflow_template_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_fwm_active ON fw_form_workflow_mappings(is_active);
CREATE INDEX IF NOT EXISTS idx_fw_fwm_published ON fw_form_workflow_mappings(is_published);
CREATE INDEX IF NOT EXISTS idx_fw_fwm_deleted ON fw_form_workflow_mappings(is_deleted);

-- ============================================================================
-- 已發行表單流程配對表 (fw_published_form_workflows)
-- ============================================================================
CREATE TABLE IF NOT EXISTS fw_published_form_workflows (
    -- 基礎欄位 (BaseModel)
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP,

    -- 多租戶欄位
    org_secure_code VARCHAR(100) NOT NULL,

    -- 來源追蹤
    source_mapping_id BIGINT NOT NULL,
    source_mapping_secure_code VARCHAR(32) NOT NULL,

    -- 表單來源資訊
    source_form_template_id BIGINT NOT NULL,
    source_form_template_secure_code VARCHAR(32) NOT NULL,
    source_form_version VARCHAR(10),
    source_form_revision BIGINT,

    -- 流程來源資訊
    source_workflow_template_id BIGINT NOT NULL,
    source_workflow_template_secure_code VARCHAR(32) NOT NULL,
    source_workflow_version VARCHAR(10),
    source_workflow_revision BIGINT,

    -- 發行資訊
    publish_version INTEGER NOT NULL DEFAULT 1,
    name VARCHAR(255) NOT NULL,
    description TEXT,

    -- 快照（完整複製）
    form_snapshot JSONB NOT NULL,
    workflow_snapshot JSONB NOT NULL,

    -- 狀態管理
    status VARCHAR(20) NOT NULL DEFAULT 'Published',

    -- 使用統計
    is_used BOOLEAN NOT NULL DEFAULT FALSE,
    first_used_at TIMESTAMP,
    instance_count INTEGER NOT NULL DEFAULT 0,

    -- 稽核欄位
    published_by VARCHAR(100),
    published_by_name VARCHAR(100),
    published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    suspended_at TIMESTAMP,
    suspended_by VARCHAR(100),
    archived_at TIMESTAMP,

    -- 約束
    CONSTRAINT fw_published_valid_status CHECK (status IN ('Published', 'Suspended', 'Archived'))
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_fw_pfw_org ON fw_published_form_workflows(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_pfw_mapping_id ON fw_published_form_workflows(source_mapping_id);
CREATE INDEX IF NOT EXISTS idx_fw_pfw_mapping_code ON fw_published_form_workflows(source_mapping_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_pfw_form ON fw_published_form_workflows(source_form_template_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_pfw_workflow ON fw_published_form_workflows(source_workflow_template_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_pfw_status ON fw_published_form_workflows(status);
CREATE INDEX IF NOT EXISTS idx_fw_pfw_published_at ON fw_published_form_workflows(published_at);
CREATE INDEX IF NOT EXISTS idx_fw_pfw_deleted ON fw_published_form_workflows(is_deleted);

-- ============================================================================
-- 完成訊息
-- ============================================================================
DO $$
BEGIN
    RAISE NOTICE '======================================';
    RAISE NOTICE 'FormWorkflow 配對資料表建立完成';
    RAISE NOTICE '建立的資料表：';
    RAISE NOTICE '  - fw_form_workflow_mappings';
    RAISE NOTICE '  - fw_published_form_workflows';
    RAISE NOTICE '======================================';
END $$;
