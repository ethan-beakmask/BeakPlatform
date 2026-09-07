"""
System organization factory defaults.

本模組補齊 fresh 安裝時系統企業需要的出廠資料，呼叫端負責 commit。

依 PERM-04，系統企業刻意不種 module_access_control；系統企業不走一般
ModuleRoleService.seed_org_module_roles 的模組授權回填。

ORG_ADMIN 帳號查詢刻意不過濾 is_active：如果 enterprise 帳號已存在但被停用，
冪等語意是沿用該帳號、不重建同名帳號，避免繞過停用狀態或撞到唯一性約束。
"""
import logging
import sys

from sqlalchemy import text

from app import db

logger = logging.getLogger(__name__)


ROLE_CODE_TO_KEY = {
    'ORG_ADMIN': 'org_admin',
    'EMPLOYEE': 'employee',
    'FORM_DESIGNER': 'form_designer',
    'FLOW_DESIGNER': 'flow_designer',
    'RISK_CONTROLLER': 'risk_controller',
}

PERMISSION_ROLE_KEYS = (
    'employee',
    'form_designer',
    'flow_designer',
    'risk_controller',
)


def _count_role_permissions(roles):
    from app.models.role_permission import RolePermission

    if not roles:
        return 0

    role_secure_codes = [role.secure_code for role in roles if role]
    if not role_secure_codes:
        return 0

    return RolePermission.query.filter(
        RolePermission.role_secure_code.in_(role_secure_codes),
        RolePermission.is_deleted == False,
    ).count()


def seed_system_org_defaults(admin_password=None) -> dict:
    """種入系統企業出廠資料（冪等，不 commit）。"""
    from app.models import Organization, Role, User
    from app.models.associations import UserRoleAssignment
    from app.models.organizational_unit import OrganizationalUnit
    from app.models.role_permission import RolePermission
    from app.models.user_numbering_rule import UserNumberingRule

    try:
        db.session.execute(text("SET LOCAL app.is_system_admin = 'true'"))

        org = Organization.query.filter_by(
            code='SYSTEM',
            is_deleted=False,
        ).first()
        if not org:
            raise ValueError('系統企業不存在，無法種入出廠資料')

        summary = {
            'roles_created': 0,
            'role_perms_assigned': 0,
            'org_admin_created': False,
            'role_assignment_created': False,
            'numbering_rules_created': 0,
            'employee_id_assigned': False,
            'external_group_created': False,
            'mrr_created': 0,
            'protected_targets_created': 0,
            'api_key_request': None,
            'proxy_request': None,
        }

        from app.services.organization_service import OrganizationService

        role_count = Role.query.filter_by(
            org_secure_code=org.secure_code,
            is_deleted=False,
        ).count()

        if role_count == 0:
            roles = OrganizationService._create_default_roles(org)
            db.session.flush()
            summary['roles_created'] = len(roles)
        else:
            existing_roles = Role.query.filter(
                Role.org_secure_code == org.secure_code,
                Role.is_deleted == False,
                Role.code.in_(list(ROLE_CODE_TO_KEY.keys())),
            ).all()
            roles = {
                ROLE_CODE_TO_KEY[role.code]: role
                for role in existing_roles
                if role.code in ROLE_CODE_TO_KEY
            }

        roles_needing_permissions = {}
        for role_key in PERMISSION_ROLE_KEYS:
            role = roles.get(role_key)
            if not role:
                continue
            permission_count = RolePermission.query.filter_by(
                role_secure_code=role.secure_code,
                is_deleted=False,
            ).count()
            if permission_count == 0:
                roles_needing_permissions[role_key] = role

        if roles_needing_permissions:
            tracked_roles = list(roles_needing_permissions.values())
            before_count = _count_role_permissions(tracked_roles)
            OrganizationService._assign_default_role_permissions(
                org, roles_needing_permissions)
            db.session.flush()
            after_count = _count_role_permissions(tracked_roles)
            summary['role_perms_assigned'] = max(0, after_count - before_count)

        org_admin_user = User.query.filter_by(
            org_secure_code=org.secure_code,
            username='enterprise',
            is_deleted=False,
        ).first()

        if not org_admin_user and admin_password:
            org_admin_user = OrganizationService._create_default_admin(
                org, 'enterprise', admin_password)
            org_admin_user.display_name = '系統企業管理員'
            db.session.flush()
            summary['org_admin_created'] = True
        elif not org_admin_user:
            warning = '未提供密碼，略過建立系統企業管理員帳號'
            logger.warning(warning)
            print(f'警告: {warning}', file=sys.stderr)

        org_admin_role = roles.get('org_admin')
        if org_admin_user and org_admin_role:
            assignment = UserRoleAssignment.query.filter_by(
                org_secure_code=org.secure_code,
                user_secure_code=org_admin_user.secure_code,
                role_secure_code=org_admin_role.secure_code,
                is_deleted=False,
            ).first()
            if not assignment:
                db.session.execute(text("SET LOCAL app.is_system_admin = 'true'"))
                db.session.flush()
                db.session.add(UserRoleAssignment(
                    user_secure_code=org_admin_user.secure_code,
                    role_secure_code=org_admin_role.secure_code,
                    org_secure_code=org.secure_code,
                ))
                db.session.flush()
                summary['role_assignment_created'] = True

        numbering_rule_count = UserNumberingRule.query.filter_by(
            org_secure_code=org.secure_code,
            is_deleted=False,
        ).count()
        if numbering_rule_count == 0:
            OrganizationService._create_default_numbering_rules(org)
            db.session.flush()
            summary['numbering_rules_created'] = 6

        if org_admin_user and not org_admin_user.employee_id:
            db.session.flush()
            OrganizationService._assign_admin_employee_id(org, org_admin_user)
            db.session.flush()
            summary['employee_id_assigned'] = bool(org_admin_user.employee_id)

        external_group = OrganizationalUnit.query.filter_by(
            org_secure_code=org.secure_code,
            code='EXTERNAL_VENDORS',
            is_deleted=False,
        ).first()
        if not external_group:
            OrganizationService._create_default_external_group(org)
            db.session.flush()
            summary['external_group_created'] = True

        from app.services.menu_service import MenuService
        summary['mrr_created'] = MenuService.seed_org_role_requirements(
            org.secure_code)

        from app.defaults.od_protected_defaults import (
            seed_org_builtin_protected_targets,
        )
        summary['protected_targets_created'] = (
            seed_org_builtin_protected_targets(org.secure_code))

        from app.defaults.api_key_request_defaults import (
            seed_org_api_key_request_flow,
        )
        api_key_result = seed_org_api_key_request_flow(org.secure_code)
        summary['api_key_request'] = api_key_result
        if isinstance(api_key_result, dict) and not api_key_result.get('ok', True):
            raise RuntimeError(
                f"API Key 申請單鏈路種入失敗: {api_key_result}")

        from app.defaults.proxy_request_defaults import (
            seed_org_proxy_request_flow,
        )
        proxy_result = seed_org_proxy_request_flow(org.secure_code)
        summary['proxy_request'] = proxy_result
        if isinstance(proxy_result, dict) and not proxy_result.get('ok', True):
            raise RuntimeError(
                f"代理指定申請單鏈路種入失敗: {proxy_result}")

        logger.info(
            'System org defaults seeded org=%s summary=%s',
            org.secure_code, summary,
        )
        return summary
    except Exception as exc:
        logger.exception('System org defaults failed: %s', exc)
        raise
