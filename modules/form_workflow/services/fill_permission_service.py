"""
表單填寫權限解析 -- FwMappingPermission 共用檢查邏輯

供表單中心列表 (fc_available)、送單 (fc_fill submit) 與 API Key 申請單
(PF-160：授權表單選項 + ApiKeyIssue 核發前重驗) 共用，
確保「看得到」「送得出」「申請得到 key」使用同一套授權判斷。

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


def list_fillable_published_templates(user, org_sc):
    """
    列出該使用者「可填寫且有 Published 版本」的表單模板。

    PF-160 的規則「你能手動填的表單，才能申請 key 去自動填」就是這一支：
    API Key 申請單的授權表單選項（fc_available.list_fillable_form_templates）
    與核發前的重驗（ApiKeyIssue handler）共用它，避免兩邊判定漂移。

    Args:
        user: 被判定的使用者（代申請時是「被代申請人」，不是送單人）
        org_sc: 企業 secure_code（TENANT-01）

    Returns:
        list[dict]: secure_code 為 fw_form_templates.secure_code（穩定、不隨發行
            改變），對應 api_keys.scopes.form_template
    """
    from app import db
    from ..models import (
        FwCategory, FwFormWorkflowMapping, FwMappingPermission,
        FwPublishedFormWorkflow,
    )
    from .security_center import is_security_category

    ctx = build_fill_permission_context(user, org_sc)

    perm_map = {}  # mapping_secure_code -> [FwMappingPermission, ...]
    if not ctx['is_hardcoded']:
        for p in FwMappingPermission.query.filter_by(
            org_secure_code=org_sc, is_deleted=False
        ).all():
            perm_map.setdefault(p.mapping_secure_code, []).append(p)

    mapping_id_to_sc = {
        m.id: m.secure_code
        for m in FwFormWorkflowMapping.query.filter_by(
            org_secure_code=org_sc, is_deleted=False
        ).all()
    }

    cat_map = {
        c.secure_code: c
        for c in FwCategory.query.filter_by(is_deleted=False).filter(
            db.or_(
                FwCategory.org_secure_code.is_(None),
                FwCategory.org_secure_code == org_sc,
            )
        ).all()
    }

    # 每張表單模板只取最新一筆 Published，與 external_trigger 的
    # _resolve_published_by_form_code() 同一個取法（created_at desc）--
    # 外部觸發實際會用到的就是那一筆，判定對象必須一致
    published_list = FwPublishedFormWorkflow.query.filter_by(
        org_secure_code=org_sc,
        status='Published',
        is_deleted=False,
    ).order_by(FwPublishedFormWorkflow.created_at.desc()).all()

    result = []
    seen_template_scs = set()
    for p in published_list:
        template_sc = p.source_form_template_secure_code
        if not template_sc or template_sc in seen_template_scs:
            continue
        seen_template_scs.add(template_sc)

        mapping_sc = p.source_mapping_secure_code or mapping_id_to_sc.get(
            p.source_mapping_id)
        if not check_mapping_permission(ctx, perm_map.get(mapping_sc)):
            continue

        form_snapshot = p.form_snapshot or {}
        cat_sc = form_snapshot.get('category_secure_code')
        # 資安分類表單由處置中心 / intake 專用鏈路承接，不是使用者手動填的對象，
        # 與表單中心清單採同一條隔離規則
        if is_security_category(cat_sc):
            continue

        cat = cat_map.get(cat_sc) if cat_sc else None
        result.append({
            'secure_code': template_sc,
            'name': form_snapshot.get('name') or p.name,
            'code': form_snapshot.get('code'),
            'description': form_snapshot.get('description') or p.description,
            'category_secure_code': cat_sc,
            'category_name': cat.name if cat else form_snapshot.get('category'),
        })

    result.sort(key=lambda i: (i.get('category_name') or '', i.get('name') or ''))
    return result
