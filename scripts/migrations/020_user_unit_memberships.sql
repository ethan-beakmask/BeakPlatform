-- Migration: 020_user_unit_memberships
-- Description: 建立用戶-組織單位成員關係表（支援跨部門/社群多重歸屬）
-- Date: 2026-01-02

-- ============================================
-- 用戶-組織單位成員關係表
-- ============================================
-- 用於記錄：
-- 1. 部門：實線(SOLID)/虛線(DOTTED) 匯報關係
-- 2. 社群：成員(MEMBER) 關係
-- ============================================

CREATE TABLE IF NOT EXISTS user_unit_memberships (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    
    -- 租戶隔離
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code),
    
    -- 關係雙方
    user_secure_code VARCHAR(32) NOT NULL REFERENCES users(secure_code),
    unit_secure_code VARCHAR(32) NOT NULL REFERENCES organizational_units(secure_code),
    
    -- 成員類型
    -- SOLID: 實線匯報（正式歸屬部門）
    -- DOTTED: 虛線匯報（跨部門支援）
    -- MEMBER: 社群成員
    membership_type VARCHAR(20) NOT NULL DEFAULT 'MEMBER',
    
    -- 角色類型（可選）
    -- MANAGER: 主管/團長
    -- DEPUTY: 副主管/副團長
    -- PROXY1: 代理人(一)
    -- PROXY2: 代理人(二)
    -- MEMBER: 一般成員/團員
    -- NULL: 無特定角色
    role_type VARCHAR(20) DEFAULT NULL,
    
    -- 生效期間（借調/臨時支援用）
    start_date DATE DEFAULT CURRENT_DATE,
    end_date DATE DEFAULT NULL,
    
    -- 備註
    notes TEXT DEFAULT NULL,
    
    -- 標準欄位
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    
    -- 唯一約束：同一用戶在同一單位只能有一種關係類型
    CONSTRAINT uq_user_unit_membership UNIQUE (user_secure_code, unit_secure_code, membership_type)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_uum_org ON user_unit_memberships(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_uum_user ON user_unit_memberships(user_secure_code);
CREATE INDEX IF NOT EXISTS idx_uum_unit ON user_unit_memberships(unit_secure_code);
CREATE INDEX IF NOT EXISTS idx_uum_type ON user_unit_memberships(membership_type);
CREATE INDEX IF NOT EXISTS idx_uum_active ON user_unit_memberships(is_deleted, end_date);

-- 欄位註解
COMMENT ON TABLE user_unit_memberships IS '用戶-組織單位成員關係表';
COMMENT ON COLUMN user_unit_memberships.membership_type IS '成員類型: SOLID=實線匯報, DOTTED=虛線匯報, MEMBER=社群成員';
COMMENT ON COLUMN user_unit_memberships.role_type IS '角色類型: MANAGER/DEPUTY/PROXY1/PROXY2/MEMBER';
COMMENT ON COLUMN user_unit_memberships.start_date IS '生效日期';
COMMENT ON COLUMN user_unit_memberships.end_date IS '結束日期（NULL=永久）';
