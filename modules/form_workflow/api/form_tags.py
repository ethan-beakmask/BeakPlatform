"""
FormWorkflow Module - Form Tags API
表單標籤管理 API
"""
from flask import Blueprint, jsonify, request
from flask_login import current_user

from app.security.decorators import module_access_required
from app.platform.auth import require_permission
from app.platform.data import get_current_org
from app import db, csrf

form_tags_bp = Blueprint(
    'form_workflow_form_tags',
    __name__,
    url_prefix='/api/form-workflow/tags'
)


# =============================================================================
# GET -- 列出標籤
# =============================================================================

@form_tags_bp.route('', methods=['GET'])
@module_access_required('form_workflow')
def list_tags():
    """列出所有表單標籤"""
    from ..models import FwFormTag

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    tags = FwFormTag.query.filter_by(
        org_secure_code=org.secure_code,
        is_deleted=False
    ).order_by(FwFormTag.display_order, FwFormTag.created_at).all()

    return jsonify({
        'success': True,
        'data': [t.to_dict() for t in tags]
    })


# =============================================================================
# POST -- 建立標籤
# =============================================================================

@form_tags_bp.route('', methods=['POST'])
@csrf.exempt
@module_access_required('form_workflow')
@require_permission('form_workflow.admin')
def create_tag():
    """
    建立表單標籤

    Body:
        code: 標籤代碼
        name: 顯示名稱
        description: 說明
        color: 顏色（選填）
        display_order: 排序
    """
    from ..models import FwFormTag

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    data = request.get_json() or {}
    code = (data.get('code') or '').strip().upper()
    name = (data.get('name') or '').strip()

    if not code:
        return jsonify({'success': False, 'message': 'code 為必填'}), 400
    if not name:
        return jsonify({'success': False, 'message': 'name 為必填'}), 400

    existing = FwFormTag.query.filter_by(
        code=code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()
    if existing:
        return jsonify({'success': False, 'message': f'標籤代碼 {code} 已存在'}), 400

    user_name = getattr(current_user, 'display_name', '') or getattr(current_user, 'native_name', '') or ''

    tag = FwFormTag(
        org_secure_code=org.secure_code,
        code=code,
        name=name,
        description=(data.get('description') or '').strip(),
        color=(data.get('color') or '').strip(),
        display_order=int(data.get('display_order', 0)),
        created_by_name=user_name,
    )

    db.session.add(tag)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': '標籤已建立',
        'data': tag.to_dict()
    }), 201


# =============================================================================
# PUT -- 更新標籤
# =============================================================================

@form_tags_bp.route('/<secure_code>', methods=['PUT'])
@csrf.exempt
@module_access_required('form_workflow')
@require_permission('form_workflow.admin')
def update_tag(secure_code):
    """更新標籤"""
    from ..models import FwFormTag

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    tag = FwFormTag.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()
    if not tag:
        return jsonify({'success': False, 'message': '標籤不存在'}), 404

    data = request.get_json() or {}

    if 'code' in data:
        new_code = (data['code'] or '').strip().upper()
        if new_code and new_code != tag.code:
            existing = FwFormTag.query.filter_by(
                code=new_code,
                org_secure_code=org.secure_code,
                is_deleted=False
            ).first()
            if existing:
                return jsonify({'success': False, 'message': f'標籤代碼 {new_code} 已存在'}), 400
            tag.code = new_code

    if 'name' in data:
        tag.name = (data['name'] or '').strip()
    if 'description' in data:
        tag.description = (data['description'] or '').strip()
    if 'color' in data:
        tag.color = (data['color'] or '').strip()
    if 'display_order' in data:
        tag.display_order = int(data.get('display_order', 0))
    if 'is_active' in data:
        tag.is_active = bool(data['is_active'])

    db.session.commit()

    return jsonify({
        'success': True,
        'message': '標籤已更新',
        'data': tag.to_dict()
    })


# =============================================================================
# DELETE -- 刪除標籤
# =============================================================================

@form_tags_bp.route('/<secure_code>', methods=['DELETE'])
@csrf.exempt
@module_access_required('form_workflow')
@require_permission('form_workflow.admin')
def delete_tag(secure_code):
    """刪除標籤（軟刪除，同步清除關聯）"""
    from ..models import FwFormTag, FwFormTemplateTag

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    tag = FwFormTag.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()
    if not tag:
        return jsonify({'success': False, 'message': '標籤不存在'}), 404

    tag.is_deleted = True

    # 軟刪除關聯
    FwFormTemplateTag.query.filter_by(
        tag_secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).update({'is_deleted': True})

    db.session.commit()

    return jsonify({
        'success': True,
        'message': '標籤已刪除'
    })


# =============================================================================
# GET/PUT -- 表單模板的標籤關聯
# =============================================================================

@form_tags_bp.route('/template/<template_secure_code>', methods=['GET'])
@module_access_required('form_workflow')
def get_template_tags(template_secure_code):
    """取得表單模板的標籤"""
    from ..models import FwFormTemplateTag, FwFormTag

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    links = FwFormTemplateTag.query.filter_by(
        form_template_secure_code=template_secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).all()

    tag_scs = [link.tag_secure_code for link in links]

    tags = []
    if tag_scs:
        tags = FwFormTag.query.filter(
            FwFormTag.secure_code.in_(tag_scs),
            FwFormTag.org_secure_code == org.secure_code,
            FwFormTag.is_deleted == False
        ).order_by(FwFormTag.display_order).all()

    return jsonify({
        'success': True,
        'data': [t.to_dict() for t in tags]
    })


@form_tags_bp.route('/template/<template_secure_code>', methods=['PUT'])
@csrf.exempt
@module_access_required('form_workflow')
@require_permission('form_workflow.admin')
def set_template_tags(template_secure_code):
    """
    設定表單模板的標籤（整批替換）

    Body:
        tag_secure_codes: [sc1, sc2, ...]
    """
    from ..models import FwFormTemplateTag

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    data = request.get_json() or {}
    new_tag_scs = set(data.get('tag_secure_codes') or [])

    # 取得現有關聯
    existing_links = FwFormTemplateTag.query.filter_by(
        form_template_secure_code=template_secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).all()
    existing_scs = {link.tag_secure_code for link in existing_links}

    # 需要刪除的
    to_remove = existing_scs - new_tag_scs
    for link in existing_links:
        if link.tag_secure_code in to_remove:
            link.is_deleted = True

    # 需要新增的
    to_add = new_tag_scs - existing_scs
    for tag_sc in to_add:
        link = FwFormTemplateTag(
            org_secure_code=org.secure_code,
            form_template_secure_code=template_secure_code,
            tag_secure_code=tag_sc,
        )
        db.session.add(link)

    db.session.commit()

    return jsonify({
        'success': True,
        'message': '標籤已更新'
    })
