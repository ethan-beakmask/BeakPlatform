-- seed_node_org_grants.sql — 受限節點的出廠授權（安裝用）
--
-- 設計（見 CLAUDE.md「節點型別的企業授權」）：org_restricted=true 的節點型別
-- 出廠只授權給系統預設企業（is_system_org=true），客戶企業看不到，
-- 之後由系統管理員在 /node-grants/ 或 scripts/node_grant.py 逐企業授權。
--
-- 前置：workflow_node_definitions 已 seed、系統企業已建立。
-- 冪等：已有未刪除 grant 的 (node_type, org) 不重複種。

BEGIN;

INSERT INTO workflow_node_org_grants (
    secure_code, node_type, org_secure_code, granted_by_secure_code,
    granted_by_name, note, created_at, updated_at, is_deleted
)
SELECT
    substr(md5(random()::text || clock_timestamp()::text), 1, 32),
    d.node_type, o.secure_code, NULL,
    'install_seed', 'system_org_default',
    now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC', FALSE
FROM workflow_node_definitions d
CROSS JOIN organizations o
WHERE d.org_restricted = TRUE
  AND d.is_deleted = FALSE
  AND o.is_system_org = TRUE
  AND o.is_deleted = FALSE
  AND NOT EXISTS (
      SELECT 1 FROM workflow_node_org_grants g
      WHERE g.node_type = d.node_type
        AND g.org_secure_code = o.secure_code
        AND g.is_deleted = FALSE
  );

COMMIT;
