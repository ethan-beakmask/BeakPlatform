#!/usr/bin/env python3
"""
041: 建立平台說明選單
- platform_help (根, header, 所有 user_type 可見)
- platform_help.system_admin (子, route, SYSTEM_ADMIN only)
- platform_help.org_admin (子, route, ORG_ADMIN only)
- platform_help.employee (子, route, EMPLOYEE only)
- platform_help.external (子, route, EXTERNAL only)
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from app import create_app, db
from app.services.menu_service import MenuService
from app.models.menu_item import MenuItem
from app.constants import SYSTEM_ORG_CODE


def run():
    app = create_app()
    with app.app_context():
        existing = MenuItem.query.filter_by(code='platform_help', is_deleted=False).first()
        if existing:
            print('platform_help menu already exists, skipping.')
            return

        help_root = MenuService.create_menu_item(
            org_secure_code=SYSTEM_ORG_CODE,
            code='platform_help',
            title='說明',
            link_type='header',
            link_target=None,
            icon='ri-question-line',
            display_order=18,
            allowed_user_types=['SYSTEM_ADMIN', 'ORG_ADMIN', 'EMPLOYEE', 'EXTERNAL'],
            is_expanded=False,
        )
        help_root.is_shared = True
        db.session.flush()

        children = [
            ('platform_help.system_admin', '系統管理員說明', 'SYSTEM_ADMIN', 1),
            ('platform_help.org_admin', '企業管理員說明', 'ORG_ADMIN', 2),
            ('platform_help.employee', '員工說明', 'EMPLOYEE', 3),
            ('platform_help.external', '外部廠商說明', 'EXTERNAL', 4),
        ]

        for code, title, user_type, order in children:
            child = MenuService.create_menu_item(
                org_secure_code=SYSTEM_ORG_CODE,
                code=code,
                title=title,
                link_type='route',
                link_target='platform_help.index',
                parent_secure_code=help_root.secure_code,
                icon=None,
                display_order=order,
                allowed_user_types=[user_type],
            )
            child.is_shared = True

        db.session.commit()
        print('Platform help menu created.')


if __name__ == '__main__':
    run()
