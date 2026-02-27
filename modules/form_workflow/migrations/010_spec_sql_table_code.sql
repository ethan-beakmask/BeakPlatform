-- 010: 為 fw_form_field_specs 新增 sql_table_code 欄位
-- 用於獨立規格（無表單綁定）的 SQL 表名基礎碼

ALTER TABLE fw_form_field_specs ADD COLUMN IF NOT EXISTS sql_table_code VARCHAR(20);
