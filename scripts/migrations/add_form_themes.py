#!/usr/bin/env python3
"""
Migration: 新增表單風格主題管理表 fw_form_themes
並 seed 內建主題 (security)

用法:
    python3 scripts/migrations/add_form_themes.py          # 執行遷移
    python3 scripts/migrations/add_form_themes.py --check   # 只檢查
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from app import create_app, db


def run_migration(check_only=False):
    app = create_app()
    with app.app_context():
        # Step 1: 建立表
        result = db.session.execute(db.text(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'fw_form_themes'"
        )).fetchone()

        if result:
            print('  [SKIP] fw_form_themes 表已存在')
        elif check_only:
            print('  [TODO] 建立 fw_form_themes 表')
        else:
            print('  [RUN] 建立 fw_form_themes 表')
            db.session.execute(db.text("""
                CREATE TABLE fw_form_themes (
                    id SERIAL PRIMARY KEY,
                    secure_code VARCHAR(32) UNIQUE NOT NULL,
                    org_secure_code VARCHAR(32),
                    name VARCHAR(100) NOT NULL,
                    display_name VARCHAR(200) NOT NULL,
                    description VARCHAR(500),
                    css_content TEXT,
                    is_system BOOLEAN DEFAULT FALSE NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE NOT NULL,
                    sort_order INTEGER DEFAULT 0,
                    is_deleted BOOLEAN DEFAULT FALSE NOT NULL,
                    deleted_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
                );
                CREATE INDEX idx_fw_form_themes_org ON fw_form_themes(org_secure_code);
                CREATE INDEX idx_fw_form_themes_name ON fw_form_themes(name);
                CREATE INDEX idx_fw_form_themes_active ON fw_form_themes(is_active);
                CREATE INDEX idx_fw_form_themes_deleted ON fw_form_themes(is_deleted);
            """))
            db.session.commit()
            print('  [OK] fw_form_themes 表建立完成')

        # Step 2: Seed 內建主題
        existing = db.session.execute(db.text(
            "SELECT name FROM fw_form_themes WHERE is_system = TRUE AND is_deleted = FALSE"
        )).fetchall()
        existing_names = {r[0] for r in existing}

        # 讀取 security 主題 CSS
        css_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'backend', 'app', 'static', 'css',
            'formio-theme-security.css'
        )
        security_css = ''
        if os.path.exists(css_path):
            with open(css_path, 'r', encoding='utf-8') as f:
                security_css = f.read()
            print(f'  [INFO] 讀取 security CSS: {len(security_css)} bytes')
        else:
            print(f'  [WARN] security CSS 不存在: {css_path}')

        seeds = [
            {
                'name': 'security',
                'display_name': '正式扁平',
                'description': '嚴肅工具風格：扁平、高資訊密度、間距緊湊、標籤在左',
                'css_content': security_css,
                'sort_order': 10,
            },
        ]

        for seed in seeds:
            if seed['name'] in existing_names:
                if check_only:
                    print(f'  [SKIP] 主題 {seed["name"]} 已存在')
                else:
                    # 更新 CSS 內容
                    db.session.execute(db.text(
                        "UPDATE fw_form_themes SET css_content = :css, display_name = :dn, "
                        "description = :desc, updated_at = CURRENT_TIMESTAMP "
                        "WHERE name = :name AND is_system = TRUE"
                    ), {
                        'css': seed['css_content'],
                        'dn': seed['display_name'],
                        'desc': seed['description'],
                        'name': seed['name'],
                    })
                    db.session.commit()
                    print(f'  [UPDATE] 主題 {seed["name"]} CSS 已更新')
            elif check_only:
                print(f'  [TODO] Seed 主題 {seed["name"]}')
            else:
                import secrets as sec
                db.session.execute(db.text(
                    "INSERT INTO fw_form_themes "
                    "(secure_code, name, display_name, description, css_content, "
                    " is_system, is_active, sort_order) "
                    "VALUES (:sc, :name, :dn, :desc, :css, TRUE, TRUE, :so)"
                ), {
                    'sc': sec.token_urlsafe(16),
                    'name': seed['name'],
                    'dn': seed['display_name'],
                    'desc': seed['description'],
                    'css': seed['css_content'],
                    'so': seed['sort_order'],
                })
                db.session.commit()
                print(f'  [OK] 主題 {seed["name"]} 已 seed')

        print('Migration completed.')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='新增表單風格主題管理表')
    parser.add_argument('--check', action='store_true', help='只檢查不執行')
    args = parser.parse_args()
    run_migration(check_only=args.check)
