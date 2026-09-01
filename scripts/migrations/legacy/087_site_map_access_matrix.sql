-- 087: Site Map portal access matrix
-- 日期: 2026-07-28
-- 用途: 讓 Site Map 節點可宣告 Portal 准入(群組×階級)，僅新增欄位不回填資料。

BEGIN;

ALTER TABLE dc_site_map_nodes
    ADD COLUMN IF NOT EXISTS access_matrix JSONB DEFAULT NULL;

COMMENT ON COLUMN dc_site_map_nodes.access_matrix IS
    'Portal 准入(群組×階級): {"read":{"groups":null|[codes],"min_level":code}}; NULL=未設定';

COMMIT;
