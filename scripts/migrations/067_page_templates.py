"""
Migration 067: 頁面模板表

建立 dc_page_templates 表，支援 NoCode Builder 的模板功能。
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from app import create_app, db

DDL = """
CREATE TABLE IF NOT EXISTS dc_page_templates (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    layout_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    style_config JSONB DEFAULT '{}'::jsonb,
    thumbnail_svg TEXT,
    created_by_sc VARCHAR(32),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dc_page_templates_org ON dc_page_templates(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_dc_page_templates_active ON dc_page_templates(org_secure_code, is_active) WHERE is_deleted = FALSE;
CREATE INDEX IF NOT EXISTS idx_dc_page_templates_creator ON dc_page_templates(created_by_sc);
"""


def run():
    app = create_app()
    with app.app_context():
        db.session.execute(db.text(DDL))
        db.session.commit()
        print('[067] dc_page_templates table created.')


if __name__ == '__main__':
    run()
