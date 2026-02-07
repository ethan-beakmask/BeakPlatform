-- =============================================================================
-- BeakMask Menu System Migration
-- Version: 001
-- Description: 動態選單系統、模組、頁面
-- =============================================================================

-- =============================================================================
-- 1. MODULES TABLE (模組)
-- =============================================================================
CREATE TABLE IF NOT EXISTS modules (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) UNIQUE NOT NULL,
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code),

    code VARCHAR(50) NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    icon VARCHAR(10),

    is_system_module BOOLEAN DEFAULT FALSE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    display_order INTEGER DEFAULT 0 NOT NULL,
    settings TEXT,

    is_deleted BOOLEAN DEFAULT FALSE NOT NULL,
    deleted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,

    CONSTRAINT uq_modules_org_code UNIQUE (org_secure_code, code)
);

CREATE INDEX IF NOT EXISTS idx_modules_secure_code ON modules(secure_code);
CREATE INDEX IF NOT EXISTS idx_modules_org ON modules(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_modules_is_deleted ON modules(is_deleted);

-- Enable RLS
ALTER TABLE modules ENABLE ROW LEVEL SECURITY;

CREATE POLICY modules_org_isolation ON modules
    FOR ALL
    USING (
        current_setting('app.is_system_admin', true) = 'true'
        OR
        org_secure_code = current_setting('app.current_org', true)
    );

-- =============================================================================
-- 2. MENU_ITEMS TABLE (選單項目 - 樹狀結構)
-- =============================================================================
CREATE TABLE IF NOT EXISTS menu_items (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) UNIQUE NOT NULL,
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code),

    -- 關聯
    module_secure_code VARCHAR(32) REFERENCES modules(secure_code),
    parent_secure_code VARCHAR(32) REFERENCES menu_items(secure_code),

    -- 基本資訊
    code VARCHAR(50) NOT NULL,
    title VARCHAR(100) NOT NULL,
    icon VARCHAR(10),

    -- 連結設定
    -- link_type: 'page', 'url', 'route', 'divider', 'header'
    link_type VARCHAR(20) DEFAULT 'route' NOT NULL,
    link_target VARCHAR(255),
    open_in_new_tab BOOLEAN DEFAULT FALSE NOT NULL,

    -- 顯示控制
    display_order INTEGER DEFAULT 0 NOT NULL,
    depth INTEGER DEFAULT 0 NOT NULL,
    is_expanded BOOLEAN DEFAULT FALSE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,

    -- Phase 1 簡化權限
    -- 0 = system_admin, 1 = org_admin, 2 = authenticated
    required_level INTEGER DEFAULT 2 NOT NULL,

    is_deleted BOOLEAN DEFAULT FALSE NOT NULL,
    deleted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,

    CONSTRAINT uq_menu_items_org_code UNIQUE (org_secure_code, code)
);

CREATE INDEX IF NOT EXISTS idx_menu_items_secure_code ON menu_items(secure_code);
CREATE INDEX IF NOT EXISTS idx_menu_items_org ON menu_items(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_menu_items_parent ON menu_items(parent_secure_code);
CREATE INDEX IF NOT EXISTS idx_menu_items_module ON menu_items(module_secure_code);
CREATE INDEX IF NOT EXISTS idx_menu_items_order ON menu_items(display_order);
CREATE INDEX IF NOT EXISTS idx_menu_items_is_deleted ON menu_items(is_deleted);

-- Enable RLS
ALTER TABLE menu_items ENABLE ROW LEVEL SECURITY;

CREATE POLICY menu_items_org_isolation ON menu_items
    FOR ALL
    USING (
        current_setting('app.is_system_admin', true) = 'true'
        OR
        org_secure_code = current_setting('app.current_org', true)
    );

-- =============================================================================
-- 3. PAGES TABLE (頁面)
-- =============================================================================
CREATE TABLE IF NOT EXISTS pages (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) UNIQUE NOT NULL,
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code),

    -- 關聯
    module_secure_code VARCHAR(32) REFERENCES modules(secure_code),

    -- 基本資訊
    code VARCHAR(50) NOT NULL,
    title VARCHAR(200) NOT NULL,
    description TEXT,

    -- 頁面類型: 'list', 'detail', 'form', 'dashboard', 'custom'
    page_type VARCHAR(20) DEFAULT 'custom' NOT NULL,

    -- URL 設定
    url_path VARCHAR(255) NOT NULL,
    flask_route VARCHAR(100),

    -- 模板/No-Code 設定
    template TEXT,

    -- Phase 1 簡化權限
    -- 'public', 'authenticated', 'org_admin', 'system_admin'
    required_access VARCHAR(20) DEFAULT 'authenticated' NOT NULL,

    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    settings TEXT,

    is_deleted BOOLEAN DEFAULT FALSE NOT NULL,
    deleted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,

    CONSTRAINT uq_pages_org_code UNIQUE (org_secure_code, code),
    CONSTRAINT uq_pages_org_url UNIQUE (org_secure_code, url_path)
);

CREATE INDEX IF NOT EXISTS idx_pages_secure_code ON pages(secure_code);
CREATE INDEX IF NOT EXISTS idx_pages_org ON pages(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_pages_module ON pages(module_secure_code);
CREATE INDEX IF NOT EXISTS idx_pages_url ON pages(url_path);
CREATE INDEX IF NOT EXISTS idx_pages_is_deleted ON pages(is_deleted);

-- Enable RLS
ALTER TABLE pages ENABLE ROW LEVEL SECURITY;

CREATE POLICY pages_org_isolation ON pages
    FOR ALL
    USING (
        current_setting('app.is_system_admin', true) = 'true'
        OR
        org_secure_code = current_setting('app.current_org', true)
    );

-- =============================================================================
-- 4. TRIGGERS
-- =============================================================================
CREATE TRIGGER update_modules_updated_at
    BEFORE UPDATE ON modules
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_menu_items_updated_at
    BEFORE UPDATE ON menu_items
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_pages_updated_at
    BEFORE UPDATE ON pages
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- 5. GRANT PERMISSIONS
-- =============================================================================
GRANT SELECT, INSERT, UPDATE, DELETE ON modules TO beakmask_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON menu_items TO beakmask_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON pages TO beakmask_app;
GRANT USAGE, SELECT ON SEQUENCE modules_id_seq TO beakmask_app;
GRANT USAGE, SELECT ON SEQUENCE menu_items_id_seq TO beakmask_app;
GRANT USAGE, SELECT ON SEQUENCE pages_id_seq TO beakmask_app;

-- =============================================================================
-- 6. SEED DATA
-- =============================================================================
-- 注意: Seed 資料由 Python 腳本建立，確保 secure_code 使用 token_urlsafe(16)
-- 執行方式: python scripts/seed_data.py
--
-- 不要在此處硬編碼 secure_code！這會造成安全風險（可被猜測）

-- =============================================================================
-- 7. COMMENTS - 資料表註解
-- =============================================================================
COMMENT ON TABLE modules IS '功能模組 - No-Code Builder 的基本單位，一個模組包含多個選單和頁面';
COMMENT ON TABLE menu_items IS '動態選單項目 - 樹狀結構的選單系統，支援多層巢狀';
COMMENT ON TABLE pages IS '頁面 - No-Code Builder 生成或自訂的頁面定義';

-- =============================================================================
-- modules 欄位註解
-- =============================================================================
COMMENT ON COLUMN modules.id IS '內部自增主鍵，僅供資料庫內部使用';
COMMENT ON COLUMN modules.secure_code IS '外部識別碼 (32 字元)，對外暴露使用，取代自增 ID';
COMMENT ON COLUMN modules.org_secure_code IS '所屬企業識別碼，多租戶隔離欄位';
COMMENT ON COLUMN modules.code IS '模組代碼，同企業內唯一，如 system, hr, sales';
COMMENT ON COLUMN modules.name IS '模組名稱，如「系統管理」「人力資源」';
COMMENT ON COLUMN modules.description IS '模組描述，說明此模組的功能範圍';
COMMENT ON COLUMN modules.icon IS '模組圖示 (emoji 或圖示代碼)';
COMMENT ON COLUMN modules.is_system_module IS '是否為系統內建模組，TRUE 時不可刪除';
COMMENT ON COLUMN modules.is_active IS '是否啟用，FALSE 時模組下所有功能停用';
COMMENT ON COLUMN modules.display_order IS '顯示排序順序';
COMMENT ON COLUMN modules.settings IS '模組設定 (JSON 格式)，儲存模組特定配置';
COMMENT ON COLUMN modules.is_deleted IS '軟刪除標記';
COMMENT ON COLUMN modules.deleted_at IS '軟刪除時間戳';
COMMENT ON COLUMN modules.created_at IS '建立時間';
COMMENT ON COLUMN modules.updated_at IS '最後更新時間';

-- =============================================================================
-- menu_items 欄位註解
-- =============================================================================
COMMENT ON COLUMN menu_items.id IS '內部自增主鍵，僅供資料庫內部使用';
COMMENT ON COLUMN menu_items.secure_code IS '外部識別碼 (32 字元)，對外暴露使用';
COMMENT ON COLUMN menu_items.org_secure_code IS '所屬企業識別碼，多租戶隔離欄位';
COMMENT ON COLUMN menu_items.module_secure_code IS '所屬模組識別碼';
COMMENT ON COLUMN menu_items.parent_secure_code IS '上層選單識別碼，用於建立樹狀結構';
COMMENT ON COLUMN menu_items.code IS '選單代碼，同企業內唯一';
COMMENT ON COLUMN menu_items.title IS '選單標題，顯示在 UI 上';
COMMENT ON COLUMN menu_items.icon IS '選單圖示 (emoji 或圖示代碼)';
COMMENT ON COLUMN menu_items.link_type IS '連結類型: page=頁面, url=外部網址, route=Flask路由, divider=分隔線, header=標題';
COMMENT ON COLUMN menu_items.link_target IS '連結目標，依 link_type 不同而異';
COMMENT ON COLUMN menu_items.open_in_new_tab IS '是否在新分頁開啟';
COMMENT ON COLUMN menu_items.display_order IS '顯示排序順序';
COMMENT ON COLUMN menu_items.depth IS '選單深度，0 為頂層';
COMMENT ON COLUMN menu_items.is_expanded IS '預設是否展開子選單';
COMMENT ON COLUMN menu_items.is_active IS '是否啟用';
COMMENT ON COLUMN menu_items.required_level IS '(已棄用) 改用 menu_permissions 交叉表';
COMMENT ON COLUMN menu_items.is_deleted IS '軟刪除標記';
COMMENT ON COLUMN menu_items.deleted_at IS '軟刪除時間戳';
COMMENT ON COLUMN menu_items.created_at IS '建立時間';
COMMENT ON COLUMN menu_items.updated_at IS '最後更新時間';

-- =============================================================================
-- pages 欄位註解
-- =============================================================================
COMMENT ON COLUMN pages.id IS '內部自增主鍵，僅供資料庫內部使用';
COMMENT ON COLUMN pages.secure_code IS '外部識別碼 (32 字元)，對外暴露使用';
COMMENT ON COLUMN pages.org_secure_code IS '所屬企業識別碼，多租戶隔離欄位';
COMMENT ON COLUMN pages.module_secure_code IS '所屬模組識別碼';
COMMENT ON COLUMN pages.code IS '頁面代碼，同企業內唯一';
COMMENT ON COLUMN pages.title IS '頁面標題';
COMMENT ON COLUMN pages.description IS '頁面描述';
COMMENT ON COLUMN pages.page_type IS '頁面類型: list=列表, detail=詳細, form=表單, dashboard=儀表板, custom=自訂';
COMMENT ON COLUMN pages.url_path IS 'URL 路徑，如 /users, /dashboard';
COMMENT ON COLUMN pages.flask_route IS '對應的 Flask 路由名稱';
COMMENT ON COLUMN pages.template IS 'No-Code 模板定義 (JSON 格式)';
COMMENT ON COLUMN pages.required_access IS '存取權限: public=公開, authenticated=需登入, org_admin=企業管理員, system_admin=系統管理員';
COMMENT ON COLUMN pages.is_active IS '是否啟用';
COMMENT ON COLUMN pages.settings IS '頁面設定 (JSON 格式)';
COMMENT ON COLUMN pages.is_deleted IS '軟刪除標記';
COMMENT ON COLUMN pages.deleted_at IS '軟刪除時間戳';
COMMENT ON COLUMN pages.created_at IS '建立時間';
COMMENT ON COLUMN pages.updated_at IS '最後更新時間';
