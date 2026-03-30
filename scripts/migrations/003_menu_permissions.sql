-- Migration: 003_menu_permissions
-- Description: 新增 MenuPermission 交叉表，用於定義選單與用戶類型的可見性關係
-- Date: 2024-12-20

-- ============================================================
-- menu_permissions 資料表
-- ============================================================
-- 說明：
-- 定義哪種用戶類型可以看到哪個選單項目
-- 權限是「平行」的，不是繼承的
-- 系統管理員只能看到為其開放的選單，不會自動看到所有選單

CREATE TABLE IF NOT EXISTS menu_permissions (
    id SERIAL PRIMARY KEY,

    -- 安全識別碼 (對外使用)
    secure_code VARCHAR(32) UNIQUE NOT NULL,

    -- 選單項目 (外鍵)
    menu_secure_code VARCHAR(32) NOT NULL REFERENCES menu_items(secure_code) ON DELETE CASCADE,

    -- 用戶類型
    user_type VARCHAR(20) NOT NULL,

    -- 額外條件 (JSON，預留未來擴充)
    conditions TEXT,

    -- 軟刪除欄位
    is_deleted BOOLEAN DEFAULT FALSE NOT NULL,
    deleted_at TIMESTAMP,

    -- 審計欄位
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,

    -- 唯一約束：同一選單+同一用戶類型只能有一筆
    CONSTRAINT unique_menu_user_type UNIQUE (menu_secure_code, user_type)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_menu_permissions_menu ON menu_permissions(menu_secure_code);
CREATE INDEX IF NOT EXISTS idx_menu_permissions_user_type ON menu_permissions(user_type);
CREATE INDEX IF NOT EXISTS idx_menu_permissions_not_deleted ON menu_permissions(is_deleted) WHERE is_deleted = FALSE;

-- user_type 檢查約束
ALTER TABLE menu_permissions
ADD CONSTRAINT chk_user_type
CHECK (user_type IN ('SYSTEM_ADMIN', 'ORG_ADMIN', 'EMPLOYEE', 'EXTERNAL'));

-- ============================================================
-- SEED DATA
-- ============================================================
-- 注意: Seed 資料現在由 Python 腳本建立，確保 secure_code 使用 token_urlsafe(16) 生成
-- 執行方式: python scripts/seed_data.py
--
-- 不要在此處使用 MD5 截斷生成 secure_code！
-- 正確做法是透過 Python Model 的 generate_secure_code() 自動生成

-- ============================================================
-- 資料表註解
-- ============================================================
COMMENT ON TABLE menu_permissions IS '選單權限交叉表 - 定義用戶類型與選單的可見性，權限是平行的不是繼承的';

-- ============================================================
-- menu_permissions 欄位註解
-- ============================================================
COMMENT ON COLUMN menu_permissions.id IS '內部自增主鍵，僅供資料庫內部使用';
COMMENT ON COLUMN menu_permissions.secure_code IS '外部識別碼 (32 字元)，對外暴露使用';
COMMENT ON COLUMN menu_permissions.menu_secure_code IS '選單項目識別碼，指向 menu_items 表';
COMMENT ON COLUMN menu_permissions.user_type IS '用戶類型: SYSTEM_ADMIN=系統管理員, ORG_ADMIN=企業管理員, EMPLOYEE=企業成員, EXTERNAL=外部廠商。平行權限，非繼承';
COMMENT ON COLUMN menu_permissions.conditions IS '額外條件 (JSON 格式)，預留擴充，如特定角色、特定部門等細粒度控制';
COMMENT ON COLUMN menu_permissions.is_deleted IS '軟刪除標記';
COMMENT ON COLUMN menu_permissions.deleted_at IS '軟刪除時間戳';
COMMENT ON COLUMN menu_permissions.created_at IS '建立時間';
COMMENT ON COLUMN menu_permissions.updated_at IS '最後更新時間';
