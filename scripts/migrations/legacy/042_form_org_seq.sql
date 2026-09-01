-- 042: 表單三層編號架構 - 新增企業表單流水號欄位
-- L1: secure_code（系統層，已存在）
-- L2: org_form_seq（企業層，本次新增）
-- L3: serial_number（顯示層，已存在，改由萬用編號系統產生）

-- 1. fw_form_instances 加企業流水號欄位
ALTER TABLE fw_form_instances
    ADD COLUMN IF NOT EXISTS org_form_seq INTEGER;

COMMENT ON COLUMN fw_form_instances.org_form_seq IS '企業內表單流水號（L2），由萬用編號系統的 counter 產生';

-- 2. 複合唯一約束（同企業+同流水號不重複）
-- 使用 partial index：只約束有值的紀錄（舊資料 NULL 不受影響）
CREATE UNIQUE INDEX IF NOT EXISTS uq_form_org_seq
    ON fw_form_instances(org_secure_code, org_form_seq)
    WHERE org_form_seq IS NOT NULL;

-- 3. 為既有企業建立預設表單編號規則（prefix + 年月 + 序號）
-- 注意：只為尚未有 FORM 預設規則的企業建立
INSERT INTO user_numbering_rules (
    secure_code, org_secure_code, name, description,
    elements, usage_scope, default_for, is_active,
    created_at, updated_at, is_deleted
)
SELECT
    encode(gen_random_bytes(16), 'hex'),
    o.secure_code,
    '預設表單編號',
    '前綴 + 年月 + 5 位序號（每月重置）',
    jsonb_build_object(
        'total_length', 0,
        'components', jsonb_build_array(
            jsonb_build_object('type', 'prefix', 'order', 1, 'values',
                jsonb_build_array(upper(left(o.code, 3)) || '-')),
            jsonb_build_object('type', 'year', 'order', 2, 'format', 'yy'),
            jsonb_build_object('type', 'month', 'order', 3, 'format', 'mm'),
            jsonb_build_object('type', 'prefix', 'order', 4, 'values',
                jsonb_build_array('-')),
            jsonb_build_object('type', 'sequence', 'order', 5,
                'start', 1, 'digits', 5, 'reset_period', 'monthly')
        )
    ),
    'INTERNAL_ONLY',
    'FORM',
    true,
    now(),
    now(),
    false
FROM organizations o
WHERE NOT EXISTS (
    SELECT 1 FROM user_numbering_rules r
    WHERE r.org_secure_code = o.secure_code
      AND r.default_for = 'FORM'
      AND r.is_deleted = false
)
AND o.is_deleted = false;
