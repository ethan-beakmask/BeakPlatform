"""
BeakPlatform - Lookup Table API
通用選項清單管理 API

端點：
- GET    /api/lookup/categories                         列出可見類別
- POST   /api/lookup/categories                         建立企業級類別
- GET    /api/lookup/categories/<sc>                    單一類別詳情
- PUT    /api/lookup/categories/<sc>                    更新類別
- DELETE /api/lookup/categories/<sc>                    軟刪除類別
- GET    /api/lookup/categories/<sc>/items              該類別下所有選項
- POST   /api/lookup/categories/<sc>/items              新增選項
- PUT    /api/lookup/items/<sc>                         更新選項
- DELETE /api/lookup/items/<sc>                         軟刪除選項
- PATCH  /api/lookup/categories/<sc>/items/reorder      批次更新排序
- GET    /api/lookup/by-code/<category_code>            用 code 取選項
"""
import logging

from flask import Blueprint, jsonify, request
from flask_login import current_user

from sqlalchemy import text

from ..security.decorators import login_required, admin_required
from ..services.lookup_service import LookupService
from .. import csrf, db


def _set_rls_context(org_secure_code):
    """設定 RLS context variables for current DB session"""
    db.session.execute(
        text("SELECT set_config('app.current_org', :org, false)"),
        {'org': org_secure_code or ''}
    )

logger = logging.getLogger(__name__)

lookup_bp = Blueprint('lookup', __name__, url_prefix='/api/lookup')


# =============================================================================
# Category 端點
# =============================================================================

@lookup_bp.route('/categories')
@login_required
def list_categories():
    """列出可見類別（系統級 + 企業級）"""
    _set_rls_context(current_user.org_secure_code)
    categories = LookupService.get_categories(current_user.org_secure_code)
    return jsonify({
        'success': True,
        'data': [c.to_dict() for c in categories]
    })


@lookup_bp.route('/categories', methods=['POST'])
@csrf.exempt
@admin_required
def create_category():
    """建立企業級類別"""
    data = request.get_json() or {}
    code = (data.get('code') or '').strip()
    name = (data.get('name') or '').strip()

    if not code:
        return jsonify({'success': False, 'error': '缺少 code'}), 400
    if not name:
        return jsonify({'success': False, 'error': '缺少 name'}), 400

    _set_rls_context(current_user.org_secure_code)

    # 檢查重複
    existing = LookupService.get_category(code, current_user.org_secure_code)
    if existing:
        return jsonify({'success': False, 'error': f'類別代碼 {code} 已存在'}), 409

    try:
        category = LookupService.create_category(
            code=code,
            name=name,
            org_secure_code=current_user.org_secure_code,
            description=data.get('description'),
            is_hierarchical=data.get('is_hierarchical', False),
            name_i18n=data.get('name_i18n'),
        )
        db.session.commit()
        return jsonify({
            'success': True,
            'data': category.to_dict(),
            'message': '已建立類別'
        }), 201
    except Exception as e:
        db.session.rollback()
        logger.exception('[Lookup] create_category error')
        return jsonify({'success': False, 'error': str(e)}), 500


@lookup_bp.route('/categories/<secure_code>')
@login_required
def get_category(secure_code):
    """單一類別詳情"""
    _set_rls_context(current_user.org_secure_code)
    category = LookupService.get_category_by_secure_code(secure_code)
    if not category:
        return jsonify({'success': False, 'error': '類別不存在'}), 404

    # 租戶隔離: 企業級類別只能看自己的
    if category.org_secure_code and category.org_secure_code != current_user.org_secure_code:
        return jsonify({'success': False, 'error': '類別不存在'}), 404

    return jsonify({'success': True, 'data': category.to_dict()})


@lookup_bp.route('/categories/<secure_code>', methods=['PUT'])
@csrf.exempt
@admin_required
def update_category(secure_code):
    """更新類別"""
    _set_rls_context(current_user.org_secure_code)
    category = LookupService.get_category_by_secure_code(secure_code)
    if not category:
        return jsonify({'success': False, 'error': '類別不存在'}), 404

    # 租戶隔離
    if category.org_secure_code and category.org_secure_code != current_user.org_secure_code:
        return jsonify({'success': False, 'error': '類別不存在'}), 404

    data = request.get_json() or {}
    try:
        updated = LookupService.update_category(
            secure_code,
            **{k: v for k, v in data.items()
               if k in ('name', 'name_i18n', 'description', 'is_hierarchical')}
        )
        if not updated:
            return jsonify({'success': False, 'error': '更新失敗'}), 400
        db.session.commit()
        return jsonify({
            'success': True,
            'data': updated.to_dict(),
            'message': '已更新類別'
        })
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 403
    except Exception as e:
        db.session.rollback()
        logger.exception('[Lookup] update_category error')
        return jsonify({'success': False, 'error': str(e)}), 500


@lookup_bp.route('/categories/<secure_code>', methods=['DELETE'])
@csrf.exempt
@admin_required
def delete_category(secure_code):
    """軟刪除類別"""
    _set_rls_context(current_user.org_secure_code)
    category = LookupService.get_category_by_secure_code(secure_code)
    if not category:
        return jsonify({'success': False, 'error': '類別不存在'}), 404

    # 租戶隔離
    if category.org_secure_code and category.org_secure_code != current_user.org_secure_code:
        return jsonify({'success': False, 'error': '類別不存在'}), 404

    try:
        success = LookupService.delete_category(secure_code)
        if not success:
            return jsonify({'success': False, 'error': '刪除失敗'}), 400
        db.session.commit()
        return jsonify({'success': True, 'message': '已刪除類別'})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 403
    except Exception as e:
        db.session.rollback()
        logger.exception('[Lookup] delete_category error')
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# Item 端點
# =============================================================================

@lookup_bp.route('/categories/<secure_code>/items')
@login_required
def list_items(secure_code):
    """該類別下所有選項"""
    _set_rls_context(current_user.org_secure_code)
    category = LookupService.get_category_by_secure_code(secure_code)
    if not category:
        return jsonify({'success': False, 'error': '類別不存在'}), 404

    if category.org_secure_code and category.org_secure_code != current_user.org_secure_code:
        return jsonify({'success': False, 'error': '類別不存在'}), 404

    # 直接查 DB（含 inactive，管理用途）
    from ..models.lookup_item import LookupItem
    query = LookupItem.query.filter_by(
        category_code=category.code,
        is_deleted=False,
    )
    if category.org_secure_code:
        query = query.filter(
            db.or_(
                LookupItem.org_secure_code.is_(None),
                LookupItem.org_secure_code == category.org_secure_code
            )
        )
    else:
        query = query.filter(LookupItem.org_secure_code.is_(None))

    items = query.order_by(LookupItem.sort_order, LookupItem.code).all()
    return jsonify({
        'success': True,
        'data': [item.to_dict() for item in items]
    })


@lookup_bp.route('/categories/<secure_code>/items', methods=['POST'])
@csrf.exempt
@admin_required
def create_item(secure_code):
    """新增選項"""
    _set_rls_context(current_user.org_secure_code)
    category = LookupService.get_category_by_secure_code(secure_code)
    if not category:
        return jsonify({'success': False, 'error': '類別不存在'}), 404

    if category.org_secure_code and category.org_secure_code != current_user.org_secure_code:
        return jsonify({'success': False, 'error': '類別不存在'}), 404

    data = request.get_json() or {}
    code = (data.get('code') or '').strip()
    label = (data.get('label') or '').strip()

    if not code:
        return jsonify({'success': False, 'error': '缺少 code'}), 400
    if not label:
        return jsonify({'success': False, 'error': '缺少 label'}), 400

    # 檢查重複
    from ..models.lookup_item import LookupItem
    existing = LookupItem.query.filter_by(
        category_code=category.code,
        code=code,
        org_secure_code=current_user.org_secure_code,
        is_deleted=False,
    ).first()
    if existing:
        return jsonify({'success': False, 'error': f'選項代碼 {code} 已存在'}), 409

    try:
        item = LookupService.create_item(
            category_code=category.code,
            code=code,
            label=label,
            org_secure_code=current_user.org_secure_code,
            label_i18n=data.get('label_i18n'),
            value=data.get('value'),
            parent_code=data.get('parent_code'),
            sort_order=data.get('sort_order', 0),
        )
        db.session.commit()
        return jsonify({
            'success': True,
            'data': item.to_dict(),
            'message': '已新增選項'
        }), 201
    except Exception as e:
        db.session.rollback()
        logger.exception('[Lookup] create_item error')
        return jsonify({'success': False, 'error': str(e)}), 500


@lookup_bp.route('/items/<secure_code>', methods=['PUT'])
@csrf.exempt
@admin_required
def update_item(secure_code):
    """更新選項"""
    _set_rls_context(current_user.org_secure_code)
    from ..models.lookup_item import LookupItem
    item = LookupItem.query.filter_by(
        secure_code=secure_code, is_deleted=False
    ).first()
    if not item:
        return jsonify({'success': False, 'error': '選項不存在'}), 404

    # 租戶隔離
    if item.org_secure_code and item.org_secure_code != current_user.org_secure_code:
        return jsonify({'success': False, 'error': '選項不存在'}), 404

    data = request.get_json() or {}
    try:
        updated = LookupService.update_item(
            secure_code,
            **{k: v for k, v in data.items()
               if k in ('label', 'label_i18n', 'value', 'parent_code', 'sort_order', 'is_active')}
        )
        if not updated:
            return jsonify({'success': False, 'error': '更新失敗'}), 400
        db.session.commit()
        return jsonify({
            'success': True,
            'data': updated.to_dict(),
            'message': '已更新選項'
        })
    except Exception as e:
        db.session.rollback()
        logger.exception('[Lookup] update_item error')
        return jsonify({'success': False, 'error': str(e)}), 500


@lookup_bp.route('/items/<secure_code>', methods=['DELETE'])
@csrf.exempt
@admin_required
def delete_item(secure_code):
    """軟刪除選項"""
    _set_rls_context(current_user.org_secure_code)
    from ..models.lookup_item import LookupItem
    item = LookupItem.query.filter_by(
        secure_code=secure_code, is_deleted=False
    ).first()
    if not item:
        return jsonify({'success': False, 'error': '選項不存在'}), 404

    if item.org_secure_code and item.org_secure_code != current_user.org_secure_code:
        return jsonify({'success': False, 'error': '選項不存在'}), 404

    try:
        success = LookupService.delete_item(secure_code)
        if not success:
            return jsonify({'success': False, 'error': '刪除失敗'}), 400
        db.session.commit()
        return jsonify({'success': True, 'message': '已刪除選項'})
    except Exception as e:
        db.session.rollback()
        logger.exception('[Lookup] delete_item error')
        return jsonify({'success': False, 'error': str(e)}), 500


@lookup_bp.route('/categories/<secure_code>/items/reorder', methods=['PATCH'])
@csrf.exempt
@admin_required
def reorder_items(secure_code):
    """批次更新排序"""
    _set_rls_context(current_user.org_secure_code)
    category = LookupService.get_category_by_secure_code(secure_code)
    if not category:
        return jsonify({'success': False, 'error': '類別不存在'}), 404

    if category.org_secure_code and category.org_secure_code != current_user.org_secure_code:
        return jsonify({'success': False, 'error': '類別不存在'}), 404

    data = request.get_json() or {}
    order_list = data.get('order', [])
    if not order_list:
        return jsonify({'success': False, 'error': '缺少 order 陣列'}), 400

    try:
        from ..models.lookup_item import LookupItem
        # order 支援兩種格式:
        #   簡易: ["sc1", "sc2", ...]  -- 只更新 sort_order
        #   完整: [{"secure_code":"sc1","parent_code":"X","sort_order":0}, ...]
        for idx, entry in enumerate(order_list):
            if isinstance(entry, str):
                item_sc = entry
                new_parent = None
                new_sort = idx
            elif isinstance(entry, dict):
                item_sc = entry.get('secure_code')
                new_parent = entry.get('parent_code')
                new_sort = entry.get('sort_order', idx)
            else:
                continue
            if not item_sc:
                continue
            item = LookupItem.query.filter_by(
                secure_code=item_sc, is_deleted=False
            ).first()
            if item and item.category_code == category.code:
                item.sort_order = new_sort
                if isinstance(entry, dict) and 'parent_code' in entry:
                    item.parent_code = new_parent or None
        db.session.commit()
        LookupService._invalidate_cache(category.code, category.org_secure_code)
        return jsonify({'success': True, 'message': '排序已更新'})
    except Exception as e:
        db.session.rollback()
        logger.exception('[Lookup] reorder_items error')
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# 快捷端點 (by category code)
# =============================================================================

@lookup_bp.route('/by-code/<category_code>')
@login_required
def get_items_by_code(category_code):
    """
    用 category code 取選項 (form.io 動態載入用)
    回傳 active items，帶快取。
    """
    _set_rls_context(current_user.org_secure_code)
    items = LookupService.get_items(category_code, current_user.org_secure_code)
    return jsonify({
        'success': True,
        'data': items
    })
