"""
NoCode Builder - Template API
頁面模板 CRUD API
"""
import logging

from flask import jsonify, request
from flask_babel import gettext as _
from flask_login import current_user

from app import csrf, db
from app.security.decorators import admin_required
from app.security.resource_gateway import ResourceGateway

from . import api_bp

logger = logging.getLogger(__name__)


# =============================================================================
# Template CRUD
# =============================================================================

@api_bp.route('/templates', methods=['GET'])
@admin_required
def list_templates():
    """列出當前企業的所有模板"""
    try:
        from ..models import DcPageTemplate

        result = ResourceGateway.filter(
            DcPageTemplate,
            is_deleted=False,
            is_active=True,
            order_by='-created_at',
        )
        return jsonify({
            'success': True,
            'data': [t.to_dict() for t in result]
        })
    except Exception as e:
        db.session.rollback()
        logger.exception('[Template] list_templates error')
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/templates', methods=['POST'])
@csrf.exempt
@admin_required
def create_template():
    """儲存當前頁面為模板"""
    try:
        from ..models import DcPageTemplate

        data = request.get_json() or {}
        name = data.get('name', '').strip()
        if not name:
            return jsonify({'success': False, 'error': _('模板名稱為必填')}), 400

        layout_json = data.get('layout_json')
        if not layout_json:
            return jsonify({'success': False, 'error': _('缺少頁面佈局資料')}), 400

        category = data.get('category', '常用').strip() or '常用'

        template = ResourceGateway.create(
            DcPageTemplate,
            check_permission=False,
            name=name,
            description=data.get('description', ''),
            category=category,
            layout_json=layout_json,
            style_config=data.get('style_config', {}),
            thumbnail_svg=data.get('thumbnail_svg', ''),
            created_by_sc=current_user.secure_code,
            is_active=True,
        )
        ResourceGateway.commit()

        return jsonify({
            'success': True,
            'data': template.to_dict(),
            'message': _('模板已儲存')
        })
    except Exception as e:
        db.session.rollback()
        logger.exception('[Template] create_template error')
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/templates/<secure_code>', methods=['PUT'])
@csrf.exempt
@admin_required
def update_template(secure_code):
    """更新模板（名稱、描述）"""
    try:
        from ..models import DcPageTemplate

        template = ResourceGateway.get(
            DcPageTemplate, secure_code,
            raise_on_not_found=False,
            check_permission=False
        )
        if not template or template.is_deleted:
            return jsonify({'success': False, 'error': _('模板不存在')}), 404

        data = request.get_json() or {}
        update_fields = {}
        for field in ('name', 'description', 'category'):
            if field in data:
                update_fields[field] = data[field]

        if 'name' in update_fields and not update_fields['name'].strip():
            return jsonify({'success': False, 'error': _('名稱不可為空')}), 400

        ResourceGateway.update(template, check_permission=False, **update_fields)
        ResourceGateway.commit()

        return jsonify({
            'success': True,
            'data': template.to_dict(),
            'message': _('模板已更新')
        })
    except Exception as e:
        db.session.rollback()
        logger.exception('[Template] update_template error')
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/templates/<secure_code>', methods=['DELETE'])
@csrf.exempt
@admin_required
def delete_template(secure_code):
    """刪除模板（軟刪除）"""
    try:
        from ..models import DcPageTemplate

        template = ResourceGateway.get(
            DcPageTemplate, secure_code,
            raise_on_not_found=False,
            check_permission=False
        )
        if not template or template.is_deleted:
            return jsonify({'success': False, 'error': _('模板不存在')}), 404

        ResourceGateway.delete(template, check_permission=False, soft=True)
        ResourceGateway.commit()

        return jsonify({'success': True, 'message': _('模板已刪除')})
    except Exception as e:
        db.session.rollback()
        logger.exception('[Template] delete_template error')
        return jsonify({'success': False, 'error': str(e)}), 500
