"""
表單填寫權限解析 -- FwMappingPermission 共用檢查邏輯

供表單中心列表 (fc_available) 與送單 (fc_fill submit) 共用，
確保「看得到」與「送得出」使用同一套授權判斷。

規則：
- FLOW_DESIGNER / FORM_DESIGNER 角色永遠可填，供試行設計稿
- 已發行表單依 fw_mapping_permissions 判斷
- 無自訂規則時，預設 EMPLOYEE（企業成員）角色可填
- EXTERNAL 用戶只能透過 group 類型授權
"""

DEFAULT_FILL_ROLE_CODE = 'EMPLOYEE'
# 企業成員出廠角色，是已發行表單未設定自訂規則時的預設可見對象。


def is_hardcoded_fill_allowed(user):
    """FLOW_DESIGNER / FORM_DESIGNER 永遠可填，供設計者試行自己設計的表單。"""
    from app.platform.auth import get_user_roles

    hardcoded_role_codes = {'FLOW_DESIGNER', 'FORM_DESIGNER'}
    user_role_codes = {r['code'] for r in get_user_roles(user)}
    return bool(user_role_codes & hardcoded_role_codes)


def build_fill_permission_context(user, org_sc):
    """
    預載用戶身份資料（部門/群組祖先鏈），供 check_mapping_permission 使用。

    Returns:
        dict: {
            is_hardcoded, is_external, user_sc, role_codes,
            user_dept_sc, dept_ancestors, group_scs, group_ancestors
        }
    """
    from app.platform.auth import get_user_roles

    role_codes = {r['code'] for r in get_user_roles(user)}
    hardcoded_role_codes = {'FLOW_DESIGNER', 'FORM_DESIGNER'}
    ctx = {
        'is_hardcoded': bool(role_codes & hardcoded_role_codes),
        'is_external': str(getattr(user, 'user_type', '')) == 'EXTERNAL',
        'user_sc': user.secure_code,
        'role_codes': role_codes,
        'user_dept_sc': None,
        'dept_ancestors': set(),
        'group_scs': set(),
        'group_ancestors': set(),
    }

    if ctx['is_hardcoded']:
        return ctx  # 硬編碼角色不需身份資料

    from app.models import UserUnitMembership, OrganizationalUnit

    ctx['user_dept_sc'] = getattr(user, 'primary_unit_secure_code', None)

    # 用戶所屬群組（透過 membership）
    ctx['group_scs'] = set(
        m.unit_secure_code for m in UserUnitMembership.query.filter_by(
            user_secure_code=user.secure_code,
            org_secure_code=org_sc,
            is_deleted=False
        ).join(
            OrganizationalUnit,
            OrganizationalUnit.secure_code == UserUnitMembership.unit_secure_code
        ).filter(
            OrganizationalUnit.unit_type == 'GROUP',
            OrganizationalUnit.is_deleted == False
        ).all()
    )

    # 部門/群組祖先鏈（用於 include_children 判斷）
    if ctx['user_dept_sc']:
        _build_unit_ancestors(ctx['user_dept_sc'], ctx['dept_ancestors'], org_sc)
    for gsc in ctx['group_scs']:
        _build_unit_ancestors(gsc, ctx['group_ancestors'], org_sc)

    return ctx


def check_mapping_permission(ctx, perms):
    """
    以預載的 context 檢查一組 FwMappingPermission 是否放行。

    Args:
        ctx: build_fill_permission_context() 的回傳
        perms: 該 mapping 的 FwMappingPermission 列表（可為 None/空）
    """
    if ctx['is_hardcoded']:
        return True

    if not perms:
        # 無自訂規則時預設「企業成員」可填；is_external 是雙保險，
        # 確保外部廠商在任何情況下都不會經由預設規則被放行。
        return (
            (not ctx['is_external']) and
            (DEFAULT_FILL_ROLE_CODE in ctx['role_codes'])
        )

    for p in perms:
        if p.grant_type == 'user':
            if ctx['is_external']:
                continue  # EXTERNAL 不能透過 user 類型授權
            if p.grant_target == ctx['user_sc']:
                return True

        elif p.grant_type == 'role':
            if ctx['is_external']:
                continue  # EXTERNAL 不能透過 role 類型授權
            # role grant_target 存 roles.code（如 EMPLOYEE），非 secure_code；
            # 規則已有 org_secure_code，可讀性高且可直接與 role_codes 比對。
            if p.grant_target in ctx['role_codes']:
                return True

        elif p.grant_type == 'department':
            if ctx['is_external']:
                continue  # EXTERNAL 不能透過 department 授權
            if not ctx['user_dept_sc']:
                continue
            if p.include_children:
                # 用戶部門在此部門的子樹中（grant_target 是祖先之一）
                if p.grant_target in ctx['dept_ancestors']:
                    return True
            else:
                if p.grant_target == ctx['user_dept_sc']:
                    return True

        elif p.grant_type == 'group':
            if not ctx['group_scs']:
                continue
            if p.include_children:
                # grant_target 是用戶群組的祖先之一（含 __ORG_ROOT__）
                if p.grant_target in ctx['group_ancestors']:
                    return True
            else:
                if p.grant_target == '__ORG_ROOT__':
                    # 虛擬企業根（不含下層）-- 有任一群組成員身份即匹配
                    return True
                elif p.grant_target in ctx['group_scs']:
                    return True

    return False


def user_can_fill_mapping(user, org_sc, mapping_sc):
    """
    單一配對的填寫權限檢查（送單路徑用）。

    Args:
        user: 當前用戶（flask_login current_user）
        org_sc: 企業 secure_code（TENANT-01）
        mapping_sc: 配對 secure_code
    """
    ctx = build_fill_permission_context(user, org_sc)
    if ctx['is_hardcoded']:
        return True

    if not mapping_sc:
        return False

    from ..models import FwMappingPermission
    perms = FwMappingPermission.query.filter_by(
        org_secure_code=org_sc,
        mapping_secure_code=mapping_sc,
        is_deleted=False
    ).all()
    return check_mapping_permission(ctx, perms)


def _build_unit_ancestors(unit_sc, ancestors, org_sc):
    """遞迴建立部門/群組祖先鏈（含自身），用於 include_children 判斷"""
    from app.models import OrganizationalUnit

    visited = set()
    current = unit_sc
    while current and current not in visited:
        visited.add(current)
        ancestors.add(current)
        unit = OrganizationalUnit.query.filter_by(
            secure_code=current,
            org_secure_code=org_sc,
            is_deleted=False
        ).first()
        if not unit or not unit.parent_secure_code:
            break
        current = unit.parent_secure_code
    if current and current not in ancestors:
        ancestors.add(current)
    # 虛擬企業根 -- 讓 grant_target='__ORG_ROOT__' + include_children 匹配所有單位
    ancestors.add('__ORG_ROOT__')
