"""
表單中心 - 可用表單列表
"""
from flask import jsonify
from flask_login import current_user

from app.security.decorators import module_access_required
from app.platform.data import get_current_org
from app import db

from .form_center import form_center_bp


@form_center_bp.route('/available-forms')
@module_access_required('form_workflow', False)
def list_available_forms():
    """
    取得可填寫的表單列表

    權限控制：
    - 硬編碼預設：SYSTEM_ADMIN / FLOW_DESIGNER 角色 / FORM_DESIGNER 角色 -> 全部可見
    - 已發行表單：依 fw_mapping_permissions 過濾（無記錄 = 僅預設角色可見）
    - 測試表單：管理員 or design.tryout 權限可見

    回傳格式：
    - _status: 'published' (已發行) 或 'test' (測試中)
    - _source: 'published' (來自快照) 或 'mapping' (來自設計稿)
    """
    from ..models import (
        FwPublishedFormWorkflow, FwFormWorkflowMapping,
        FwFormTemplate, FwWorkflowTemplate, FwMappingPermission
    )

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    # 判斷是否可見測試表單（管理員 or 有 design.tryout 權限）
    from app.platform.auth import has_permission, get_user_roles
    is_admin = (
        getattr(current_user, 'is_org_admin', False) or
        has_permission('form_workflow.design.tryout')
    )

    # =========================================================================
    # 填寫權限判斷：硬編碼預設角色
    # =========================================================================
    HARDCODED_ROLE_CODES = {'FLOW_DESIGNER', 'FORM_DESIGNER'}
    user_type = str(getattr(current_user, 'user_type', ''))
    user_role_codes = {r['code'] for r in get_user_roles(current_user)}
    is_hardcoded_allowed = (
        user_type == 'SYSTEM_ADMIN' or
        bool(user_role_codes & HARDCODED_ROLE_CODES)
    )
    is_external = (user_type == 'EXTERNAL')

    # =========================================================================
    # 若非硬編碼角色，預載權限資料與用戶身份
    # =========================================================================
    perm_map = {}  # mapping_secure_code -> [FwMappingPermission, ...]
    user_dept_sc = None
    user_dept_ancestors = set()  # 用戶部門所在的祖先鏈
    user_group_scs = set()
    user_group_ancestors = set()  # 用戶群組的祖先鏈（含自身）

    if not is_hardcoded_allowed:
        # 載入所有配對權限
        all_perms = FwMappingPermission.query.filter_by(
            org_secure_code=org.secure_code,
            is_deleted=False
        ).all()
        for p in all_perms:
            perm_map.setdefault(p.mapping_secure_code, []).append(p)

        # 用戶主要部門
        user_dept_sc = getattr(current_user, 'primary_unit_secure_code', None)

        # 用戶所屬群組（透過 membership）
        from app.models import UserUnitMembership, OrganizationalUnit
        user_group_scs = set(
            m.unit_secure_code for m in UserUnitMembership.query.filter_by(
                user_secure_code=current_user.secure_code,
                org_secure_code=org.secure_code,
                is_deleted=False
            ).join(
                OrganizationalUnit,
                OrganizationalUnit.secure_code == UserUnitMembership.unit_secure_code
            ).filter(
                OrganizationalUnit.unit_type == 'GROUP',
                OrganizationalUnit.is_deleted == False
            ).all()
        )

        # 建立部門祖先鏈（用於 include_children 判斷）
        if user_dept_sc:
            from app.models import OrganizationalUnit
            _build_dept_ancestors(user_dept_sc, user_dept_ancestors, org.secure_code)

        # 建立群組祖先鏈（用於群組 include_children 判斷）
        for gsc in user_group_scs:
            _build_group_ancestors(gsc, user_group_ancestors, org.secure_code)

    def _check_mapping_permission(mapping_sc):
        """檢查當前用戶是否有權填寫此配對的表單"""
        if is_hardcoded_allowed:
            return True

        perms = perm_map.get(mapping_sc)
        if not perms:
            return False  # 無自訂規則，僅硬編碼角色可用

        for p in perms:
            if p.grant_type == 'user':
                if is_external:
                    continue  # EXTERNAL 不能透過 user 類型授權
                if p.grant_target == current_user.secure_code:
                    return True

            elif p.grant_type == 'department':
                if is_external:
                    continue  # EXTERNAL 不能透過 department 授權
                if not user_dept_sc:
                    continue
                if p.include_children:
                    # 用戶部門在此部門的子樹中（grant_target 是祖先之一）
                    if p.grant_target in user_dept_ancestors:
                        return True
                else:
                    if p.grant_target == user_dept_sc:
                        return True

            elif p.grant_type == 'group':
                if not user_group_scs:
                    continue
                if p.include_children:
                    # grant_target 是用戶群組的祖先之一（含 __ORG_ROOT__）
                    if p.grant_target in user_group_ancestors:
                        return True
                else:
                    if p.grant_target == '__ORG_ROOT__':
                        # 虛擬企業根（不含下層）-- 有任一群組成員身份即匹配
                        return True
                    elif p.grant_target in user_group_scs:
                        return True

        return False

    # 預先載入分類映射（category_secure_code -> parent info）
    from ..models import FwCategory
    all_cats = FwCategory.query.filter_by(is_deleted=False).filter(
        db.or_(
            FwCategory.org_secure_code.is_(None),
            FwCategory.org_secure_code == org.secure_code
        )
    ).all()
    cat_map = {c.secure_code: c for c in all_cats}

    def _enrich_category(item, cat_sc):
        """補充分類資訊到 item"""
        item['category_secure_code'] = cat_sc
        cat = cat_map.get(cat_sc) if cat_sc else None
        if cat and cat.parent_secure_code:
            parent = cat_map.get(cat.parent_secure_code)
            item['parent_category_secure_code'] = cat.parent_secure_code
            item['parent_category_name'] = parent.name if parent else ''
            item['child_category_name'] = cat.name
        elif cat:
            item['parent_category_secure_code'] = cat.secure_code
            item['parent_category_name'] = cat.name
            item['child_category_name'] = None
        else:
            item['parent_category_secure_code'] = None
            item['parent_category_name'] = None
            item['child_category_name'] = None

    result = []
    seen_mapping_ids = set()
    need_category_ids = []  # 需要 fallback 查 category 的 form_template_id

    # 預查 mapping_id -> mapping_secure_code 映射（用於權限查詢）
    all_mappings_for_org = FwFormWorkflowMapping.query.filter_by(
        org_secure_code=org.secure_code,
        is_deleted=False
    ).all()
    mapping_id_to_sc = {m.id: m.secure_code for m in all_mappings_for_org}

    # 1. 優先顯示已發行版本（從快照取得，設計稿刪除不影響）
    published_list = FwPublishedFormWorkflow.query.filter_by(
        org_secure_code=org.secure_code,
        status='Published',
        is_deleted=False
    ).order_by(FwPublishedFormWorkflow.published_at.desc()).all()

    for p in published_list:
        mapping_id = p.source_mapping_id
        if mapping_id in seen_mapping_ids:
            continue
        seen_mapping_ids.add(mapping_id)

        # 權限過濾：檢查用戶是否有權填寫此配對
        mapping_sc = p.source_mapping_secure_code or mapping_id_to_sc.get(mapping_id)
        if not _check_mapping_permission(mapping_sc):
            continue

        form_snapshot = p.form_snapshot or {}
        workflow_snapshot = p.workflow_snapshot or {}
        category = form_snapshot.get('category')
        cat_sc = form_snapshot.get('category_secure_code')

        item = {
            'id': p.source_form_template_id,
            'secure_code': p.secure_code,
            'name': form_snapshot.get('name') or p.name,
            'description': form_snapshot.get('description') or p.description,
            'category': category,
            'code': form_snapshot.get('code'),
            'version': form_snapshot.get('version'),
            'publish_version': p.publish_version,
            'published_at': p.published_at.isoformat() if p.published_at else None,
            'workflow_template_name': workflow_snapshot.get('name'),
            'mapping_id': mapping_id,
            '_status': 'published',
            '_source': 'published',
        }

        # 嘗試從快照取 category_secure_code
        if cat_sc:
            _enrich_category(item, cat_sc)
        else:
            # fallback 待後面批次處理
            item['category_secure_code'] = None
            item['parent_category_secure_code'] = None
            item['parent_category_name'] = None
            item['child_category_name'] = None
            if p.source_form_template_id:
                need_category_ids.append((len(result), p.source_form_template_id))

        result.append(item)

    # category fallback: 快照沒有 category_secure_code 時查 FwFormTemplate
    if need_category_ids:
        ft_ids = list(set(fid for _, fid in need_category_ids))
        templates = FwFormTemplate.query.filter(
            FwFormTemplate.id.in_(ft_ids)
        ).all()
        ft_map = {t.id: t for t in templates}
        for idx, ft_id in need_category_ids:
            ft = ft_map.get(ft_id)
            if ft:
                result[idx]['category'] = ft.category
                _enrich_category(result[idx], ft.category_secure_code)

    # 2. 管理員額外顯示未發行的配對（用於測試）
    if is_admin:
        mappings = FwFormWorkflowMapping.query.filter_by(
            org_secure_code=org.secure_code,
            is_active=True,
            is_deleted=False
        ).order_by(FwFormWorkflowMapping.created_at.desc()).all()

        for mapping in mappings:
            form_template = FwFormTemplate.query.filter_by(
                id=mapping.form_template_id,
                is_deleted=False,
                is_active=True
            ).first()

            workflow_template = FwWorkflowTemplate.query.filter_by(
                id=mapping.workflow_template_id,
                is_deleted=False,
                is_subprocess=False
            ).first()

            if not form_template or not workflow_template:
                continue

            item = {
                'id': form_template.id,
                'secure_code': form_template.secure_code,
                'name': form_template.name,
                'description': form_template.description,
                'category': form_template.category,
                'code': form_template.code,
                'version': form_template.version,
                'mapping_id': mapping.id,
                'mapping_secure_code': mapping.secure_code,
                'workflow_template_id': workflow_template.id,
                'workflow_template_name': workflow_template.name,
                'workflow_template_secure_code': workflow_template.secure_code,
                '_status': 'test',
                '_source': 'mapping',
            }
            _enrich_category(item, form_template.category_secure_code)
            result.append(item)

    return jsonify({
        'success': True,
        'data': result,
        'is_admin': is_admin
    })


def _build_dept_ancestors(dept_sc, ancestors, org_sc):
    """遞迴建立部門祖先鏈（含自身），用於 include_children 判斷"""
    from app.models import OrganizationalUnit

    visited = set()
    current = dept_sc
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
    # 加入最終的根部門
    if current and current not in ancestors:
        ancestors.add(current)
    # 虛擬企業根 -- 讓 grant_target='__ORG_ROOT__' + include_children 匹配所有部門
    ancestors.add('__ORG_ROOT__')


def _build_group_ancestors(group_sc, ancestors, org_sc):
    """遞迴建立群組祖先鏈（含自身），用於群組 include_children 判斷"""
    from app.models import OrganizationalUnit

    visited = set()
    current = group_sc
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
    # 虛擬企業根 -- 讓 grant_target='__ORG_ROOT__' + include_children 匹配所有群組
    ancestors.add('__ORG_ROOT__')
