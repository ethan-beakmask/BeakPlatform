-- 054: menu_items 新增 is_user_created 欄位
-- 用於區分預設選單（禁止刪除）與用戶自建選單（可刪除）
ALTER TABLE menu_items ADD COLUMN IF NOT EXISTS is_user_created BOOLEAN NOT NULL DEFAULT false;
