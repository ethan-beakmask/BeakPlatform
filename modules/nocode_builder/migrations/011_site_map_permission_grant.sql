-- 011: SiteMapPermission 准入權限欄位擴充
-- 新增 grant_type / grant_target / grant_target_name / include_children
-- 用於部門/社群/個人多重選擇准入模式

ALTER TABLE dc_site_map_permissions
    ADD COLUMN IF NOT EXISTS grant_type VARCHAR(20),
    ADD COLUMN IF NOT EXISTS grant_target VARCHAR(100),
    ADD COLUMN IF NOT EXISTS grant_target_name VARCHAR(200) DEFAULT '',
    ADD COLUMN IF NOT EXISTS include_children BOOLEAN NOT NULL DEFAULT FALSE;

-- 放寬舊欄位 NOT NULL（新記錄不一定填）
ALTER TABLE dc_site_map_permissions
    ALTER COLUMN target_type DROP NOT NULL,
    ALTER COLUMN target_secure_code DROP NOT NULL;

-- target_secure_code 原本 VARCHAR(32)，grant_target 可能存 '__ORG_ROOT__' 等虛擬值
-- 同步放寬 target_secure_code 長度
ALTER TABLE dc_site_map_permissions
    ALTER COLUMN target_secure_code TYPE VARCHAR(100);

-- 索引
CREATE INDEX IF NOT EXISTS idx_dc_smp_grant_type
    ON dc_site_map_permissions (grant_type)
    WHERE is_deleted = FALSE;
