-- 007: Site Map 節點准入控制
-- 新增 access_roles (准入角色清單) 和 redirect_to (拒絕時轉向)
-- access_roles: [] = NONE(預設,拒絕所有), ["GUEST"] = 任何人, ["MANAGER",...] = 角色清單

ALTER TABLE dc_site_map_nodes
    ADD COLUMN IF NOT EXISTS access_roles JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS redirect_to VARCHAR(200) DEFAULT '/dashboard';

-- 將既有節點設為 GUEST (向下相容: 原本無權限記錄 = 所有人可見)
UPDATE dc_site_map_nodes
SET access_roles = '["GUEST"]'::jsonb
WHERE access_roles IS NULL OR access_roles = '[]'::jsonb;
