"""
FormWorkflow Module - Categories API
表單流程分類管理 API（二層結構）
"""
from flask import Blueprint, jsonify, request
from flask_login import current_user

from app.security.decorators import module_access_required, page_keys_required
from app.platform.auth import require_any_permission
from app.platform.data import get_current_org
from app import db, csrf
from flask_babel import gettext as _

# 建立 API Blueprint
categories_bp = Blueprint(
    'form_workflow_categories',
    __name__,
    url_prefix='/api/form-workflow/categories'
)


def _build_tree(parents, children_map, context=None):
    """組裝樹狀結構"""
    tree = []
    for p in parents:
        d = p.to_dict()
        kids = children_map.get(p.secure_code, [])
        d['children'] = [c.to_dict() for c in kids]
        tree.append(d)
    return tree


# =============================================================================
# GET — 列出分類（預設樹狀）
# =============================================================================

@categories_bp.route('', methods=['GET'])
@module_access_required('form_workflow')
def list_categories():
    """
    列出分類

    Query Parameters:
        context: 使用情境 (form_design, workflow_design, form_center)
        parent: 若指定父分類 secure_code，只回傳該父分類的子分類
        flat: 若為 1，回傳扁平清單（不組裝樹狀）
    """
    from ..models import FwCategory

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    context = request.args.get('context', '')
    parent_sc = request.args.get('parent')
    flat = request.args.get('flat') == '1'

    # 基礎查詢
    query = FwCategory.query.filter_by(is_deleted=False).filter(
        db.or_(
            FwCategory.org_secure_code.is_(None),
            FwCategory.org_secure_code == org.secure_code
        )
    )

    # 根據情境過濾（只對父分類生效）
    if context == 'form_design':
        query = query.filter(
            db.or_(
                FwCategory.parent_secure_code.isnot(None),
                FwCategory.show_in_form_design == True
            )
        )
    elif context == 'workflow_design':
        query = query.filter(
            db.or_(
                FwCategory.parent_secure_code.isnot(None),
                FwCategory.show_in_workflow_design == True
            )
        )
    elif context == 'form_center':
        query = query.filter(
            db.or_(
                FwCategory.parent_secure_code.isnot(None),
                FwCategory.show_in_form_center == True
            )
        )

    # 只取某父分類下的子分類
    if parent_sc:
        children = query.filter(
            FwCategory.parent_secure_code == parent_sc
        ).order_by(FwCategory.display_order, FwCategory.name).all()
        return jsonify({'success': True, 'data': [c.to_dict() for c in children]})

    all_cats = query.order_by(FwCategory.display_order, FwCategory.name).all()

    if flat:
        return jsonify({'success': True, 'data': [c.to_dict() for c in all_cats]})

    # 組裝樹狀結構
    parents = [c for c in all_cats if c.is_parent]
    children_map = {}
    for c in all_cats:
        if c.is_child:
            children_map.setdefault(c.parent_secure_code, []).append(c)

    tree = _build_tree(parents, children_map, context)

    return jsonify({'success': True, 'data': tree})


@categories_bp.route('/<secure_code>', methods=['GET'])
@module_access_required('form_workflow')
def get_category(secure_code):
    """取得單一分類"""
    from ..models import FwCategory

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    category = FwCategory.query.filter_by(
        secure_code=secure_code,
        is_deleted=False
    ).first()

    if not category:
        return jsonify({'success': False, 'message': _('分類不存在')}), 404

    if category.org_secure_code and category.org_secure_code != org.secure_code:
        return jsonify({'success': False, 'message': _('無權查看此分類')}), 403

    data = category.to_dict()

    # 若為父分類，附加子分類
    if category.is_parent:
        children = FwCategory.query.filter_by(
            parent_secure_code=category.secure_code,
            is_deleted=False
        ).order_by(FwCategory.display_order, FwCategory.name).all()
        data['children'] = [c.to_dict() for c in children]

    return jsonify({'success': True, 'data': data})


# =============================================================================
# POST — 建立分類
# =============================================================================

@categories_bp.route('', methods=['POST'])
@csrf.exempt
@module_access_required('form_workflow')
@page_keys_required('form_workflow.categories')
@require_any_permission('form_workflow.admin', 'form_workflow.template.manage', 'form_workflow.workflow.manage')
def create_category():
    """
    建立分類

    Body:
        name: 分類名稱（必填）
        description: 描述
        parent_secure_code: 父分類 secure_code（有值 → 建立子分類；無值 → 建立父分類）
        display_order: 排序
        show_in_form_design / show_in_workflow_design / show_in_form_center: 顯示開關（父分類用）
    """
    from ..models import FwCategory

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    data = request.get_json() or {}

    if not data.get('name'):
        return jsonify({'success': False, 'message': _('分類名稱為必填')}), 400

    parent_sc = data.get('parent_secure_code')

    # 若建立子分類，驗證父分類存在
    if parent_sc:
        parent = FwCategory.query.filter_by(
            secure_code=parent_sc,
            is_deleted=False
        ).first()
        if not parent:
            return jsonify({'success': False, 'message': _('指定的父分類不存在')}), 400
        if parent.is_child:
            return jsonify({'success': False, 'message': _('不支援三層分類')}), 400

    # 檢查同層名稱是否已存在
    dup_query = FwCategory.query.filter_by(
        name=data['name'],
        is_deleted=False
    )
    if parent_sc:
        dup_query = dup_query.filter_by(parent_secure_code=parent_sc)
    else:
        dup_query = dup_query.filter(FwCategory.parent_secure_code.is_(None))

    # 同企業或系統分類
    dup_query = dup_query.filter(
        db.or_(
            FwCategory.org_secure_code == org.secure_code,
            FwCategory.org_secure_code.is_(None)
        )
    )

    if dup_query.first():
        return jsonify({'success': False, 'message': _('分類「%(name)s」已存在', name=data["name"])}), 400

    try:
        category = FwCategory(
            org_secure_code=org.secure_code,
            parent_secure_code=parent_sc,
            name=data['name'],
            description=data.get('description', ''),
            display_order=data.get('display_order', 0),
            is_system=False,
            show_in_form_design=data.get('show_in_form_design', True),
            show_in_workflow_design=data.get('show_in_workflow_design', True),
            show_in_form_center=data.get('show_in_form_center', True),
        )

        db.session.add(category)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': _('分類建立成功'),
            'data': category.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': _('建立失敗: %(error)s', error=str(e))}), 500


# =============================================================================
# PUT — 更新分類
# =============================================================================

@categories_bp.route('/<secure_code>', methods=['PUT'])
@csrf.exempt
@module_access_required('form_workflow')
@page_keys_required('form_workflow.categories')
@require_any_permission('form_workflow.admin', 'form_workflow.template.manage', 'form_workflow.workflow.manage')
def update_category(secure_code):
    """更新分類"""
    from ..models import FwCategory

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    category = FwCategory.query.filter_by(
        secure_code=secure_code,
        is_deleted=False
    ).first()

    if not category:
        return jsonify({'success': False, 'message': _('分類不存在')}), 404

    if category.is_system:
        return jsonify({'success': False, 'message': _('系統內建分類無法修改')}), 403

    if category.org_secure_code != org.secure_code:
        return jsonify({'success': False, 'message': _('無權修改此分類')}), 403

    data = request.get_json() or {}

    try:
        # 更新名稱時檢查同層是否重複
        if 'name' in data and data['name'] != category.name:
            dup_query = FwCategory.query.filter_by(
                name=data['name'],
                parent_secure_code=category.parent_secure_code,
                is_deleted=False
            ).filter(
                db.or_(
                    FwCategory.org_secure_code == org.secure_code,
                    FwCategory.org_secure_code.is_(None)
                )
            )
            existing = dup_query.first()
            if existing and existing.id != category.id:
                return jsonify({'success': False, 'message': _('分類「%(name)s」已存在', name=data["name"])}), 400
            category.name = data['name']

        if 'description' in data:
            category.description = data['description']
        if 'display_order' in data:
            category.display_order = data['display_order']

        # 顯示開關（僅父分類有意義）
        if category.is_parent:
            if 'show_in_form_design' in data:
                category.show_in_form_design = data['show_in_form_design']
            if 'show_in_workflow_design' in data:
                category.show_in_workflow_design = data['show_in_workflow_design']
            if 'show_in_form_center' in data:
                category.show_in_form_center = data['show_in_form_center']

        db.session.commit()

        return jsonify({
            'success': True,
            'message': _('分類更新成功'),
            'data': category.to_dict()
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': _('更新失敗: %(error)s', error=str(e))}), 500


# =============================================================================
# DELETE — 刪除分類
# =============================================================================

@categories_bp.route('/<secure_code>', methods=['DELETE'])
@csrf.exempt
@module_access_required('form_workflow')
@page_keys_required('form_workflow.categories')
@require_any_permission('form_workflow.admin', 'form_workflow.template.manage', 'form_workflow.workflow.manage')
def delete_category(secure_code):
    """刪除分類"""
    from ..models import FwCategory

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    category = FwCategory.query.filter_by(
        secure_code=secure_code,
        is_deleted=False
    ).first()

    if not category:
        return jsonify({'success': False, 'message': _('分類不存在')}), 404

    if category.org_secure_code != org.secure_code:
        return jsonify({'success': False, 'message': _('無權刪除此分類')}), 403

    can_delete, message = category.can_delete(org.secure_code)
    if not can_delete:
        return jsonify({'success': False, 'message': message}), 400

    try:
        category.is_deleted = True
        db.session.commit()

        return jsonify({
            'success': True,
            'message': _('分類已刪除')
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': _('刪除失敗: %(error)s', error=str(e))}), 500


# =============================================================================
# POST /reorder — 同層排序
# =============================================================================

@categories_bp.route('/reorder', methods=['POST'])
@csrf.exempt
@module_access_required('form_workflow')
@page_keys_required('form_workflow.categories')
@require_any_permission('form_workflow.admin', 'form_workflow.template.manage', 'form_workflow.workflow.manage')
def reorder_categories():
    """
    重新排序分類（同層內）

    Body:
        order: [secure_code, ...]  同層分類的排序
        parent_secure_code: 父分類 secure_code（null 表示排序第一層）
    """
    from ..models import FwCategory

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    data = request.get_json() or {}
    order = data.get('order', [])

    if not order:
        return jsonify({'success': False, 'message': _('排序清單不可為空')}), 400

    try:
        for index, sc in enumerate(order):
            category = FwCategory.query.filter_by(
                secure_code=sc,
                is_deleted=False
            ).first()
            if category and (
                category.org_secure_code == org.secure_code or
                category.org_secure_code is None
            ):
                category.display_order = index

        db.session.commit()

        return jsonify({
            'success': True,
            'message': _('排序已更新')
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': _('排序失敗: %(error)s', error=str(e))}), 500
