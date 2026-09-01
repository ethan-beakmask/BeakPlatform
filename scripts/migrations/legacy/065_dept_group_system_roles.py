"""
065: 部門/社群系統角色重構

取消 per-unit *_MEMBER 角色，改用系統級 DEPT_MEMBER、DEPT_EMPLOYEE、GROUP_MEMBER。

變更內容：
1. 為每個企業建立 DEPT_MEMBER、DEPT_EMPLOYEE、GROUP_MEMBER 系統角色
2. 為既有的 DEPT_MANAGER 加上 DEPT_POSITION 互斥群組
3. 將既有部門成員的 *_MEMBER 角色指派遷移為 DEPT_MEMBER + DEPT_EMPLOYEE
4. 將既有社群的 *_MEMBER 角色指派遷移為 GROUP_MEMBER
5. 將既有主管同時指派 DEPT_MEMBER（主管也是部門成員）
6. 軟刪除舊的 per-unit *_MEMBER 角色
7. 移除 organizational_units.member_role_secure_code 欄位

用法:
    python scripts/migrations/065_dept_group_system_roles.py          顯示說明
    python scripts/migrations/065_dept_group_system_roles.py --status 檢查狀態
    python scripts/migrations/065_dept_group_system_roles.py --run    執行遷移
"""
import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from app import create_app, db

MIGRATION_ID = '065_dept_group_system_roles'


def _get_or_create_system_role(org_sc, code, name, description,
                               role_type, scope_type, is_manager=False,
                               exclusive_group=None):
    """取得或建立系統角色，回傳 Role 物件"""
    from app.models.role import Role

    existing = Role.query.filter(
        Role.org_secure_code == org_sc,
        Role.code == code,
        Role.is_deleted == False,
    ).first()

    if existing:
        # 確保屬性一致
        changed = False
        if existing.exclusive_group != exclusive_group:
            existing.exclusive_group = exclusive_group
            changed = True
        if not existing.is_system_role:
            existing.is_system_role = True
            changed = True
        return existing, changed

    role = Role(
        org_secure_code=org_sc,
        role_type=role_type,
        scope_type=scope_type,
        code=code,
        name=name,
        description=description,
        exclusive_group=exclusive_group,
        is_manager=is_manager,
        is_system_role=True,
        is_active=True,
    )
    role.update_full_path()
    db.session.add(role)
    db.session.flush()
    return role, True


def check_status():
    """檢查遷移狀態"""
    app = create_app()
    with app.app_context():
        from app.models.role import Role
        from app.models import Organization

        orgs = Organization.query.filter(
            Organization.is_deleted == False
        ).all()

        print(f"\n企業數: {len(orgs)}")

        for org in orgs:
            print(f"\n--- {org.name} ({org.secure_code}) ---")

            # 檢查新系統角色
            for code in ('DEPT_MEMBER', 'DEPT_EMPLOYEE', 'GROUP_MEMBER'):
                role = Role.query.filter(
                    Role.org_secure_code == org.secure_code,
                    Role.code == code,
                    Role.is_deleted == False,
                ).first()
                status = 'OK' if role else 'MISSING'
                print(f"  {code}: {status}")

            # 檢查 DEPT_MANAGER exclusive_group
            mgr = Role.query.filter(
                Role.org_secure_code == org.secure_code,
                Role.code == 'DEPT_MANAGER',
                Role.is_deleted == False,
            ).first()
            if mgr:
                eg = mgr.exclusive_group or 'NULL'
                print(f"  DEPT_MANAGER exclusive_group: {eg}")

            # 計算舊的 *_MEMBER 角色
            old_member_roles = Role.query.filter(
                Role.org_secure_code == org.secure_code,
                Role.code.like('%_MEMBER'),
                Role.is_system_role == False,
                Role.is_deleted == False,
            ).count()
            print(f"  舊 *_MEMBER 角色 (待清理): {old_member_roles}")

        # 檢查 member_role_secure_code 欄位
        col_exists = db.session.execute(db.text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'organizational_units'
            AND column_name = 'member_role_secure_code'
        """)).fetchone()
        print(f"\nmember_role_secure_code 欄位: {'EXISTS (待移除)' if col_exists else 'REMOVED'}")


def run_migration():
    """執行遷移"""
    app = create_app()
    with app.app_context():
        from app.models.role import Role, RoleType, ScopeType, ExclusiveGroup
        from app.models import Organization
        from app.models.associations import UserRoleAssignment
        from app.models.organizational_unit import OrganizationalUnit, UnitType

        orgs = Organization.query.filter(
            Organization.is_deleted == False
        ).all()

        total_created = 0
        total_migrated = 0
        total_cleaned = 0

        for org in orgs:
            org_sc = org.secure_code
            print(f"\n=== 處理企業: {org.name} ({org_sc}) ===")

            # --- Step 1: 建立新系統角色 ---
            dept_member, created = _get_or_create_system_role(
                org_sc, 'DEPT_MEMBER', '部門成員',
                '部門通用成員角色，部門內所有人(主管+員工)皆擁有',
                RoleType.ROLE, ScopeType.DEPARTMENT
            )
            if created:
                total_created += 1
                print(f"  [建立] DEPT_MEMBER")

            dept_employee, created = _get_or_create_system_role(
                org_sc, 'DEPT_EMPLOYEE', '部門員工',
                '部門一般員工，與部門主管互斥(同一部門下擇一)',
                RoleType.ROLE, ScopeType.DEPARTMENT,
                exclusive_group=ExclusiveGroup.DEPT_POSITION
            )
            if created:
                total_created += 1
                print(f"  [建立] DEPT_EMPLOYEE")

            group_member, created = _get_or_create_system_role(
                org_sc, 'GROUP_MEMBER', '社群成員',
                '社群通用成員角色，社群內所有人(召集人+團員)皆擁有',
                RoleType.ROLE, ScopeType.GROUP
            )
            if created:
                total_created += 1
                print(f"  [建立] GROUP_MEMBER")

            # --- Step 2: DEPT_MANAGER 加上互斥群組 ---
            dept_manager = Role.query.filter(
                Role.org_secure_code == org_sc,
                Role.code == 'DEPT_MANAGER',
                Role.is_deleted == False,
            ).first()
            if dept_manager and dept_manager.exclusive_group != ExclusiveGroup.DEPT_POSITION:
                dept_manager.exclusive_group = ExclusiveGroup.DEPT_POSITION
                print(f"  [更新] DEPT_MANAGER -> exclusive_group=DEPT_POSITION")

            db.session.flush()

            # --- Step 3: 遷移舊 *_MEMBER 角色指派 ---
            old_member_roles = Role.query.filter(
                Role.org_secure_code == org_sc,
                Role.code.like('%_MEMBER'),
                Role.is_system_role == False,
                Role.is_deleted == False,
            ).all()

            for old_role in old_member_roles:
                # 找出此角色的所有指派
                assignments = UserRoleAssignment.query.filter(
                    UserRoleAssignment.role_secure_code == old_role.secure_code,
                    UserRoleAssignment.is_deleted == False,
                ).all()

                # 判斷是部門還是社群角色
                is_dept = old_role.scope_type == ScopeType.DEPARTMENT

                for assign in assignments:
                    unit_sc = assign.unit_secure_code

                    # 嘗試從 bound_unit 或 assignment 取得 unit
                    if not unit_sc and old_role.bound_unit_secure_code:
                        unit_sc = old_role.bound_unit_secure_code

                    if not unit_sc:
                        # 嘗試用 role code 反推 unit
                        role_prefix = old_role.code.replace('_MEMBER', '')
                        unit = OrganizationalUnit.query.filter(
                            OrganizationalUnit.org_secure_code == org_sc,
                            OrganizationalUnit.code == role_prefix,
                            OrganizationalUnit.is_deleted == False,
                        ).first()
                        if unit:
                            unit_sc = unit.secure_code

                    if is_dept:
                        # 部門: 指派 DEPT_MEMBER + DEPT_EMPLOYEE
                        _ensure_assignment(
                            org_sc, assign.user_secure_code,
                            dept_member.secure_code, unit_sc,
                            'migration_065'
                        )
                        # 檢查此人在此部門是否已有 DEPT_MANAGER
                        has_mgr = False
                        if dept_manager and unit_sc:
                            has_mgr = UserRoleAssignment.query.filter(
                                UserRoleAssignment.org_secure_code == org_sc,
                                UserRoleAssignment.user_secure_code == assign.user_secure_code,
                                UserRoleAssignment.role_secure_code == dept_manager.secure_code,
                                UserRoleAssignment.unit_secure_code == unit_sc,
                                UserRoleAssignment.is_deleted == False,
                            ).first() is not None

                        if not has_mgr:
                            _ensure_assignment(
                                org_sc, assign.user_secure_code,
                                dept_employee.secure_code, unit_sc,
                                'migration_065'
                            )
                    else:
                        # 社群: 指派 GROUP_MEMBER
                        _ensure_assignment(
                            org_sc, assign.user_secure_code,
                            group_member.secure_code, unit_sc,
                            'migration_065'
                        )

                    total_migrated += 1

                # 軟刪除舊角色的所有指派
                for assign in assignments:
                    assign.is_deleted = True
                    assign.deleted_at = datetime.utcnow()

                # 軟刪除舊角色
                old_role.is_deleted = True
                old_role.deleted_at = datetime.utcnow()
                total_cleaned += 1
                print(f"  [清理] {old_role.code} ({old_role.name})")

            # --- Step 4: 既有主管也要有 DEPT_MEMBER ---
            if dept_manager:
                mgr_assignments = UserRoleAssignment.query.filter(
                    UserRoleAssignment.org_secure_code == org_sc,
                    UserRoleAssignment.role_secure_code == dept_manager.secure_code,
                    UserRoleAssignment.is_deleted == False,
                ).all()

                for ma in mgr_assignments:
                    _ensure_assignment(
                        org_sc, ma.user_secure_code,
                        dept_member.secure_code, ma.unit_secure_code,
                        'migration_065'
                    )

            db.session.flush()

        # --- Step 5: 移除 member_role_secure_code 欄位 ---
        col_exists = db.session.execute(db.text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'organizational_units'
            AND column_name = 'member_role_secure_code'
        """)).fetchone()

        if col_exists:
            db.session.execute(db.text(
                "ALTER TABLE organizational_units DROP COLUMN member_role_secure_code"
            ))
            print(f"\n[移除] organizational_units.member_role_secure_code 欄位")

        db.session.commit()

        print(f"\n{'='*50}")
        print(f"遷移完成:")
        print(f"  新增系統角色: {total_created}")
        print(f"  遷移角色指派: {total_migrated}")
        print(f"  清理舊角色:   {total_cleaned}")


def _ensure_assignment(org_sc, user_sc, role_sc, unit_sc, operator):
    """確保角色指派存在"""
    from app.models.associations import UserRoleAssignment

    existing = UserRoleAssignment.query.filter(
        UserRoleAssignment.org_secure_code == org_sc,
        UserRoleAssignment.user_secure_code == user_sc,
        UserRoleAssignment.role_secure_code == role_sc,
        UserRoleAssignment.unit_secure_code == unit_sc,
    ).first()

    if existing:
        if existing.is_deleted:
            existing.is_deleted = False
            existing.deleted_at = None
        return

    assignment = UserRoleAssignment(
        org_secure_code=org_sc,
        user_secure_code=user_sc,
        role_secure_code=role_sc,
        unit_secure_code=unit_sc,
        assigned_by=operator,
    )
    db.session.add(assignment)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=MIGRATION_ID)
    parser.add_argument('--run', action='store_true', help='執行遷移')
    parser.add_argument('--status', action='store_true', help='檢查狀態')
    args = parser.parse_args()

    if args.status:
        check_status()
    elif args.run:
        run_migration()
    else:
        print(__doc__)
