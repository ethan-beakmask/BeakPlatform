-- 108: fw_mapping_permissions 新增 role 授權類型
-- 用途：允許表單流程配對填寫權限以角色 code（roles.code）作為授權目標。
ALTER TABLE fw_mapping_permissions DROP CONSTRAINT IF EXISTS fw_mp_valid_grant_type;
ALTER TABLE fw_mapping_permissions ADD CONSTRAINT fw_mp_valid_grant_type
    CHECK (grant_type IN ('department', 'group', 'user', 'role'));
