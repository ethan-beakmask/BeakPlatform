#!/usr/bin/env python3
"""
099 - 合併 platform_help 底下四條過時說明選單（冪等）

調整內容：
  1. 將 platform_help.org_admin 原地改為 platform_help.manual
  2. 補齊 menu_permissions 的 SYSTEM_ADMIN / ORG_ADMIN / EMPLOYEE / EXTERNAL
  3. 補齊每個企業的 ORG_ADMIN / EMPLOYEE / EXTERNAL_USERS 角色需求
  4. 軟刪 platform_help.system_admin / platform_help.employee / platform_help.external
     以及它們的 menu_permissions / menu_role_requirements

使用方式:
    cd /opt/BeakPlatform-dev
    python scripts/migrations/099_merge_platform_help_menu.py
    python scripts/migrations/099_merge_platform_help_menu.py --dry-run
    python scripts/migrations/099_merge_platform_help_menu.py --run
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from sqlalchemy import text

from app import create_app, db
from app.models import MenuItem, Organization, Role
from app.models.menu_permission import MenuPermission
from app.models.menu_role_requirement import MenuRoleRequirement


MIGRATION_ID = '099_merge_platform_help_menu'
SOURCE_CODE = 'platform_help.org_admin'
TARGET_CODE = 'platform_help.manual'
OLD_CODES = [
    'platform_help.system_admin',
    'platform_help.employee',
    'platform_help.external',
]
TARGET_USER_TYPES = ['SYSTEM_ADMIN', 'ORG_ADMIN', 'EMPLOYEE', 'EXTERNAL']
TARGET_ROLE_CODES = ['ORG_ADMIN', 'EMPLOYEE', 'EXTERNAL_USERS']


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _restore_or_add_permission(menu_sc: str, user_type: str, dry_run: bool) -> str:
    existing = MenuPermission.query.filter_by(
        menu_secure_code=menu_sc,
        user_type=user_type,
    ).first()
    if existing and not existing.is_deleted:
        return 'skip'
    if existing:
        if not dry_run:
            existing.is_deleted = False
            existing.deleted_at = None
            existing.updated_at = _now()
        return 'restore'
    if not dry_run:
        db.session.add(MenuPermission(
            menu_secure_code=menu_sc,
            user_type=user_type,
        ))
    return 'add'


def _restore_or_add_role_requirement(
    menu_sc: str,
    org_sc: str,
    role_sc: str,
    dry_run: bool,
) -> str:
    existing = MenuRoleRequirement.query.filter_by(
        menu_secure_code=menu_sc,
        role_secure_code=role_sc,
        org_secure_code=org_sc,
    ).first()
    if existing and not existing.is_deleted:
        return 'skip'
    if existing:
        if not dry_run:
            existing.is_deleted = False
            existing.deleted_at = None
            existing.updated_at = _now()
        return 'restore'
    if not dry_run:
        db.session.add(MenuRoleRequirement(
            menu_secure_code=menu_sc,
            role_secure_code=role_sc,
            org_secure_code=org_sc,
        ))
    return 'add'


def _soft_delete_query(model, filters, dry_run: bool) -> int:
    query = model.query.filter(*filters, model.is_deleted == False)  # noqa: E712
    count = query.count()
    if count and not dry_run:
        query.update(
            {
                'is_deleted': True,
                'deleted_at': _now(),
                'updated_at': _now(),
            },
            synchronize_session=False,
        )
    return count


def _active_menu(code: str) -> MenuItem | None:
    return MenuItem.query.filter_by(code=code, is_deleted=False).first()


def run(dry_run: bool = True) -> int:
    app = create_app()
    with app.app_context():
        db.session.execute(text("SET LOCAL app.is_system_admin = 'true'"))

        print(f"[{MIGRATION_ID}] 模式: {'dry-run（未寫入）' if dry_run else 'run（會寫入）'}")

        manual = _active_menu(TARGET_CODE)
        source = _active_menu(SOURCE_CODE)

        if manual is None and source is None:
            print(f"[ERR] 找不到 active {TARGET_CODE} 或 {SOURCE_CODE}，中止")
            db.session.rollback()
            return 1

        renamed_deleted_manual = 0
        if manual is None:
            deleted_manuals = MenuItem.query.filter(
                MenuItem.code == TARGET_CODE,
                MenuItem.is_deleted == True,  # noqa: E712
            ).all()
            for item in deleted_manuals:
                renamed_deleted_manual += 1
                new_code = f'platform_help.manual.old{item.id}'
                print(f"[FIX ] 已刪除舊 manual code 暫存改名: id={item.id} -> {new_code}")
                if not dry_run:
                    item.code = new_code
                    item.updated_at = _now()

            manual = source
            print(
                f"[UPD ] {SOURCE_CODE} -> {TARGET_CODE}, "
                "title=使用者手冊, link_target=platform_help.index"
            )
            if not dry_run:
                manual.code = TARGET_CODE
                manual.title = '使用者手冊'
                manual.title_i18n = {'en': 'User Manual'}
                manual.link_type = 'route'
                manual.link_target = 'platform_help.index'
                manual.display_order = 0
                manual.required_level = 0
                manual.is_active = True
                manual.is_shared = False
                manual.updated_at = _now()
                db.session.flush()
        else:
            print(f"[SKIP] active {TARGET_CODE} 已存在，沿用 sc={manual.secure_code}")
            if not dry_run:
                manual.title = '使用者手冊'
                manual.title_i18n = {'en': 'User Manual'}
                manual.link_type = 'route'
                manual.link_target = 'platform_help.index'
                manual.display_order = 0
                manual.required_level = 0
                manual.is_active = True
                manual.is_shared = False
                manual.updated_at = _now()

        perm_stats = {'add': 0, 'restore': 0, 'skip': 0}
        for user_type in TARGET_USER_TYPES:
            status = _restore_or_add_permission(manual.secure_code, user_type, dry_run)
            perm_stats[status] += 1
            print(f"[{status.upper():4}] menu_permissions: {TARGET_CODE} user_type={user_type}")

        role_stats = {'add': 0, 'restore': 0, 'skip': 0, 'missing_role': 0}
        orgs = Organization.query.filter_by(is_deleted=False).all()
        for org in orgs:
            roles = Role.query.filter(
                Role.org_secure_code == org.secure_code,
                Role.code.in_(TARGET_ROLE_CODES),
                Role.is_deleted == False,  # noqa: E712
            ).all()
            role_by_code = {role.code: role for role in roles}
            for role_code in TARGET_ROLE_CODES:
                role = role_by_code.get(role_code)
                if role is None:
                    role_stats['missing_role'] += 1
                    print(f"[WARN] org={org.secure_code} 找不到 role code={role_code}，略過")
                    continue
                status = _restore_or_add_role_requirement(
                    manual.secure_code,
                    org.secure_code,
                    role.secure_code,
                    dry_run,
                )
                role_stats[status] += 1
                print(
                    f"[{status.upper():4}] menu_role_requirements: "
                    f"org={org.secure_code} role={role_code}"
                )

        duplicate_codes = list(OLD_CODES)
        if source is not None and source.secure_code != manual.secure_code:
            duplicate_codes.append(SOURCE_CODE)

        old_menus = MenuItem.query.filter(
            MenuItem.code.in_(duplicate_codes),
            MenuItem.is_deleted == False,  # noqa: E712
        ).all()
        old_menu_scs = [item.secure_code for item in old_menus]

        deleted_permissions = 0
        deleted_requirements = 0
        if old_menu_scs:
            deleted_permissions = _soft_delete_query(
                MenuPermission,
                [MenuPermission.menu_secure_code.in_(old_menu_scs)],
                dry_run,
            )
            deleted_requirements = _soft_delete_query(
                MenuRoleRequirement,
                [MenuRoleRequirement.menu_secure_code.in_(old_menu_scs)],
                dry_run,
            )

        deleted_menus = len(old_menus)
        for item in old_menus:
            print(f"[DEL ] menu_items 軟刪: code={item.code} sc={item.secure_code}")
            if not dry_run:
                item.is_deleted = True
                item.deleted_at = _now()
                item.updated_at = _now()

        if dry_run:
            db.session.rollback()
            print("[DRY ] 已 rollback，未寫入")
        else:
            db.session.commit()
            print("[DONE] 已 commit")

        print(
            "[SUMMARY] "
            f"更新選單={0 if manual is None else 1}, "
            f"暫存改名={renamed_deleted_manual}, "
            f"補權限 add={perm_stats['add']} restore={perm_stats['restore']} skip={perm_stats['skip']}, "
            f"補角色 add={role_stats['add']} restore={role_stats['restore']} "
            f"skip={role_stats['skip']} missing_role={role_stats['missing_role']}, "
            f"軟刪選單={deleted_menus}, 軟刪權限={deleted_permissions}, 軟刪角色需求={deleted_requirements}"
        )

        db.session.execute(text("SET LOCAL app.is_system_admin = 'true'"))
        rows = db.session.execute(text("""
            SELECT
                mi.code,
                mi.title,
                mi.link_type,
                mi.link_target,
                mi.is_deleted,
                COUNT(DISTINCT mp.user_type) FILTER (WHERE mp.is_deleted = false) AS active_permissions,
                COUNT(DISTINCT mrr.secure_code) FILTER (WHERE mrr.is_deleted = false) AS active_role_requirements
            FROM menu_items mi
            LEFT JOIN menu_permissions mp ON mp.menu_secure_code = mi.secure_code
            LEFT JOIN menu_role_requirements mrr ON mrr.menu_secure_code = mi.secure_code
            WHERE mi.code LIKE 'platform_help.%'
            GROUP BY mi.code, mi.title, mi.link_type, mi.link_target, mi.is_deleted
            ORDER BY mi.code, mi.is_deleted
        """)).fetchall()
        print("[VERIFY] platform_help.* 選單狀態：")
        for row in rows:
            print(
                "  "
                f"code={row.code}, title={row.title}, deleted={row.is_deleted}, "
                f"target={row.link_type}:{row.link_target}, "
                f"active_permissions={row.active_permissions}, "
                f"active_role_requirements={row.active_role_requirements}"
            )
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description='099: 合併 platform_help 說明選單',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--run', action='store_true', help='實際執行並 commit')
    parser.add_argument('--dry-run', action='store_true', help='預覽但不寫入')
    args = parser.parse_args()

    if args.run and args.dry_run:
        parser.error('--run 與 --dry-run 只能擇一')

    if not args.run and not args.dry_run:
        parser.print_help()
        print('\n[INFO] 未指定參數，預設執行 dry-run；加上 --run 才會寫入資料庫。')
        return run(dry_run=True)

    return run(dry_run=not args.run)


if __name__ == '__main__':
    sys.exit(main())
