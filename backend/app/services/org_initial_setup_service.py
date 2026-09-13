"""
Organization initial setup service.

This is the single implementation used by the first-login wizard and seed
scripts when converting the original admin into a bound employee/admin pair.
"""
import logging

from flask_babel import gettext as _

from .. import db
from ..models.role import Role
from ..models.user import User, UserType
from ..models.user_numbering_rule import UsedUserNumber
from .numbering_service import NumberingService
from .password_policy_service import PasswordPolicyService
from .role_assignment_service import assign_role

logger = logging.getLogger(__name__)


def complete_initial_setup(
    org,
    original_admin,
    username,
    native_name,
    english_name,
    password,
    *,
    employee_id=None,
    nickname=None,
    backup_email_1=None,
    mobile_phone_1=None,
    must_change_password=False,
):
    """
    Complete the original admin wizard.

    Returns:
        {'employee': User, 'admin': User}

    Raises:
        ValueError: localized validation message suitable for flashing.
    """
    if not org:
        raise ValueError(_('找不到所屬企業'))
    if not original_admin or not getattr(original_admin, 'is_original_admin', False):
        raise ValueError(_('只有原始管理員可以執行初始設定'))
    if original_admin.org_secure_code != org.secure_code:
        raise ValueError(_('原始管理員與企業不一致'))
    if not original_admin.is_active or original_admin.is_deleted:
        raise ValueError(_('原始管理員帳號不可用'))

    native_name = (native_name or '').strip()
    english_name = (english_name or '').strip()
    username_raw = (username or '').strip()
    username = ''.join(username_raw.split()).lower()
    employee_id = (employee_id or '').strip() or None
    nickname = (nickname or '').strip() or None
    backup_email_1 = (backup_email_1 or '').strip() or None
    mobile_phone_1 = (mobile_phone_1 or '').strip() or None

    if not native_name or not english_name or not username:
        raise ValueError(_('本國姓名、英文姓名、帳號為必填'))
    if not password:
        raise ValueError(_('密碼為必填'))

    pw_valid, pw_errors = PasswordPolicyService.validate_password(
        password, org.secure_code)
    if not pw_valid:
        raise ValueError('\n'.join(pw_errors))

    auto_generated_id = False
    default_rule = None
    if not employee_id:
        default_rule = NumberingService.get_default_rule(
            org.secure_code, 'EMPLOYEE'
        )
        if default_rule:
            try:
                employee_id = NumberingService.get_next_number(
                    default_rule, consume=False
                )
                auto_generated_id = True
            except ValueError:
                employee_id = None
    if not employee_id:
        raise ValueError(_('用戶編號為必填，且無可用的預設編號規則'))

    employee_email = f"{username}@{org.domain_name}"
    admin_username = f"admin-{username}"
    admin_email = f"{admin_username}@{org.domain_name}"

    existing_emp = User.query.filter_by(
        email=employee_email,
        is_deleted=False,
    ).first()
    if existing_emp:
        raise ValueError(_('帳號 %(username)s 已存在', username=username))

    existing_adm = User.query.filter_by(
        email=admin_email,
        is_deleted=False,
    ).first()
    if existing_adm:
        raise ValueError(_('管理員帳號 %(username)s 已存在', username=admin_username))

    emp_id_exists = User.query.filter_by(
        org_secure_code=org.secure_code,
        employee_id=employee_id,
        is_deleted=False,
    ).first()
    if emp_id_exists:
        raise ValueError(_('用戶編號 %(employee_id)s 已存在', employee_id=employee_id))

    display_name_field = org.get_setting('display_name_field', 'native_name')
    display_name_map = {
        'native_name': native_name,
        'english_name': english_name,
        'nickname': nickname or native_name,
        'username': username,
        'employee_id': employee_id,
    }
    display_name = display_name_map.get(display_name_field, native_name)

    if not backup_email_1:
        backup_email_1 = employee_email

    employee = User(
        username=username,
        email=employee_email,
        display_name=display_name,
        org_secure_code=org.secure_code,
        user_type=UserType.EMPLOYEE,
        is_active=True,
        employee_id=employee_id,
        english_name=english_name,
        native_name=native_name,
        nickname=nickname,
        backup_email_1=backup_email_1,
        mobile_phone_1=mobile_phone_1,
        must_change_password=must_change_password,
    )
    employee.set_password(password)
    db.session.add(employee)
    db.session.flush()

    if employee_id:
        if auto_generated_id:
            default_rule = default_rule or NumberingService.get_default_rule(
                org.secure_code, 'EMPLOYEE'
            )
            if default_rule:
                NumberingService.get_next_number(default_rule, consume=True)
                used = UsedUserNumber.query.filter_by(
                    org_secure_code=org.secure_code,
                    number=employee_id,
                ).first()
                if used:
                    used.user_secure_code = employee.secure_code
        else:
            UsedUserNumber.record_number(
                org_secure_code=org.secure_code,
                number=employee_id,
                user_secure_code=employee.secure_code,
            )

    admin_user = User(
        username=admin_username,
        email=admin_email,
        display_name=display_name,
        org_secure_code=org.secure_code,
        user_type=UserType.ORG_ADMIN,
        is_active=True,
        backup_email_1=backup_email_1,
        bound_employee_secure_code=employee.secure_code,
        must_change_password=must_change_password,
    )
    admin_user.set_password(password)
    db.session.add(admin_user)
    db.session.flush()

    for user, role_code in ((admin_user, 'ORG_ADMIN'), (employee, 'EMPLOYEE')):
        role = Role.query.filter(
            Role.org_secure_code == org.secure_code,
            Role.code == role_code,
            Role.is_deleted == False,
        ).first()
        if role:
            assign_role(
                org.secure_code,
                user.secure_code,
                role.secure_code,
                operator=original_admin,
                source_ref='system:initial-setup',
                commit=False,
            )

    original_admin.is_active = False
    logger.info(
        "[INITIAL-SETUP] org=%s employee=%s admin=%s original_admin=%s deactivated",
        org.domain_name,
        username,
        admin_username,
        original_admin.username,
    )
    db.session.flush()
    return {'employee': employee, 'admin': admin_user}


def create_bound_org_admin(org, bound_employee, password, operator):
    """Create an ORG_ADMIN account bound to an existing employee."""
    if not org:
        raise ValueError(_('找不到所屬企業'))
    if not bound_employee:
        raise ValueError(_('選擇的企業成員帳號無效'))
    if bound_employee.org_secure_code != org.secure_code:
        raise ValueError(_('選擇的企業成員帳號無效'))
    if bound_employee.user_type != UserType.EMPLOYEE:
        raise ValueError(_('選擇的企業成員帳號無效'))
    if not bound_employee.is_active or bound_employee.is_deleted:
        raise ValueError(_('選擇的企業成員帳號無效'))
    if not password:
        raise ValueError(_('請輸入密碼'))

    admin_username = f"admin-{bound_employee.username}"
    admin_email = f"{admin_username}@{org.domain_name}"
    existing = User.query.filter_by(email=admin_email, is_deleted=False).first()
    if existing:
        raise ValueError(_('管理員帳號 %(username)s 已存在', username=admin_username))

    notify_email = bound_employee.backup_email_1 or bound_employee.email
    admin_user = User(
        username=admin_username,
        email=admin_email,
        display_name=bound_employee.display_name,
        org_secure_code=org.secure_code,
        user_type=UserType.ORG_ADMIN,
        is_active=True,
        backup_email_1=notify_email,
        bound_employee_secure_code=bound_employee.secure_code,
    )
    admin_user.set_password(password)
    db.session.add(admin_user)
    db.session.flush()

    org_admin_role = Role.query.filter(
        Role.org_secure_code == org.secure_code,
        Role.code == 'ORG_ADMIN',
        Role.is_deleted == False,
    ).first()
    if org_admin_role:
        assign_role(
            org.secure_code,
            admin_user.secure_code,
            org_admin_role.secure_code,
            operator=operator,
            source_ref='admin:create-bound-org-admin',
            commit=False,
        )

    original_admin = User.query.filter(
        User.org_secure_code == org.secure_code,
        User.is_original_admin == True,
        User.is_active == True,
        User.is_deleted == False,
    ).first()
    if original_admin:
        original_admin.is_active = False

    db.session.flush()
    return {'admin': admin_user, 'disabled_original_admin': original_admin}
