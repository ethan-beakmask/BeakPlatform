-- 134_os_file_write_newline_smart.sql
--
-- OsFileWrite 新增 newline_smart 設定，讓預設追加行為接在上一筆後另起新行，
-- 避免 newline_after 預設值在下一次寫入前被截尾邏輯清掉後造成內容黏行。
--
-- 只更新節點定義的 config_schema；既有流程圖未帶 key 時由後端與面板預設視為 true。
--
-- 冪等：jsonb || 可重複合併相同 schema，WHERE 條件讓已存在 newline_smart 時重跑為 0 筆。
BEGIN;

UPDATE workflow_node_definitions
SET config_schema = config_schema || '{"newline_smart": "boolean"}'::jsonb
WHERE node_type = 'OsFileWrite'
  AND (config_schema IS NULL OR NOT config_schema ? 'newline_smart');

COMMIT;
