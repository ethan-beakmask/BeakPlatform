"""
Migration 066: 內建檔案加密

1. 建立 org_encryption_keys 表 (企業加密金鑰)
2. 擴充 platform_files 表 (加密 metadata 欄位)
3. 將 storage_type='beakseal' 更新為 'encrypted'
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from app import create_app, db

DDL = """
-- 1. 企業加密金鑰表
CREATE TABLE IF NOT EXISTS org_encryption_keys (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code),
    wrapped_key TEXT NOT NULL,
    key_nonce VARCHAR(64) NOT NULL,
    algorithm VARCHAR(32) NOT NULL DEFAULT 'AES-256-GCM',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_oek_org_sc ON org_encryption_keys(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_oek_active ON org_encryption_keys(org_secure_code, is_active) WHERE is_deleted = FALSE;

-- 2. 擴充 platform_files 表
ALTER TABLE platform_files ADD COLUMN IF NOT EXISTS wrapped_dek TEXT;
ALTER TABLE platform_files ADD COLUMN IF NOT EXISTS dek_nonce VARCHAR(64);
ALTER TABLE platform_files ADD COLUMN IF NOT EXISTS file_nonce VARCHAR(64);
ALTER TABLE platform_files ADD COLUMN IF NOT EXISTS encryption_key_sc VARCHAR(32);

-- 3. 清理舊的 beakseal 記錄 (開發環境測試資料)
DELETE FROM platform_files WHERE storage_type = 'beakseal';
"""


def run():
    app = create_app('development')
    with app.app_context():
        db.session.execute(db.text(DDL))
        db.session.commit()
        print("[066] 內建檔案加密 migration 完成")


if __name__ == '__main__':
    run()
