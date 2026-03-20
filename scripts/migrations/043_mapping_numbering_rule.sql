-- 043: 配對層級表單編號規則
-- 讓每組配對可選擇自己的編號規格

-- 1. fw_form_workflow_mappings 加入編號規則欄位
ALTER TABLE fw_form_workflow_mappings
    ADD COLUMN IF NOT EXISTS numbering_rule_secure_code VARCHAR(32) DEFAULT NULL;

COMMENT ON COLUMN fw_form_workflow_mappings.numbering_rule_secure_code
    IS '表單編號規則 secure_code（NULL = 使用企業表單預設）';

-- 2. fw_published_form_workflows 加入編號規則快照
ALTER TABLE fw_published_form_workflows
    ADD COLUMN IF NOT EXISTS numbering_rule_secure_code VARCHAR(32) DEFAULT NULL;

COMMENT ON COLUMN fw_published_form_workflows.numbering_rule_secure_code
    IS '發行時快照的編號規則 secure_code（NULL = 使用企業表單預設）';
