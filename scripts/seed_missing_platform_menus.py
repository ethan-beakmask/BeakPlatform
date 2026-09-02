#!/usr/bin/env python3
"""補種缺少的平台選單。"""
import os
import sys

os.environ['SKIP_MODULE_SYNC'] = '1'
os.environ['EXECUTOR_STANDALONE'] = '1'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


USAGE = """用法:
  scripts/seed_missing_platform_menus.py --dry-run
  scripts/seed_missing_platform_menus.py --apply

說明:
  補上 CORE_MENUS 中尚未存在的平台選單。已存在的 code 一律不修改。
  --dry-run 只顯示將補種的選單；--apply 才會寫入資料庫。
"""


def _print_usage():
    print(USAGE)


def _load_dotenv():
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding='utf-8') as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _user_types_for(menu_def):
    from app.defaults.menu_defaults import get_allowed_user_types

    if '_user_types_override' in menu_def:
        return menu_def['_user_types_override']
    return get_allowed_user_types(
        menu_def['required_level'],
        menu_def.get('is_shared', False),
    )


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ('--dry-run', '--apply', '--help', '-h'):
        _print_usage()
        return 0 if len(sys.argv) == 2 and sys.argv[1] in ('--help', '-h') else 1
    if sys.argv[1] in ('--help', '-h'):
        _print_usage()
        return 0

    _load_dotenv()
    from app import create_app, db
    from app.constants import SYSTEM_ORG_CODE
    from app.defaults.menu_defaults import CORE_MENUS
    from app.defaults.platform_menu_defaults import (
        build_menu_item,
        generate_secure_code,
        set_menu_permissions,
    )
    from app.models import MenuItem, MenuRoleRequirement, Organization
    from app.services.menu_service import MenuService

    app = create_app()
    with app.app_context():
        system_org = Organization.query.filter_by(
            secure_code=SYSTEM_ORG_CODE,
            is_deleted=False,
        ).first()
        if not system_org:
            print(f"錯誤: 系統企業 {SYSTEM_ORG_CODE} 不存在")
            return 1

        items = MenuItem.query.filter_by(
            org_secure_code=SYSTEM_ORG_CODE,
            is_deleted=False,
        ).all()
        code_to_item = {item.code: item for item in items}
        missing = [
            menu_def
            for depth in (0, 1)
            for menu_def in CORE_MENUS
            if menu_def.get('depth', 0) == depth and menu_def['code'] not in code_to_item
        ]

        if missing:
            print("將補種選單:")
            for menu_def in missing:
                print(f"  - {menu_def['code']}")
        else:
            print("沒有缺少的平台選單")

        if sys.argv[1] == '--dry-run':
            print("Key2: 將呼叫 seed_all_orgs_role_requirements")
            return 0

        created = []
        for menu_def in missing:
            parent_secure_code = None
            parent_code = menu_def.get('parent_code')
            if parent_code:
                parent = code_to_item.get(parent_code)
                if not parent:
                    print(f"略過 {menu_def['code']}: 找不到父選單 {parent_code}")
                    continue
                parent_secure_code = parent.secure_code

            menu = build_menu_item(
                {**menu_def, 'org_secure_code': SYSTEM_ORG_CODE},
                generate_secure_code(),
                parent_secure_code,
            )
            db.session.add(menu)
            db.session.flush()
            code_to_item[menu.code] = menu
            set_menu_permissions(menu.secure_code, _user_types_for(menu_def))
            created.append(menu.code)

        orgs = Organization.query.filter(Organization.is_deleted == False).all()
        before_counts = {
            org.secure_code: MenuRoleRequirement.query.filter_by(
                org_secure_code=org.secure_code,
                is_deleted=False,
            ).count()
            for org in orgs
        }
        mrr_created = MenuService.seed_all_orgs_role_requirements(code_to_item)
        after_counts = {
            org.secure_code: MenuRoleRequirement.query.filter_by(
                org_secure_code=org.secure_code,
                is_deleted=False,
            ).count()
            for org in orgs
        }
        db.session.commit()

        print(f"已補種 {len(created)} 個選單: {', '.join(created) if created else '無'}")
        print(f"Key2 新增 {mrr_created} 筆")
        for org in orgs:
            delta = after_counts.get(org.secure_code, 0) - before_counts.get(org.secure_code, 0)
            print(f"  - {org.code}: 新增 {delta} 筆 Key2")
    return 0


if __name__ == '__main__':
    sys.exit(main())
