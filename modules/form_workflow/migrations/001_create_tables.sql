-- FormWorkflow Module - 資料庫遷移腳本
-- 版本: 001
-- 說明: 建立 form_workflow 模組所需的資料表
-- 執行方式: psql -U beakplatform -d beakplatform_dev -f 001_create_tables.sql

-- ============================================================================
-- 表單模板 (fw_form_templates)
-- ============================================================================
CREATE TABLE IF NOT EXISTS fw_form_templates (
    -- 基礎欄位 (BaseModel)
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP,

    -- 多租戶欄位 (ModuleBaseModel)
    org_secure_code VARCHAR(32) NOT NULL,

    -- 基本資訊
    code VARCHAR(100) NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    category VARCHAR(100),

    -- form.io schema
    schema JSONB NOT NULL,

    -- 版本控制
    version VARCHAR(2) DEFAULT 'AA',
    revision BIGINT DEFAULT 1,

    -- 設計器配置
    builder_config JSONB DEFAULT '{}',

    -- 縮圖
    thumbnail_2x1 TEXT,
    thumbnail_1x1 TEXT,
    thumbnail_1x2 TEXT,

    -- 狀態
    is_published BOOLEAN NOT NULL DEFAULT FALSE,
    publish_at TIMESTAMP,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_protected BOOLEAN NOT NULL DEFAULT FALSE,

    -- 權限控制
    permission_type VARCHAR(20) NOT NULL DEFAULT 'org',
    owner_secure_code VARCHAR(50),
    allowed_editors JSONB
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_fw_form_templates_org ON fw_form_templates(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_form_templates_code ON fw_form_templates(code);
CREATE INDEX IF NOT EXISTS idx_fw_form_templates_category ON fw_form_templates(category);
CREATE INDEX IF NOT EXISTS idx_fw_form_templates_published ON fw_form_templates(is_published);
CREATE INDEX IF NOT EXISTS idx_fw_form_templates_active ON fw_form_templates(is_active);
CREATE INDEX IF NOT EXISTS idx_fw_form_templates_deleted ON fw_form_templates(is_deleted);
CREATE INDEX IF NOT EXISTS idx_fw_form_templates_owner ON fw_form_templates(owner_secure_code);

-- ============================================================================
-- 工作流模板 (fw_workflow_templates)
-- ============================================================================
CREATE TABLE IF NOT EXISTS fw_workflow_templates (
    -- 基礎欄位 (BaseModel)
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP,

    -- 多租戶欄位
    org_secure_code VARCHAR(32) NOT NULL,

    -- 關聯的表單模板
    form_template_secure_code VARCHAR(32),

    -- 基本資訊
    code VARCHAR(100) NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    category VARCHAR(100),

    -- Cytoscape.js 流程圖
    graph JSONB NOT NULL,
    cytoscape_config JSONB,

    -- 版本控制
    version VARCHAR(2) DEFAULT 'AA',
    revision BIGINT DEFAULT 0,

    -- 縮圖
    thumbnail_2x1 TEXT,
    thumbnail_1x1 TEXT,
    thumbnail_1x2 TEXT,

    -- 狀態
    is_published BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_protected BOOLEAN NOT NULL DEFAULT FALSE,

    -- 權限控制
    permission_type VARCHAR(20) NOT NULL DEFAULT 'org',
    owner_secure_code VARCHAR(50),
    allowed_editors JSONB,

    -- 子流程相關
    is_subprocess BOOLEAN NOT NULL DEFAULT FALSE,
    parent_workflow_secure_code VARCHAR(32),

    -- 超時設定
    timeout_minutes INTEGER
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_fw_workflow_templates_org ON fw_workflow_templates(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_workflow_templates_code ON fw_workflow_templates(code);
CREATE INDEX IF NOT EXISTS idx_fw_workflow_templates_category ON fw_workflow_templates(category);
CREATE INDEX IF NOT EXISTS idx_fw_workflow_templates_form ON fw_workflow_templates(form_template_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_workflow_templates_published ON fw_workflow_templates(is_published);
CREATE INDEX IF NOT EXISTS idx_fw_workflow_templates_active ON fw_workflow_templates(is_active);
CREATE INDEX IF NOT EXISTS idx_fw_workflow_templates_deleted ON fw_workflow_templates(is_deleted);
CREATE INDEX IF NOT EXISTS idx_fw_workflow_templates_subprocess ON fw_workflow_templates(is_subprocess);
CREATE INDEX IF NOT EXISTS idx_fw_workflow_templates_parent ON fw_workflow_templates(parent_workflow_secure_code);

-- ============================================================================
-- 表單實例 (fw_form_instances)
-- ============================================================================
CREATE TABLE IF NOT EXISTS fw_form_instances (
    -- 基礎欄位 (BaseModel)
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP,

    -- 多租戶欄位
    org_secure_code VARCHAR(32) NOT NULL,

    -- 關聯的模板
    form_template_secure_code VARCHAR(32) NOT NULL,
    workflow_template_secure_code VARCHAR(32),
    published_secure_code VARCHAR(32),

    -- 測試標記
    is_test BOOLEAN NOT NULL DEFAULT FALSE,

    -- 來源資訊
    source_type VARCHAR(50) NOT NULL DEFAULT 'WEB',
    source_ip VARCHAR(100),
    source_user_agent TEXT,
    source_api_key VARCHAR(200),

    -- 申請人
    applicant_secure_code VARCHAR(32),
    applicant_name VARCHAR(200),
    applicant_dept VARCHAR(200),
    applicant_username VARCHAR(200),
    applicant_email VARCHAR(200),

    -- 表單內容
    form_data JSONB NOT NULL,
    builder_config JSONB,

    -- 狀態
    status VARCHAR(50) NOT NULL DEFAULT 'DRAFT',
    current_node_id VARCHAR(100),

    -- 標題
    title VARCHAR(500),

    -- 編號
    serial_number VARCHAR(100) NOT NULL UNIQUE,

    -- 時間
    submitted_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_fw_form_instances_org ON fw_form_instances(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_form_instances_template ON fw_form_instances(form_template_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_form_instances_workflow ON fw_form_instances(workflow_template_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_form_instances_status ON fw_form_instances(status);
CREATE INDEX IF NOT EXISTS idx_fw_form_instances_applicant ON fw_form_instances(applicant_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_form_instances_deleted ON fw_form_instances(is_deleted);
CREATE INDEX IF NOT EXISTS idx_fw_form_instances_test ON fw_form_instances(is_test);
CREATE INDEX IF NOT EXISTS idx_fw_form_instances_serial ON fw_form_instances(serial_number);

-- ============================================================================
-- 工作流實例 (fw_workflow_instances)
-- ============================================================================
CREATE TABLE IF NOT EXISTS fw_workflow_instances (
    -- 基礎欄位 (BaseModel)
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP,

    -- 多租戶欄位
    org_secure_code VARCHAR(32) NOT NULL,

    -- 關聯
    form_instance_secure_code VARCHAR(32),
    workflow_template_secure_code VARCHAR(32) NOT NULL,

    -- 狀態
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',

    -- 當前節點
    current_node_id VARCHAR(100),
    current_node_type VARCHAR(50),

    -- 執行紀錄
    execution_code VARCHAR(50) NOT NULL UNIQUE,
    execution_log JSONB DEFAULT '[]',

    -- 流程變數
    variables JSONB DEFAULT '{}',

    -- 測試標記
    is_test BOOLEAN NOT NULL DEFAULT FALSE,

    -- 錯誤資訊
    error_message TEXT,
    error_node_id VARCHAR(100),

    -- 建立者
    created_by_secure_code VARCHAR(32),

    -- 超時
    timeout_at TIMESTAMP,

    -- 時間
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_fw_workflow_instances_org ON fw_workflow_instances(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_workflow_instances_form ON fw_workflow_instances(form_instance_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_workflow_instances_template ON fw_workflow_instances(workflow_template_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_workflow_instances_status ON fw_workflow_instances(status);
CREATE INDEX IF NOT EXISTS idx_fw_workflow_instances_execution ON fw_workflow_instances(execution_code);
CREATE INDEX IF NOT EXISTS idx_fw_workflow_instances_deleted ON fw_workflow_instances(is_deleted);
CREATE INDEX IF NOT EXISTS idx_fw_workflow_instances_test ON fw_workflow_instances(is_test);

-- ============================================================================
-- 簽核記錄 (fw_approval_records)
-- ============================================================================
CREATE TABLE IF NOT EXISTS fw_approval_records (
    -- 基礎欄位 (BaseModel)
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP,

    -- 多租戶欄位
    org_secure_code VARCHAR(32) NOT NULL,

    -- 關聯
    form_instance_secure_code VARCHAR(32) NOT NULL,
    workflow_instance_secure_code VARCHAR(32),

    -- 節點資訊
    node_id VARCHAR(100) NOT NULL,
    node_name VARCHAR(200),

    -- 簽核人
    approver_secure_code VARCHAR(32),
    approver_name VARCHAR(200),
    approver_dept VARCHAR(200),

    -- 代理人資訊
    delegate_from_secure_code VARCHAR(32),
    delegate_from_name VARCHAR(200),

    -- 簽核動作
    action VARCHAR(50) NOT NULL,

    -- 簽核意見
    comment TEXT,

    -- 時間
    assigned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    acted_at TIMESTAMP
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_fw_approval_records_org ON fw_approval_records(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_approval_records_form ON fw_approval_records(form_instance_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_approval_records_workflow ON fw_approval_records(workflow_instance_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_approval_records_approver ON fw_approval_records(approver_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_approval_records_action ON fw_approval_records(action);
CREATE INDEX IF NOT EXISTS idx_fw_approval_records_deleted ON fw_approval_records(is_deleted);

-- ============================================================================
-- 節點執行隊列 (fw_node_execution_queue)
-- ============================================================================
CREATE TABLE IF NOT EXISTS fw_node_execution_queue (
    -- 基礎欄位 (BaseModel)
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP,

    -- 多租戶欄位
    org_secure_code VARCHAR(32) NOT NULL,

    -- 關聯的工作流實例
    workflow_instance_secure_code VARCHAR(32) NOT NULL,

    -- 節點資訊
    node_id VARCHAR(100) NOT NULL,
    node_type VARCHAR(50) NOT NULL,
    node_name VARCHAR(200),
    node_config JSONB DEFAULT '{}',

    -- 執行狀態
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',

    -- 重試資訊
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 3,

    -- 執行結果
    result JSONB,
    error_message TEXT,

    -- 時間
    scheduled_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,

    -- Worker 資訊
    worker_id VARCHAR(100),
    process_id INTEGER
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_fw_node_execution_queue_org ON fw_node_execution_queue(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_node_execution_queue_workflow ON fw_node_execution_queue(workflow_instance_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_node_execution_queue_type ON fw_node_execution_queue(node_type);
CREATE INDEX IF NOT EXISTS idx_fw_node_execution_queue_status ON fw_node_execution_queue(status);
CREATE INDEX IF NOT EXISTS idx_fw_node_execution_queue_deleted ON fw_node_execution_queue(is_deleted);
CREATE INDEX IF NOT EXISTS idx_fw_node_execution_queue_scheduled ON fw_node_execution_queue(scheduled_at);

-- ============================================================================
-- 工作流變數 (fw_workflow_variables) - 選用
-- ============================================================================
CREATE TABLE IF NOT EXISTS fw_workflow_variables (
    -- 基礎欄位
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- 多租戶欄位
    org_secure_code VARCHAR(32) NOT NULL,

    -- 關聯
    workflow_instance_secure_code VARCHAR(32) NOT NULL,

    -- 變數資訊
    var_name VARCHAR(200) NOT NULL,
    var_value JSONB,
    var_type VARCHAR(50) DEFAULT 'GLOBAL',  -- GLOBAL, LOCAL

    -- 來源節點
    source_node_id VARCHAR(100)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_fw_workflow_variables_workflow ON fw_workflow_variables(workflow_instance_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_workflow_variables_name ON fw_workflow_variables(var_name);
CREATE INDEX IF NOT EXISTS idx_fw_workflow_variables_type ON fw_workflow_variables(var_type);

-- 唯一約束
CREATE UNIQUE INDEX IF NOT EXISTS idx_fw_workflow_variables_unique
    ON fw_workflow_variables(workflow_instance_secure_code, var_name, var_type);

-- ============================================================================
-- 完成訊息
-- ============================================================================
DO $$
BEGIN
    RAISE NOTICE '======================================';
    RAISE NOTICE 'FormWorkflow 模組資料表建立完成';
    RAISE NOTICE '建立的資料表：';
    RAISE NOTICE '  - fw_form_templates';
    RAISE NOTICE '  - fw_workflow_templates';
    RAISE NOTICE '  - fw_form_instances';
    RAISE NOTICE '  - fw_workflow_instances';
    RAISE NOTICE '  - fw_approval_records';
    RAISE NOTICE '  - fw_node_execution_queue';
    RAISE NOTICE '  - fw_workflow_variables';
    RAISE NOTICE '======================================';
END $$;
