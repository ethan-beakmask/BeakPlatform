"""
NoCode Builder - Template API
頁面模板 CRUD API
"""
import logging

from flask import jsonify, request
from flask_babel import gettext as _
from flask_login import current_user

from app import csrf, db
from app.pageir import validate_page_ir
from app.security.decorators import admin_required
from app.security.resource_gateway import ResourceGateway
from app.security.tenant_isolation import get_current_tenant

from . import api_bp
from ..services.page_template_service import sanitize_template_ir

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

        sub_system_sc = (request.args.get('sub_system') or '').strip()
        common = dict(is_deleted=False, is_active=True, order_by='-created_at')

        # scope 已鎖死為 system 且這些列 org_secure_code 為 NULL，跳過租戶過濾不會外洩企業資料。
        system_items = ResourceGateway.filter(
            DcPageTemplate,
            skip_tenant_filter=True,
            scope='system',
            **common,
        )
        org_items = ResourceGateway.filter(DcPageTemplate, scope='org', **common)
        sub_items = []
        if sub_system_sc:
            sub_items = ResourceGateway.filter(
                DcPageTemplate,
                scope='sub_system',
                sub_system_secure_code=sub_system_sc,
                **common,
            )

        scope_weight = {'system': 0, 'org': 1, 'sub_system': 2}
        result = sorted(
            [*system_items, *org_items, *sub_items],
            key=lambda t: (
                scope_weight.get(t.scope, 99),
                -(t.created_at.timestamp() if t.created_at else 0),
            ),
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
        from ..models import DcPageTemplate, DcSubSystem

        data = request.get_json() or {}
        raw_scope = data.get('scope') or 'org'
        scope = raw_scope.strip() if isinstance(raw_scope, str) else ''
        sub_system_sc = (data.get('sub_system_secure_code') or '').strip()
        source_sub_system_sc = (data.get('source_sub_system_sc') or '').strip()
        if scope == 'system':
            return jsonify({'success': False, 'error': _('內建樣板只能由平台種子腳本建立')}), 403
        if scope not in {'org', 'sub_system'}:
            return jsonify({'success': False, 'error': _('樣板範圍不正確')}), 400

        name = data.get('name', '').strip()
        if not name:
            return jsonify({'success': False, 'error': _('模板名稱為必填')}), 400
        if scope == 'sub_system':
            if not sub_system_sc:
                return jsonify({'success': False, 'error': _('子系統 secure_code 為必填')}), 400
            sub = ResourceGateway.get(
                DcSubSystem,
                sub_system_sc,
                raise_on_not_found=False,
                check_permission=False,
            )
            if not sub or sub.is_deleted:
                return jsonify({'success': False, 'error': _('子系統不存在')}), 404
            if not source_sub_system_sc:
                source_sub_system_sc = sub_system_sc

        layout_json = data.get('layout_json')
        if not layout_json:
            return jsonify({'success': False, 'error': _('缺少頁面佈局資料')}), 400

        ok, errors = validate_page_ir(layout_json)
        if not ok:
            return jsonify({
                'success': False,
                'error': _('Page IR validation failed'),
                'errors': errors,
            }), 400

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
            scope=scope,
            sub_system_secure_code=sub_system_sc if scope == 'sub_system' else None,
            source_sub_system_sc=source_sub_system_sc or None,
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


@api_bp.route('/templates/<secure_code>/instantiate', methods=['POST'])
@csrf.exempt
@admin_required
def instantiate_template(secure_code):
    """以頁面樣板建立新頁面。"""
    try:
        from ..models import DcPageLayout, DcPageTemplate, DcSubSystem

        template = ResourceGateway.get(
            DcPageTemplate,
            secure_code,
            raise_on_not_found=False,
            check_permission=False,
        )
        if not template or template.is_deleted:
            system_templates = ResourceGateway.filter(
                DcPageTemplate,
                skip_tenant_filter=True,
                check_permission=False,
                scope='system',
                secure_code=secure_code,
                is_deleted=False,
            )
            template = system_templates[0] if system_templates else None

        if not template:
            return jsonify({'success': False, 'error': _('模板不存在')}), 404

        data = request.get_json() or {}
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'success': False, 'error': _('名稱不可為空')}), 400

        sub_system_sc = (data.get('sub_system_secure_code') or '').strip()
        sub_system = ResourceGateway.get(
            DcSubSystem,
            sub_system_sc,
            raise_on_not_found=False,
            check_permission=False,
        )
        if not sub_system or sub_system.is_deleted:
            return jsonify({'success': False, 'error': _('子系統不存在')}), 404

        new_ir, report = sanitize_template_ir(
            template.layout_json or {},
            source_sub_system_sc=template.source_sub_system_sc,
            target_sub_system_sc=sub_system.secure_code,
            source_org_sc=template.org_secure_code,
            target_org_sc=get_current_tenant(),
        )
        ok, errors = validate_page_ir(new_ir)
        if not ok:
            logger.error(
                '[Template] sanitize_template_ir produced invalid Page IR: '
                'template=%s target_sub_system=%s errors=%s',
                secure_code,
                sub_system.secure_code,
                errors,
            )
            return jsonify({'success': False, 'error': _('Page IR validation failed')}), 500

        page = ResourceGateway.create(
            DcPageLayout,
            check_permission=False,
            name=name,
            description=data.get('description', ''),
            layout_json=new_ir,
            is_active=True,
        )
        ResourceGateway.commit()

        return jsonify({
            'success': True,
            'data': {
                'page': page.to_dict(),
                'report': report,
            },
        }), 201
    except Exception as e:
        db.session.rollback()
        logger.exception('[Template] instantiate_template error')
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
        # 第二道防線：避免日後若 get() 放寬租戶過濾時，內建樣板被 API 修改。
        if template.scope == 'system':
            return jsonify({'success': False, 'error': _('內建樣板不可修改')}), 403

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
        # 第二道防線：避免日後若 get() 放寬租戶過濾時，內建樣板被 API 刪除。
        if template.scope == 'system':
            return jsonify({'success': False, 'error': _('內建樣板不可刪除')}), 403

        ResourceGateway.delete(template, check_permission=False, soft=True)
        ResourceGateway.commit()

        return jsonify({'success': True, 'message': _('模板已刪除')})
    except Exception as e:
        db.session.rollback()
        logger.exception('[Template] delete_template error')
        return jsonify({'success': False, 'error': str(e)}), 500
