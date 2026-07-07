#!/usr/bin/env python3
"""
076 - 建立 SYSTEM_ADMIN 角色並授予全部有效權限（冪等）

背景：[SEC-02] 移除了 SYSTEM_ADMIN 的 user_type RBAC 捷徑，系統管理員
必須靠實際角色授權通過 PermissionService 檢查。

本 migration 取代舊工具腳本 seed_system_admin_role.py（該腳本把 dev 的
系統企業 secure_code 'system.local' 硬編碼，prod 部署時 FK 爆炸）。
系統企業一律從 DB 以 code='SYSTEM' 動態解析，任何環境皆可執行。

1. 建立 SYSTEM_ADMIN 角色（掛在系統企業下，不存在才建）
2. 將全部有效權限（SYSTEM/ORG/MODULE）授予該角色
3. 將角色指派給所有 user_type=SYSTEM_ADMIN 的帳號

可重複執行（已存在的角色/授權/指派會跳過）。注意：075 之後若有新
migration 增加權限代碼，需另建 migration 補授權，或重跑本腳本邏輯。
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'backend'))


def main():
    from app import create_app, db
    from app.models import (
        User, Role, Permission, RolePermission, UserRoleAssignment, Organization,
    )
    from app.utils.security import generate_secure_code

    app = create_app()
    with app.app_context():
        # 系統企業動態解析 -- 各環境 secure_code 不同（dev: system.local，
        # prod: sys-xxxx），唯一不變的是 code='SYSTEM'
        sys_org = Organization.query.filter_by(
            code='SYSTEM', is_deleted=False
        ).first()
        if sys_org is None:
            print('ERROR: 找不到 code=SYSTEM 的系統企業，中止')
            sys.exit(1)
        sys_org_sc = sys_org.secure_code
        print(f'系統企業: {sys_org_sc}')

        role = Role.query.filter_by(
            code='SYSTEM_ADMIN', org_secure_code=sys_org_sc, is_deleted=False
        ).first()
        if role is None:
            role = Role(
                secure_code=generate_secure_code(),
                code='SYSTEM_ADMIN',
                name='系統管理員',
                org_secure_code=sys_org_sc,
                role_level='MEMBER',
                scope_type='GLOBAL',
                is_active=True,
            )
            db.session.add(role)
            db.session.flush()
            print(f'建立角色 SYSTEM_ADMIN ({role.secure_code})')
        else:
            print(f'角色已存在 ({role.secure_code})')

        perms = Permission.query.filter_by(is_active=True, is_deleted=False).all()
        granted = 0
        for p in perms:
            exists = RolePermission.query.filter_by(
                role_secure_code=role.secure_code,
                permission_secure_code=p.secure_code,
                is_deleted=False,
            ).first()
            if exists:
                continue
            db.session.add(RolePermission(
                secure_code=generate_secure_code(),
                role_secure_code=role.secure_code,
                permission_secure_code=p.secure_code,
                is_active=True,
            ))
            granted += 1
        print(f'授予權限 {granted} 筆（總權限 {len(perms)} 筆，其餘已存在）')

        admins = User.query.filter_by(
            user_type='SYSTEM_ADMIN', is_deleted=False
        ).all()
        assigned = 0
        for u in admins:
            exists = UserRoleAssignment.query.filter_by(
                user_secure_code=u.secure_code,
                role_secure_code=role.secure_code,
                is_deleted=False,
            ).first()
            if exists:
                continue
            db.session.add(UserRoleAssignment(
                secure_code=generate_secure_code(),
                user_secure_code=u.secure_code,
                role_secure_code=role.secure_code,
                org_secure_code=u.org_secure_code,
            ))
            assigned += 1
            print(f'指派給 {u.username} ({u.org_secure_code})')
        print(f'指派 {assigned} 筆（系統管理員共 {len(admins)} 人）')

        db.session.commit()
        print('已提交')


if __name__ == '__main__':
    main()
