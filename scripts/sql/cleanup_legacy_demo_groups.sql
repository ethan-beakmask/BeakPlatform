-- 清除舊版範例資料留下的空群組 EXT_PARTNER（外部合作夥伴）
--
-- 舊版 seed_demo_org.py 會在企業群組樹的根層建立這個群組，但外部廠商帳號只能歸屬
-- EXTERNAL_VENDORS 底下的群組，所以它從來沒有作用。新版範例已不再建立。
--
-- 只處理「代碼與名稱都相符、位於根層、非系統群組，且沒有任何子群組、成員、
-- 角色指派、綁定角色」的列，以軟刪除處理；已被使用的同名群組一律不動。
-- fresh 與 update 都會執行，可重複執行。

UPDATE organizational_units u
   SET is_deleted = true,
       deleted_at = (now() AT TIME ZONE 'UTC'),
       updated_at = (now() AT TIME ZONE 'UTC')
 WHERE u.unit_type = 'GROUP'
   AND u.code = 'EXT_PARTNER'
   AND u.name = '外部合作夥伴'
   AND u.parent_secure_code IS NULL
   AND u.is_system_unit = false
   AND u.is_deleted = false
   AND NOT EXISTS (
       SELECT 1 FROM organizational_units c
        WHERE c.parent_secure_code = u.secure_code AND c.is_deleted = false)
   AND NOT EXISTS (
       SELECT 1 FROM user_unit_memberships m
        WHERE m.unit_secure_code = u.secure_code AND m.is_deleted = false)
   AND NOT EXISTS (
       SELECT 1 FROM user_role_assignments a
        WHERE a.unit_secure_code = u.secure_code AND a.is_deleted = false)
   AND NOT EXISTS (
       SELECT 1 FROM roles r
        WHERE r.bound_unit_secure_code = u.secure_code AND r.is_deleted = false);
