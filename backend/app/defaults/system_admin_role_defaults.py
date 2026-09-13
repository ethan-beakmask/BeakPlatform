"""
SYSTEM_ADMIN 角色出廠種入（冪等，不 commit）。

背景：[SEC-02] SYSTEM_ADMIN 這種 user_type 不享有 RBAC 捷徑，走 ResourceGateway 的
單筆檢視／集合查詢一律靠角色持有的 permission code。dev 庫的 SYSTEM_ADMIN 角色是
2026-07 legacy migration 076 建的，bootstrap 一直沒有對應步驟，所以 2026-09-13 之前的
每一次全新安裝，系統管理員都是零角色：企業列表看得到、點進合約就 403
「No permission to view Contract」（bpserv 2026-09-13 Ethan 撞到）。

做三件事，全部冪等：
1. 系統企業（code='SYSTEM'）底下建 SYSTEM_ADMIN 角色（不存在才建）
2. 把所有啟用中的 permission 授給它（缺哪個補哪個——新增 permission code 後跑
   bootstrap --update 會自動補齊，不必另寫 migration）
3. 指派給所有 user_type=SYSTEM_ADMIN 的啟用帳號（缺才指派）

呼叫端（bootstrap）負責 commit。順序上必須在 seed_system_permissions 與 sync_modules
之後（模組權限才會被納入），fresh 與 update 兩種模式都跑。
"""
import logging

from sqlalchemy import text

from app import db

logger = logging.getLogger(__name__)

SYSTEM_ADMIN_ROLE_CODE = 'SYSTEM_ADMIN'


def seed_system_admin_role() -> dict:
    from app.models import Organization, Permission, Role, User
    from app.models.associations import UserRoleAssignment
    from app.models.role import RoleLevel, RoleType, ScopeType
    from app.models.role_permission import RolePermission
    from app.models.user import UserType
    from app.services.role_assignment_service import ensure_role_layer_compatible

    db.session.execute(text("SET LOCAL app.is_system_admin = 'true'"))

    org = Organization.query.filter_by(code='SYSTEM', is_deleted=False).first()
    if not org:
        raise ValueError('系統企業不存在，無法種入 SYSTEM_ADMIN 角色')

    summary = {
        'role_created': False,
        'permissions_granted': 0,
        'assignments_created': 0,
        'role_secure_code': None,
    }

    role = Role.query.filter_by(
        org_secure_code=org.secure_code,
        code=SYSTEM_ADMIN_ROLE_CODE,
        is_deleted=False,
    ).first()
    if role is None:
        role = Role(
            org_secure_code=org.secure_code,
            code=SYSTEM_ADMIN_ROLE_CODE,
            name='系統管理員',
            description='平台系統管理員；持有全部權限定義（出廠自動維護）',
            role_type=RoleType.ROLE,
            scope_type=ScopeType.GLOBAL,
            role_level=RoleLevel.MEMBER,
            is_system_role=True,
            is_active=True,
        )
        db.session.add(role)
        db.session.flush()
        summary['role_created'] = True
    summary['role_secure_code'] = role.secure_code

    granted = {
        rp.permission_secure_code
        for rp in RolePermission.query.filter_by(
            role_secure_code=role.secure_code, is_deleted=False).all()
    }
    for perm in Permission.query.filter_by(is_active=True, is_deleted=False).all():
        if perm.secure_code in granted:
            continue
        db.session.add(RolePermission(
            role_secure_code=role.secure_code,
            permission_secure_code=perm.secure_code,
            is_active=True,
        ))
        summary['permissions_granted'] += 1

    admins = User.query.filter_by(
        user_type=UserType.SYSTEM_ADMIN, is_deleted=False, is_active=True).all()
    for admin in admins:
        exists = UserRoleAssignment.query.filter_by(
            user_secure_code=admin.secure_code,
            role_secure_code=role.secure_code,
            is_deleted=False,
        ).first()
        if exists:
            continue
        ensure_role_layer_compatible(admin, role)
        db.session.add(UserRoleAssignment(
            user_secure_code=admin.secure_code,
            role_secure_code=role.secure_code,
            org_secure_code=org.secure_code,
            assigned_by='bootstrap',
        ))
        summary['assignments_created'] += 1

    db.session.flush()
    logger.info('seed_system_admin_role: %s', summary)
    return summary
