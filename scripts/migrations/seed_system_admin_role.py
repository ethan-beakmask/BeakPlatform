#!/usr/bin/env python3
"""
建立 SYSTEM_ADMIN 角色並授予全部有效權限

背景：[SEC-02] 移除了 SYSTEM_ADMIN 的 user_type RBAC 捷徑，系統管理員
必須靠實際角色授權通過 PermissionService 檢查。本腳本：
1. 建立 SYSTEM_ADMIN 角色（org=system.local，不存在才建）
2. 將全部有效權限（SYSTEM/ORG/MODULE）授予該角色
3. 將角色指派給所有 user_type=SYSTEM_ADMIN 的帳號

可重複執行（已存在的授權/指派會跳過）。
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))


def usage():
    print("""用法: python3 seed_system_admin_role.py [--dry-run]

建立 SYSTEM_ADMIN 角色、授予全部有效權限、指派給系統管理員帳號。

參數:
  --dry-run   只顯示將執行的動作，不寫入""")
    sys.exit(1)


def main():
    dry = '--dry-run' in sys.argv
    if any(a not in ('--dry-run',) for a in sys.argv[1:]):
        usage()

    from app import create_app, db
    from app.models import User, Role, Permission, RolePermission, UserRoleAssignment
    from app.utils.security import generate_secure_code

    app = create_app()
    with app.app_context():
        role = Role.query.filter_by(
            code='SYSTEM_ADMIN', org_secure_code='system.local', is_deleted=False
        ).first()
        if role is None:
            role = Role(
                secure_code=generate_secure_code(),
                code='SYSTEM_ADMIN',
                name='系統管理員',
                org_secure_code='system.local',
                role_level='MEMBER',
                scope_type='GLOBAL',
                is_active=True,
            )
            if not dry:
                db.session.add(role)
                db.session.flush()
            print(f"建立角色 SYSTEM_ADMIN ({role.secure_code})")
        else:
            print(f"角色已存在 ({role.secure_code})")

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
            if not dry:
                db.session.add(RolePermission(
                    secure_code=generate_secure_code(),
                    role_secure_code=role.secure_code,
                    permission_secure_code=p.secure_code,
                    is_active=True,
                ))
            granted += 1
        print(f"授予權限 {granted} 筆（總權限 {len(perms)} 筆，其餘已存在）")

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
            if not dry:
                db.session.add(UserRoleAssignment(
                    secure_code=generate_secure_code(),
                    user_secure_code=u.secure_code,
                    role_secure_code=role.secure_code,
                    org_secure_code=u.org_secure_code,
                ))
            assigned += 1
            print(f"指派給 {u.username} ({u.org_secure_code})")
        print(f"指派 {assigned} 筆（系統管理員共 {len(admins)} 人）")

        if not dry:
            db.session.commit()
            print("已提交")
        else:
            print("dry-run，未寫入")


if __name__ == '__main__':
    main()
