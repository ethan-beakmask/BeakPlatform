"""
BeakPlatform - Data API for Modules
模組資料接口

提供模組查詢平台資料（用戶、部門、角色等）的標準接口。
所有查詢都會自動過濾當前企業的資料（租戶隔離）。
"""
from typing import List, Optional, Dict, Any

from flask_login import current_user


def get_current_org():
    """
    取得當前用戶的企業

    Returns:
        Organization 物件，未登入時返回 None
    """
    if not current_user or not current_user.is_authenticated:
        return None

    return current_user.organization


def get_current_org_code() -> Optional[str]:
    """
    取得當前企業的 secure_code

    Returns:
        企業 secure_code，未登入時返回 None
    """
    org = get_current_org()
    return org.secure_code if org else None


def get_users(
    include_inactive: bool = False,
    department_code: str = None,
    role_code: str = None,
    search: str = None,
    limit: int = None
) -> List[Dict[str, Any]]:
    """
    查詢當前企業的用戶列表

    Args:
        include_inactive: 是否包含停用的用戶
        department_code: 過濾特定部門
        role_code: 過濾特定角色
        search: 搜尋關鍵字（姓名、帳號、企業成員編號）
        limit: 限制回傳數量

    Returns:
        用戶資料列表（字典格式）
    """
    org_code = get_current_org_code()
    if not org_code:
        return []

    from ..models import User, UserUnitAssignment, UserRoleAssignment
    from .. import db

    query = User.query.filter(
        User.org_secure_code == org_code,
        User.is_deleted == False
    )

    if not include_inactive:
        query = query.filter(User.is_active == True)

    if department_code:
        # 透過 UserUnitAssignment 過濾
        subquery = db.session.query(UserUnitAssignment.user_secure_code).filter(
            UserUnitAssignment.unit_secure_code == department_code,
            UserUnitAssignment.is_deleted == False
        )
        query = query.filter(User.secure_code.in_(subquery))

    if role_code:
        # 透過 UserRoleAssignment 過濾
        subquery = db.session.query(UserRoleAssignment.user_secure_code).filter(
            UserRoleAssignment.role_secure_code == role_code,
            UserRoleAssignment.is_deleted == False
        )
        query = query.filter(User.secure_code.in_(subquery))

    if search:
        search_pattern = f'%{search}%'
        query = query.filter(db.or_(
            User.display_name.ilike(search_pattern),
            User.username.ilike(search_pattern),
            User.employee_id.ilike(search_pattern),
            User.email.ilike(search_pattern)
        ))

    query = query.order_by(User.display_name)

    if limit:
        query = query.limit(limit)

    users = query.all()

    return [_user_to_dict(u) for u in users]


def get_user_by_code(secure_code: str) -> Optional[Dict[str, Any]]:
    """
    依 secure_code 取得用戶

    Args:
        secure_code: 用戶的 secure_code

    Returns:
        用戶資料（字典格式），找不到時返回 None
    """
    org_code = get_current_org_code()
    if not org_code:
        return None

    from ..models import User

    user = User.query.filter(
        User.secure_code == secure_code,
        User.org_secure_code == org_code,
        User.is_deleted == False
    ).first()

    return _user_to_dict(user) if user else None


def get_user_by_employee_id(employee_id: str) -> Optional[Dict[str, Any]]:
    """
    依企業成員編號取得用戶

    Args:
        employee_id: 企業成員編號

    Returns:
        用戶資料（字典格式），找不到時返回 None
    """
    org_code = get_current_org_code()
    if not org_code:
        return None

    from ..models import User

    user = User.query.filter(
        User.employee_id == employee_id,
        User.org_secure_code == org_code,
        User.is_deleted == False
    ).first()

    return _user_to_dict(user) if user else None


def get_departments(
    include_inactive: bool = False,
    parent_code: str = None,
    flat: bool = False
) -> List[Dict[str, Any]]:
    """
    查詢當前企業的部門列表

    Args:
        include_inactive: 是否包含停用的部門
        parent_code: 過濾特定父部門下的子部門
        flat: True 返回扁平列表，False 返回樹狀結構

    Returns:
        部門資料列表
    """
    org_code = get_current_org_code()
    if not org_code:
        return []

    from ..models import OrganizationalUnit, UnitType

    query = OrganizationalUnit.query.filter(
        OrganizationalUnit.org_secure_code == org_code,
        OrganizationalUnit.unit_type == UnitType.DEPARTMENT,
        OrganizationalUnit.is_deleted == False
    )

    if not include_inactive:
        query = query.filter(OrganizationalUnit.is_active == True)

    if parent_code:
        query = query.filter(OrganizationalUnit.parent_secure_code == parent_code)

    query = query.order_by(OrganizationalUnit.sort_order, OrganizationalUnit.name)

    departments = query.all()

    if flat:
        return [_department_to_dict(d) for d in departments]

    # 建構樹狀結構
    return _build_department_tree(departments)


def get_department_by_code(secure_code: str) -> Optional[Dict[str, Any]]:
    """
    依 secure_code 取得部門

    Args:
        secure_code: 部門的 secure_code

    Returns:
        部門資料（字典格式），找不到時返回 None
    """
    org_code = get_current_org_code()
    if not org_code:
        return None

    from ..models import OrganizationalUnit

    dept = OrganizationalUnit.query.filter(
        OrganizationalUnit.secure_code == secure_code,
        OrganizationalUnit.org_secure_code == org_code,
        OrganizationalUnit.is_deleted == False
    ).first()

    return _department_to_dict(dept) if dept else None


def get_roles(include_inactive: bool = False) -> List[Dict[str, Any]]:
    """
    查詢當前企業的角色列表

    Args:
        include_inactive: 是否包含停用的角色

    Returns:
        角色資料列表
    """
    org_code = get_current_org_code()
    if not org_code:
        return []

    from ..models import Role

    query = Role.query.filter(
        Role.org_secure_code == org_code,
        Role.is_deleted == False
    )

    if not include_inactive:
        query = query.filter(Role.is_active == True)

    query = query.order_by(Role.name)

    roles = query.all()

    return [_role_to_dict(r) for r in roles]


def get_role_by_code(secure_code: str) -> Optional[Dict[str, Any]]:
    """
    依 secure_code 取得角色

    Args:
        secure_code: 角色的 secure_code

    Returns:
        角色資料（字典格式），找不到時返回 None
    """
    org_code = get_current_org_code()
    if not org_code:
        return None

    from ..models import Role

    role = Role.query.filter(
        Role.secure_code == secure_code,
        Role.org_secure_code == org_code,
        Role.is_deleted == False
    ).first()

    return _role_to_dict(role) if role else None


# ==================== Helper Functions ====================

def _user_to_dict(user) -> Optional[Dict[str, Any]]:
    """將 User 物件轉換為字典"""
    if not user:
        return None

    return {
        'secure_code': user.secure_code,
        'username': user.username,
        'email': user.email,
        'display_name': user.display_name,
        'employee_id': user.employee_id,
        'is_active': user.is_active,
        'is_org_admin': user.is_org_admin,
        'primary_unit_code': user.primary_unit.secure_code if user.primary_unit else None,
        'primary_unit_name': user.primary_unit.name if user.primary_unit else None,
    }


def _department_to_dict(dept) -> Optional[Dict[str, Any]]:
    """將 OrganizationalUnit 物件轉換為字典"""
    if not dept:
        return None

    return {
        'secure_code': dept.secure_code,
        'code': dept.code,
        'name': dept.name,
        'parent_code': dept.parent_secure_code,
        'is_active': dept.is_active,
        'sort_order': dept.sort_order,
        'manager_code': _department_manager_code(dept),
    }


def _department_manager_code(dept) -> Optional[str]:
    """部門正主管（DEPT_MANAGER@unit 的第一位 regular 持有者）；PF-250：organizational_units 沒有 manager_secure_code 欄位，改由角色指派推導。"""
    from ..services.dept_membership_service import get_system_role
    from ..services.unit_resolver import resolve_role_holders

    role = get_system_role(dept.org_secure_code, 'DEPT_MANAGER')
    if not role:
        return None
    holders = resolve_role_holders(role.secure_code, dept.org_secure_code, dept.secure_code, unit_only=True)
    return holders[0] if holders else None


def _role_to_dict(role) -> Optional[Dict[str, Any]]:
    """將 Role 物件轉換為字典"""
    if not role:
        return None

    return {
        'secure_code': role.secure_code,
        'code': role.code,
        'name': role.name,
        'description': role.description,
        'is_active': role.is_active,
        'role_type': role.role_type.value if role.role_type else None,
    }


def _build_department_tree(departments: list) -> List[Dict[str, Any]]:
    """將部門列表建構為樹狀結構"""
    dept_dict = {d.secure_code: _department_to_dict(d) for d in departments}

    # 加入 children 欄位
    for d in dept_dict.values():
        d['children'] = []

    # 建構父子關係
    roots = []
    for d in dept_dict.values():
        parent_code = d['parent_code']
        if parent_code and parent_code in dept_dict:
            dept_dict[parent_code]['children'].append(d)
        else:
            roots.append(d)

    return roots


# ==================== Menu Functions ====================

def get_module_menu_tree(module_name: str) -> List[Dict[str, Any]]:
    """
    取得模組的選單樹

    Args:
        module_name: 模組名稱

    Returns:
        選單樹結構
    """
    from ..services.module_menu_service import ModuleMenuService

    menus = ModuleMenuService.get_module_menus(module_name)

    # 建構樹狀結構
    return _build_menu_tree(menus)


def _build_menu_tree(menus: list) -> List[Dict[str, Any]]:
    """將選單列表建構為樹狀結構"""
    menu_dict = {}

    # 先建立所有選單的字典
    for m in menus:
        menu_dict[m.secure_code] = {
            'code': m.code,
            'title': m.title,
            'icon': m.icon,
            'url': m.link_target,
            'is_active': m.is_active,
            'children': []
        }

    # 建構父子關係
    roots = []
    for m in menus:
        node = menu_dict[m.secure_code]
        if m.parent_secure_code and m.parent_secure_code in menu_dict:
            menu_dict[m.parent_secure_code]['children'].append(node)
        else:
            roots.append(node)

    return roots
