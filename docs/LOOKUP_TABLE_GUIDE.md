# Lookup Table 開發速查

## 架構概述

| 表 | 用途 | org_secure_code |
|----|------|-----------------|
| `lookup_categories` | 類別定義 | NULL=系統級, 有值=企業級 |
| `lookup_items` | 選項資料 | 同上 |

- 繼承 BaseModel（非 TenantBaseModel），因 org 可為 NULL
- RLS 已啟用：一般用戶只能看到系統級 + 自己企業的資料
- 系統級操作需先 `SET LOCAL app.is_system_admin = 'true'`

---

## SQL 操作

### 查詢

```sql
-- 列出所有系統級 category
SELECT code, name, is_system, is_hierarchical
FROM lookup_categories
WHERE org_secure_code IS NULL AND is_deleted = FALSE;

-- 查詢某 category 下的所有選項
SELECT code, label, value, sort_order
FROM lookup_items
WHERE category_code = 'INSTALLED_MODULES'
  AND is_deleted = FALSE
  AND is_active = TRUE
ORDER BY sort_order, code;

-- 查詢某企業可見的所有選項（系統級 + 企業級合併）
SELECT code, label, value, org_secure_code
FROM lookup_items
WHERE category_code = 'GENDER'
  AND (org_secure_code IS NULL OR org_secure_code = 'abc123')
  AND is_deleted = FALSE AND is_active = TRUE
ORDER BY sort_order;
```

### 新增 Category

```sql
-- 系統級 category（全平台共用）
INSERT INTO lookup_categories (secure_code, code, name, name_i18n, is_system, is_deleted, created_at, updated_at)
VALUES (
    'sc_' || substr(md5(random()::text), 1, 28),
    'GENDER',
    '性別',
    '{"en": "Gender"}',
    TRUE,
    FALSE,
    NOW(), NOW()
);

-- 企業級 category
INSERT INTO lookup_categories (secure_code, org_secure_code, code, name, is_system, is_deleted, created_at, updated_at)
VALUES (
    'sc_' || substr(md5(random()::text), 1, 28),
    'ORG_SECURE_CODE_HERE',
    'CUSTOM_LIST',
    '自訂清單',
    FALSE,
    FALSE,
    NOW(), NOW()
);
```

### 新增 Item

```sql
-- 基本選項
INSERT INTO lookup_items (secure_code, category_code, code, label, label_i18n, sort_order, is_active, is_deleted, created_at, updated_at)
VALUES (
    'sc_' || substr(md5(random()::text), 1, 28),
    'GENDER',
    'MALE',
    '男',
    '{"en": "Male"}',
    1,
    TRUE, FALSE,
    NOW(), NOW()
);

-- 帶附加資料的選項
INSERT INTO lookup_items (secure_code, category_code, code, label, value, sort_order, is_active, is_deleted, created_at, updated_at)
VALUES (
    'sc_' || substr(md5(random()::text), 1, 28),
    'INSTALLED_MODULES',
    'data_crud',
    '資料表工具',
    '{"version": "1.0.0", "description": "...", "enabled": true}',
    0,
    TRUE, FALSE,
    NOW(), NOW()
);

-- 階層選項（parent_code）
INSERT INTO lookup_items (secure_code, category_code, code, label, parent_code, sort_order, is_active, is_deleted, created_at, updated_at)
VALUES (
    'sc_' || substr(md5(random()::text), 1, 28),
    'REGION',
    'TAIPEI_CITY',
    '台北市',
    'NORTH',       -- 指向同 category 的 code='NORTH' 項目
    1,
    TRUE, FALSE,
    NOW(), NOW()
);
```

### JSONB 欄位操作

```sql
-- 讀取 value JSONB 中的特定欄位
SELECT code, label, value->>'version' AS version, value->>'enabled' AS enabled
FROM lookup_items
WHERE category_code = 'INSTALLED_MODULES' AND is_deleted = FALSE;

-- 用 JSONB 條件篩選
SELECT code, label
FROM lookup_items
WHERE category_code = 'INSTALLED_MODULES'
  AND (value->>'enabled')::boolean = TRUE
  AND is_deleted = FALSE;

-- 更新 JSONB 中的特定 key
UPDATE lookup_items
SET value = jsonb_set(COALESCE(value, '{}'), '{version}', '"2.0.0"'),
    updated_at = NOW()
WHERE category_code = 'INSTALLED_MODULES' AND code = 'data_crud';

-- 新增 JSONB key
UPDATE lookup_items
SET value = COALESCE(value, '{}') || '{"new_key": "new_value"}',
    updated_at = NOW()
WHERE secure_code = 'xxx';

-- 刪除 JSONB key
UPDATE lookup_items
SET value = value - 'old_key',
    updated_at = NOW()
WHERE secure_code = 'xxx';

-- 查詢 label_i18n 多語系
SELECT code,
       label AS "zh-TW",
       label_i18n->>'en' AS "en",
       label_i18n->>'ja' AS "ja"
FROM lookup_items
WHERE category_code = 'GENDER' AND is_deleted = FALSE;
```

### 更新與軟刪除

```sql
-- 更新選項標籤
UPDATE lookup_items
SET label = '新標籤', updated_at = NOW()
WHERE category_code = 'GENDER' AND code = 'MALE' AND is_deleted = FALSE;

-- 停用選項（保留資料但不顯示）
UPDATE lookup_items
SET is_active = FALSE, updated_at = NOW()
WHERE secure_code = 'xxx';

-- 軟刪除
UPDATE lookup_items
SET is_deleted = TRUE, deleted_at = NOW()
WHERE secure_code = 'xxx';
```

---

## Python Service 操作

```python
from backend.app.services.lookup_service import LookupService

# 讀取選項（帶快取）
items = LookupService.get_items('GENDER')
items = LookupService.get_items('GENDER', org_secure_code='abc123')  # 含企業級

# 讀取 category
cat = LookupService.get_category('INSTALLED_MODULES')

# 列出所有 category
cats = LookupService.get_categories()
cats = LookupService.get_categories(org_secure_code='abc123')

# 建立 category
LookupService.create_category(
    code='RELIGION',
    name='宗教',
    name_i18n={'en': 'Religion'},
    is_system=True,
)
db.session.commit()

# 建立選項
LookupService.create_item(
    category_code='RELIGION',
    code='BUDDHISM',
    label='佛教',
    label_i18n={'en': 'Buddhism'},
    sort_order=1,
)
db.session.commit()

# 更新選項
LookupService.update_item('SECURE_CODE', label='新名稱', sort_order=2)
db.session.commit()

# 軟刪除
LookupService.delete_item('SECURE_CODE')
db.session.commit()
```

---

## 唯一約束

| 表 | 約束 | 說明 |
|----|------|------|
| lookup_categories | `(COALESCE(org, '__SYSTEM__'), code)` | 同一 org 內 code 唯一 |
| lookup_items | `(COALESCE(org, '__SYSTEM__'), category_code, code)` | 同一 org + category 內 code 唯一 |

約束僅對 `is_deleted = FALSE` 的記錄生效（partial unique index）。

---

## 現有系統級 Category

| code | 名稱 | 維護方式 |
|------|------|----------|
| INSTALLED_MODULES | 已安裝模組 | `LookupService.sync_installed_modules()` 自動同步 |
