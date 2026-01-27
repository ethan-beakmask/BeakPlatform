"""
FormWorkflow Module - Categories API
表單流程分類管理 API
"""
from flask import Blueprint, jsonify, request
from flask_login import current_user

from app.security.decorators import login_required
from app.platform.data import get_current_org
from app import db, csrf

# 建立 API Blueprint
categories_bp = Blueprint(
    'form_workflow_categories',
    __name__,
    url_prefix='/api/form-workflow/categories'
)


# =============================================================================
# 公開 API - 一般使用者
# =============================================================================

@categories_bp.route('', methods=['GET'])
@login_required
def list_categories():
    """
    列出當前使用者可見的分類

    Query Parameters:
        context: 使用情境 (form_design, workflow_design, form_center)
    """
    from ..models import FwCategory

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    context = request.args.get('context', '')

    # 查詢：系統分類 + 當前企業分類
    query = FwCategory.query.filter_by(is_deleted=False).filter(
        db.or_(
            FwCategory.org_secure_code.is_(None),  # 系統分類
            FwCategory.org_secure_code == org.secure_code  # 企業分類
        )
    )

    # 根據情境過濾
    if context == 'form_design':
        query = query.filter(FwCategory.show_in_form_design == True)
    elif context == 'workflow_design':
        query = query.filter(FwCategory.show_in_workflow_design == True)
    elif context == 'form_center':
        query = query.filter(FwCategory.show_in_form_center == True)

    categories = query.order_by(FwCategory.display_order, FwCategory.name).all()

    return jsonify({
        'success': True,
        'data': [cat.to_dict() for cat in categories]
    })


@categories_bp.route('/<secure_code>', methods=['GET'])
@login_required
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
        return jsonify({'success': False, 'message': '分類不存在'}), 404

    # 檢查權限
    if category.org_secure_code and category.org_secure_code != org.secure_code:
        return jsonify({'success': False, 'message': '無權查看此分類'}), 403

    return jsonify({
        'success': True,
        'data': category.to_dict()
    })


# =============================================================================
# 管理 API
# =============================================================================

@categories_bp.route('', methods=['POST'])
@csrf.exempt
@login_required
def create_category():
    """建立分類"""
    from ..models import FwCategory

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    data = request.get_json() or {}

    if not data.get('name'):
        return jsonify({'success': False, 'message': '分類名稱為必填'}), 400

    # 檢查名稱是否已存在
    existing = FwCategory.query.filter_by(
        name=data['name'],
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()
    if existing:
        return jsonify({'success': False, 'message': f'分類「{data["name"]}」已存在'}), 400

    try:
        category = FwCategory(
            org_secure_code=org.secure_code,
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
            'message': '分類建立成功',
            'data': category.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'建立失敗: {str(e)}'}), 500


@categories_bp.route('/<secure_code>', methods=['PUT'])
@csrf.exempt
@login_required
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
        return jsonify({'success': False, 'message': '分類不存在'}), 404

    # 系統分類不允許企業修改
    if category.is_system:
        return jsonify({'success': False, 'message': '系統內建分類無法修改'}), 403

    # 只能修改自己企業的分類
    if category.org_secure_code != org.secure_code:
        return jsonify({'success': False, 'message': '無權修改此分類'}), 403

    data = request.get_json() or {}

    try:
        # 更新名稱時檢查是否重複
        if 'name' in data and data['name'] != category.name:
            existing = FwCategory.query.filter_by(
                name=data['name'],
                org_secure_code=org.secure_code,
                is_deleted=False
            ).first()
            if existing and existing.id != category.id:
                return jsonify({'success': False, 'message': f'分類「{data["name"]}」已存在'}), 400

            # 同步更新使用此分類的表單和流程
            from ..models import FwFormTemplate, FwWorkflowTemplate
            old_name = category.name
            FwFormTemplate.query.filter_by(
                category=old_name,
                org_secure_code=org.secure_code
            ).update({'category': data['name']})
            FwWorkflowTemplate.query.filter_by(
                category=old_name,
                org_secure_code=org.secure_code
            ).update({'category': data['name']})

            category.name = data['name']

        if 'description' in data:
            category.description = data['description']
        if 'display_order' in data:
            category.display_order = data['display_order']
        if 'show_in_form_design' in data:
            category.show_in_form_design = data['show_in_form_design']
        if 'show_in_workflow_design' in data:
            category.show_in_workflow_design = data['show_in_workflow_design']
        if 'show_in_form_center' in data:
            category.show_in_form_center = data['show_in_form_center']

        db.session.commit()

        return jsonify({
            'success': True,
            'message': '分類更新成功',
            'data': category.to_dict()
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'更新失敗: {str(e)}'}), 500


@categories_bp.route('/<secure_code>', methods=['DELETE'])
@csrf.exempt
@login_required
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
        return jsonify({'success': False, 'message': '分類不存在'}), 404

    # 只能刪除自己企業的分類
    if category.org_secure_code != org.secure_code:
        return jsonify({'success': False, 'message': '無權刪除此分類'}), 403

    can_delete, message = category.can_delete(org.secure_code)
    if not can_delete:
        return jsonify({'success': False, 'message': message}), 400

    try:
        category.is_deleted = True
        db.session.commit()

        return jsonify({
            'success': True,
            'message': '分類已刪除'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'刪除失敗: {str(e)}'}), 500


@categories_bp.route('/reorder', methods=['POST'])
@csrf.exempt
@login_required
def reorder_categories():
    """重新排序分類"""
    from ..models import FwCategory

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    data = request.get_json() or {}
    order = data.get('order', [])

    if not order:
        return jsonify({'success': False, 'message': '排序清單不可為空'}), 400

    try:
        for index, secure_code in enumerate(order):
            category = FwCategory.query.filter_by(
                secure_code=secure_code,
                org_secure_code=org.secure_code,
                is_deleted=False
            ).first()
            if category:
                category.display_order = index

        db.session.commit()

        return jsonify({
            'success': True,
            'message': '排序已更新'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'排序失敗: {str(e)}'}), 500
