-- BeakPlatform: 選單出廠預設值表
-- 用途: 系統管理員儲存選單快照，供重置功能使用
-- 建立日期: 2026-04-01

CREATE TABLE IF NOT EXISTS menu_defaults (
    id              SERIAL PRIMARY KEY,
    code            VARCHAR(50)  NOT NULL UNIQUE,
    title           VARCHAR(100) NOT NULL,
    title_i18n      JSONB        DEFAULT '{}',
    icon            VARCHAR(50),
    link_type       VARCHAR(20)  NOT NULL DEFAULT 'route',
    link_target     VARCHAR(255),
    display_order   INTEGER      NOT NULL DEFAULT 0,
    depth           INTEGER      NOT NULL DEFAULT 0,
    parent_code     VARCHAR(50),
    is_expanded     BOOLEAN      NOT NULL DEFAULT false,
    is_shared       BOOLEAN      NOT NULL DEFAULT false,
    required_permission VARCHAR(50),
    user_types      JSONB        NOT NULL DEFAULT '[]',
    role_codes      JSONB        NOT NULL DEFAULT '[]',
    saved_by        VARCHAR(100) NOT NULL,
    saved_at        TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_menu_defaults_code ON menu_defaults (code);

COMMENT ON TABLE menu_defaults IS '選單出廠預設值 - 系統管理員儲存的選單快照';
COMMENT ON COLUMN menu_defaults.user_types IS 'Key1: MenuPermission user_type 列表 (JSONB array)';
COMMENT ON COLUMN menu_defaults.role_codes IS 'Key2: MenuRoleRequirement role code 列表 (JSONB array)';
