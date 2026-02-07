-- Migration 017: 重構選單架構 - 通用選單改為系統共用
-- 問題：beakplatform.local 的選單被授權給 SYSTEM_ADMIN，違反多租戶隔離概念
-- 解法：將通用功能選單移到 system.local 並設為 is_shared = true
--
-- 執行時機：beakplatform.local 企業被軟刪除前執行
-- 注意：此遷移已於 2025-12-28 執行完成

BEGIN;

-- 1. 將通用選單移到 system.local 並設為共用
-- 這些選單對所有企業都適用，由 ResourceGateway 保證資料隔離
UPDATE menu_items
SET org_secure_code = 'system.local',
    is_shared = true,
    updated_at = NOW()
WHERE org_secure_code = 'lkpjrhad7yXuJuLOhxyS38'  -- beakplatform.local
  AND code IN (
    'dashboard',           -- 儀表板
    'personal_settings',   -- 個人設定
    'users',               -- 用戶帳號
    'roles',               -- 角色管理
    'form_workflow',       -- 表單流程系統 (父選單)
    'workflow_designer',   -- 流程設計
    'form_designer',       -- 表單設計
    'form_workflow_mapping', -- 表單流程配對
    'form_center',         -- 表單中心
    'module_area',         -- 模組區
    'system_settings',     -- 系統設定
    'departments',         -- 部門設定
    'groups',              -- 群組設定
    'module_users'         -- 模組用戶設定
  );

-- 2. 修正選單的 module 引用
-- 問題：移動後的選單仍引用 beakplatform.local 的 module
-- 解法：改為引用 system.local 的 system_core module
UPDATE menu_items
SET module_secure_code = (
    SELECT secure_code FROM modules
    WHERE org_secure_code = 'system.local'
    AND code = 'system_core'
    LIMIT 1
)
WHERE org_secure_code = 'system.local'
AND module_secure_code IN (
    SELECT secure_code FROM modules
    WHERE org_secure_code = 'lkpjrhad7yXuJuLOhxyS38'
);

-- 3. 確認結果
SELECT code, title, org_secure_code, is_shared
FROM menu_items
WHERE is_deleted = false
ORDER BY org_secure_code, display_order;

COMMIT;
