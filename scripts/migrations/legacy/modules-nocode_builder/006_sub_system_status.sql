-- Migration 006: 子系統狀態機 + 開發者名單 + 佈局模式
-- Phase 1 of Web Builder Studio

-- 新增 status 欄位 (draft/published)
ALTER TABLE dc_sub_systems
    ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'draft';

-- 新增 developers 欄位 (開發者 user_secure_code 陣列)
ALTER TABLE dc_sub_systems
    ADD COLUMN IF NOT EXISTS developers JSONB DEFAULT '[]'::jsonb;

-- 新增 layout_mode 欄位 (grid/free)
ALTER TABLE dc_sub_systems
    ADD COLUMN IF NOT EXISTS layout_mode VARCHAR(20) NOT NULL DEFAULT 'grid';

-- 狀態索引
CREATE INDEX IF NOT EXISTS idx_dc_sub_systems_status
    ON dc_sub_systems(status);

-- 權限 GRANT
GRANT SELECT, INSERT, UPDATE, DELETE ON dc_sub_systems TO beakplatform;
