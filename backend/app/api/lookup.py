"""
BeakPlatform - Lookup Table API
通用選項清單管理 API

資料隔離架構:
  - 系統級 (is_system=True, org_secure_code=NULL): 留主庫，ORM 存取，禁止修改/刪除
  - 企業級: 存入企業專屬 DB (org_{id})，psycopg2 raw SQL 存取

端點：
- GET    /api/lookup/categories                         列出可見類別 (合併雙來源)
- POST   /api/lookup/categories                         建立企業級類別
- GET    /api/lookup/categories/<sc>                    單一類別詳情
- PUT    /api/lookup/categories/<sc>                    更新類別 (企業級)
- DELETE /api/lookup/categories/<sc>                    軟刪除類別 (企業級)
- GET    /api/lookup/categories/<sc>/items              該類別下所有選項 (合併)
- POST   /api/lookup/categories/<sc>/items              新增選項 (企業類別)
- PUT    /api/lookup/items/<sc>                         更新選項 (企業級)
- DELETE /api/lookup/items/<sc>                         軟刪除選項 (企業級)
- PATCH  /api/lookup/categories/<sc>/items/reorder      批次更新排序 (企業類別)
- GET    /api/lookup/by-code/<category_code>            用 code 取選項 (合併)
"""
import logging
import re

from flask import Blueprint, jsonify, request
from flask_babel import gettext as _
from flask_login import current_user

from ..security.decorators import login_required, admin_required
from ..services.lookup_service import LookupService
from ..services.lookup_org_service import LookupOrgService, OrgDatabaseUnavailable
from ..services.code_generator import get_code_generator
from .. import csrf

_CODE_PATTERN = re.compile(r'^[A-Za-z][A-Za-z0-9_]*$')

_VALUE_FIELDS = ('value_str', 'value_int', 'value_decimal',
                 'value_date', 'value_time', 'value_datetime')

logger = logging.getLogger(__name__)


def _extract_value_fields(data: dict) -> dict:
    """從 request data 提取並驗證多型別值欄位"""
    result = {}
    for field in _VALUE_FIELDS:
        if field not in data:
            continue
        val = data[field]
        if val == '' or val is None:
            result[field] = None
            continue
        if field == 'value_str':
            val = str(val)
            if len(val) > 500:
                raise ValueError(_('字串值不得超過 500 字元'))
            result[field] = val
        elif field == 'value_int':
            try:
                result[field] = int(val)
            except (ValueError, TypeError):
                raise ValueError(_('整數值格式錯誤'))
        elif field == 'value_decimal':
            try:
                result[field] = round(float(val), 2)
            except (ValueError, TypeError):
                raise ValueError(_('小數值格式錯誤'))
        elif field == 'value_date':
            if not re.match(r'^\d{4}-\d{2}-\d{2}$', str(val)):
                raise ValueError(_('日期格式錯誤，應為 YYYY-MM-DD'))
            result[field] = str(val)
        elif field == 'value_time':
            if not re.match(r'^\d{2}:\d{2}(:\d{2})?$', str(val)):
                raise ValueError(_('時間格式錯誤，應為 HH:MM'))
            result[field] = str(val)
        elif field == 'value_datetime':
            # datetime-local 輸入格式: YYYY-MM-DDTHH:MM
            s = str(val).replace('T', ' ').replace('t', ' ')
            if not re.match(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}(:\d{2})?$', s):
                raise ValueError(_('日期時間格式錯誤，應為 YYYY-MM-DD HH:MM'))
            result[field] = s
    return result

lookup_bp = Blueprint('lookup', __name__, url_prefix='/api/lookup')


# =============================================================================
# Category 端點
# =============================================================================

@lookup_bp.route('/categories')
@login_required
def list_categories():
    """列出可見類別（系統級 + 企業級合併）"""
    categories = LookupService.get_categories_merged(current_user.org_secure_code)
    return jsonify({
        'success': True,
        'data': categories
    })


@lookup_bp.route('/categories', methods=['POST'])
@csrf.exempt
@admin_required
def create_category():
    """建立企業級類別 (寫入 org DB)"""
    data = request.get_json() or {}
    code = (data.get('code') or '').strip()
    name = (data.get('name') or '').strip()

    if not code:
        return jsonify({'success': False, 'error': _('缺少 code')}), 400
    if not name:
        return jsonify({'success': False, 'error': _('缺少 name')}), 400

    # 代碼格式驗證
    generator = get_code_generator()
    is_valid, error = generator.validate(code)
    if not is_valid:
        return jsonify({'success': False, 'error': error}), 400

    org_sc = current_user.org_secure_code

    # 檢查不與系統級 code 衝突
    sys_cat = LookupService.get_category(code)
    if sys_cat:
        return jsonify({'success': False, 'error': _('類別代碼 %(code)s 與系統級類別衝突', code=code)}), 409

    # 檢查不與企業級 code 重複
    org_cat = LookupOrgService.get_category_by_code(org_sc, code)
    if org_cat:
        return jsonify({'success': False, 'error': _('類別代碼 %(code)s 已存在', code=code)}), 409

    try:
        category = LookupOrgService.create_category(
            org_secure_code=org_sc,
            code=code,
            name=name,
            description=data.get('description'),
            is_hierarchical=data.get('is_hierarchical', False),
            name_i18n=data.get('name_i18n'),
        )
        LookupService._invalidate_cache(code, org_sc)
        return jsonify({
            'success': True,
            'data': category,
            'message': _('已建立類別')
        }), 201
    except OrgDatabaseUnavailable:
        logger.warning('[Lookup] create_category: 企業專屬資料庫不可用 org=%s', org_sc)
        return jsonify({
            'success': False,
            'error': _('企業專屬資料庫目前無法使用，請聯絡系統管理員'),
        }), 503
    except RuntimeError as e:
        logger.warning(f'[Lookup] create_category: {e}')
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.exception('[Lookup] create_category error')
        return jsonify({'success': False, 'error': str(e)}), 500


@lookup_bp.route('/categories/<secure_code>')
@login_required
def get_category(secure_code):
    """單一類別詳情 (先查主庫系統級，再查 org DB)"""
    org_sc = current_user.org_secure_code

    # 先查主庫
    sys_cat = LookupService.get_category_by_secure_code(secure_code)
    if sys_cat:
        # 系統級或屬於當前企業的主庫資料
        if sys_cat.org_secure_code and sys_cat.org_secure_code != org_sc:
            return jsonify({'success': False, 'error': _('類別不存在')}), 404
        return jsonify({'success': True, 'data': sys_cat.to_dict()})

    # 查 org DB
    org_cat = LookupOrgService.get_category_by_secure_code(org_sc, secure_code)
    if org_cat:
        return jsonify({'success': True, 'data': org_cat})

    return jsonify({'success': False, 'error': _('類別不存在')}), 404


@lookup_bp.route('/categories/<secure_code>', methods=['PUT'])
@csrf.exempt
@admin_required
def update_category(secure_code):
    """更新類別 (系統級 403，企業級走 org DB)"""
    org_sc = current_user.org_secure_code
    location = LookupService.resolve_category_location(secure_code, org_sc)

    if location == 'system':
        return jsonify({'success': False, 'error': _('系統級類別不可修改')}), 403
    if location is None:
        try:
            LookupOrgService.ensure_tables(org_sc)
        except OrgDatabaseUnavailable:
            logger.warning('[Lookup] update_category: 企業專屬資料庫不可用 org=%s', org_sc)
            return jsonify({
                'success': False,
                'error': _('企業專屬資料庫目前無法使用，請聯絡系統管理員'),
            }), 503
        return jsonify({'success': False, 'error': _('類別不存在')}), 404

    # 企業級 -> org DB
    data = request.get_json() or {}
    try:
        updated = LookupOrgService.update_category(
            org_sc, secure_code,
            **{k: v for k, v in data.items()
               if k in ('name', 'name_i18n', 'description', 'is_hierarchical', 'is_active')}
        )
        if not updated:
            return jsonify({'success': False, 'error': _('更新失敗')}), 400
        # invalidate 合併快取
        cat_code = updated.get('code', '')
        LookupService._invalidate_cache(cat_code, org_sc)
        return jsonify({
            'success': True,
            'data': updated,
            'message': _('已更新類別')
        })
    except OrgDatabaseUnavailable:
        logger.warning('[Lookup] update_category: 企業專屬資料庫不可用 org=%s', org_sc)
        return jsonify({
            'success': False,
            'error': _('企業專屬資料庫目前無法使用，請聯絡系統管理員'),
        }), 503
    except Exception as e:
        logger.exception('[Lookup] update_category error')
        return jsonify({'success': False, 'error': str(e)}), 500


@lookup_bp.route('/categories/<secure_code>', methods=['DELETE'])
@csrf.exempt
@admin_required
def delete_category(secure_code):
    """軟刪除類別 (系統級 403，企業級走 org DB)"""
    org_sc = current_user.org_secure_code
    location = LookupService.resolve_category_location(secure_code, org_sc)

    if location == 'system':
        return jsonify({'success': False, 'error': _('系統級類別不可刪除')}), 403
    if location is None:
        try:
            LookupOrgService.ensure_tables(org_sc)
        except OrgDatabaseUnavailable:
            logger.warning('[Lookup] delete_category: 企業專屬資料庫不可用 org=%s', org_sc)
            return jsonify({
                'success': False,
                'error': _('企業專屬資料庫目前無法使用，請聯絡系統管理員'),
            }), 503
        return jsonify({'success': False, 'error': _('類別不存在')}), 404

    try:
        # 先取類別資訊
        org_cat = LookupOrgService.get_category_by_secure_code(org_sc, secure_code)
        if not org_cat:
            return jsonify({'success': False, 'error': _('類別不存在')}), 404
        cat_code = org_cat.get('code', '')

        # 必須先停用才能刪除
        if org_cat.get('is_active', True):
            return jsonify({'success': False, 'error': _('請先停用類別後再刪除')}), 400

        success = LookupOrgService.delete_category(org_sc, secure_code)
        if not success:
            return jsonify({'success': False, 'error': _('刪除失敗')}), 400
        LookupService._invalidate_cache(cat_code, org_sc)
        return jsonify({'success': True, 'message': _('已刪除類別')})
    except OrgDatabaseUnavailable:
        logger.warning('[Lookup] delete_category: 企業專屬資料庫不可用 org=%s', org_sc)
        return jsonify({
            'success': False,
            'error': _('企業專屬資料庫目前無法使用，請聯絡系統管理員'),
        }), 503
    except Exception as e:
        logger.exception('[Lookup] delete_category error')
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# Item 端點
# =============================================================================

@lookup_bp.route('/categories/<secure_code>/items')
@login_required
def list_items(secure_code):
    """
    該類別下所有選項 (合併系統+企業，含 inactive，管理用途)

    category 可在主庫或 org DB:
    - 系統類別: 只回主庫 items (系統級)
    - 企業類別: 只回 org DB items
    """
    org_sc = current_user.org_secure_code

    # 定位 category
    sys_cat = LookupService.get_category_by_secure_code(secure_code)
    if sys_cat:
        if sys_cat.org_secure_code and sys_cat.org_secure_code != org_sc:
            return jsonify({'success': False, 'error': _('類別不存在')}), 404
        # 系統類別: 回主庫 items
        items = LookupService.get_all_items_merged(sys_cat.code, org_sc)
        return jsonify({'success': True, 'data': items})

    # 查 org DB category
    org_cat = LookupOrgService.get_category_by_secure_code(org_sc, secure_code)
    if not org_cat:
        return jsonify({'success': False, 'error': _('類別不存在')}), 404

    # 企業類別: 回 org DB items
    items = LookupOrgService.get_all_items(org_sc, org_cat['code'])
    return jsonify({'success': True, 'data': items})


@lookup_bp.route('/categories/<secure_code>/items', methods=['POST'])
@csrf.exempt
@admin_required
def create_item(secure_code):
    """新增選項 (定位 category 來源，企業類別才允許新增)"""
    org_sc = current_user.org_secure_code

    # 定位 category
    sys_cat = LookupService.get_category_by_secure_code(secure_code)
    if sys_cat:
        if sys_cat.is_system:
            return jsonify({'success': False, 'error': _('系統級類別不可新增選項')}), 403
        if sys_cat.org_secure_code and sys_cat.org_secure_code != org_sc:
            return jsonify({'success': False, 'error': _('類別不存在')}), 404
        # 主庫非系統級 category -- 這種情況在遷移後不應存在
        # 但為安全起見仍處理: 拒絕寫入
        return jsonify({'success': False, 'error': _('此類別不允許新增選項')}), 403

    try:
        LookupOrgService.ensure_tables(org_sc)
    except OrgDatabaseUnavailable:
        logger.warning('[Lookup] create_item: 企業專屬資料庫不可用 org=%s', org_sc)
        return jsonify({
            'success': False,
            'error': _('企業專屬資料庫目前無法使用，請聯絡系統管理員'),
        }), 503

    org_cat = LookupOrgService.get_category_by_secure_code(org_sc, secure_code)
    if not org_cat:
        return jsonify({'success': False, 'error': _('類別不存在')}), 404

    data = request.get_json() or {}
    code = (data.get('code') or '').strip()
    label = (data.get('label') or '').strip()

    if not code:
        return jsonify({'success': False, 'error': _('缺少 code')}), 400
    if not label:
        return jsonify({'success': False, 'error': _('缺少 label')}), 400

    # 代碼格式驗證
    if not _CODE_PATTERN.match(code):
        return jsonify({'success': False, 'error': _('代碼格式錯誤：只能包含英文、數字和底線，且必須以英文開頭')}), 400

    cat_code = org_cat['code']

    # 檢查重複
    if LookupOrgService.check_item_code_exists(org_sc, cat_code, code):
        return jsonify({'success': False, 'error': _('選項代碼 %(code)s 已存在', code=code)}), 409

    try:
        value_fields = _extract_value_fields(data)
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    try:
        item = LookupOrgService.create_item(
            org_secure_code=org_sc,
            category_code=cat_code,
            code=code,
            label=label,
            label_i18n=data.get('label_i18n'),
            value=data.get('value'),
            parent_code=data.get('parent_code'),
            sort_order=data.get('sort_order', 0),
            **value_fields,
        )
        LookupService._invalidate_cache(cat_code, org_sc)
        return jsonify({
            'success': True,
            'data': item,
            'message': _('已新增選項')
        }), 201
    except OrgDatabaseUnavailable:
        logger.warning('[Lookup] create_item: 企業專屬資料庫不可用 org=%s', org_sc)
        return jsonify({
            'success': False,
            'error': _('企業專屬資料庫目前無法使用，請聯絡系統管理員'),
        }), 503
    except Exception as e:
        logger.exception('[Lookup] create_item error')
        return jsonify({'success': False, 'error': str(e)}), 500


@lookup_bp.route('/items/<secure_code>', methods=['PUT'])
@csrf.exempt
@admin_required
def update_item(secure_code):
    """更新選項 (系統級 403，企業級走 org DB)"""
    org_sc = current_user.org_secure_code
    location = LookupService.resolve_item_location(secure_code, org_sc)

    if location == 'system':
        return jsonify({'success': False, 'error': _('系統級選項不可修改')}), 403
    if location is None:
        try:
            LookupOrgService.ensure_tables(org_sc)
        except OrgDatabaseUnavailable:
            logger.warning('[Lookup] update_item: 企業專屬資料庫不可用 org=%s', org_sc)
            return jsonify({
                'success': False,
                'error': _('企業專屬資料庫目前無法使用，請聯絡系統管理員'),
            }), 503
        return jsonify({'success': False, 'error': _('選項不存在')}), 404

    # 企業級 -> org DB
    data = request.get_json() or {}
    try:
        value_fields = _extract_value_fields(data)
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    try:
        base_fields = {k: v for k, v in data.items()
                       if k in ('label', 'label_i18n', 'value', 'parent_code', 'sort_order', 'is_active')}
        base_fields.update(value_fields)
        updated = LookupOrgService.update_item(
            org_sc, secure_code, **base_fields
        )
        if not updated:
            return jsonify({'success': False, 'error': _('更新失敗')}), 400
        LookupService._invalidate_cache(updated.get('category_code', ''), org_sc)
        return jsonify({
            'success': True,
            'data': updated,
            'message': _('已更新選項')
        })
    except OrgDatabaseUnavailable:
        logger.warning('[Lookup] update_item: 企業專屬資料庫不可用 org=%s', org_sc)
        return jsonify({
            'success': False,
            'error': _('企業專屬資料庫目前無法使用，請聯絡系統管理員'),
        }), 503
    except Exception as e:
        logger.exception('[Lookup] update_item error')
        return jsonify({'success': False, 'error': str(e)}), 500


@lookup_bp.route('/items/<secure_code>', methods=['DELETE'])
@csrf.exempt
@admin_required
def delete_item(secure_code):
    """軟刪除選項 (系統級 403，企業級走 org DB)"""
    org_sc = current_user.org_secure_code
    location = LookupService.resolve_item_location(secure_code, org_sc)

    if location == 'system':
        return jsonify({'success': False, 'error': _('系統級選項不可刪除')}), 403
    if location is None:
        try:
            LookupOrgService.ensure_tables(org_sc)
        except OrgDatabaseUnavailable:
            logger.warning('[Lookup] delete_item: 企業專屬資料庫不可用 org=%s', org_sc)
            return jsonify({
                'success': False,
                'error': _('企業專屬資料庫目前無法使用，請聯絡系統管理員'),
            }), 503
        return jsonify({'success': False, 'error': _('選項不存在')}), 404

    try:
        # 取得 item 資訊
        org_item = LookupOrgService.get_item_by_secure_code(org_sc, secure_code)
        if not org_item:
            return jsonify({'success': False, 'error': _('選項不存在')}), 404
        cat_code = org_item.get('category_code', '')

        # 後端也檢查：必須先停用才能刪除
        if org_item.get('is_active', True):
            return jsonify({'success': False, 'error': _('請先停用選項後再刪除')}), 400

        success = LookupOrgService.delete_item(org_sc, secure_code)
        if not success:
            return jsonify({'success': False, 'error': _('刪除失敗')}), 400
        LookupService._invalidate_cache(cat_code, org_sc)
        return jsonify({'success': True, 'message': _('已刪除選項')})
    except OrgDatabaseUnavailable:
        logger.warning('[Lookup] delete_item: 企業專屬資料庫不可用 org=%s', org_sc)
        return jsonify({
            'success': False,
            'error': _('企業專屬資料庫目前無法使用，請聯絡系統管理員'),
        }), 503
    except RuntimeError as e:
        # 子選項仍啟用中等業務錯誤
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.exception('[Lookup] delete_item error')
        return jsonify({'success': False, 'error': str(e)}), 500


@lookup_bp.route('/categories/<secure_code>/items/reorder', methods=['PATCH'])
@csrf.exempt
@admin_required
def reorder_items(secure_code):
    """批次更新排序 (企業類別才允許)"""
    org_sc = current_user.org_secure_code

    # 定位 category
    location = LookupService.resolve_category_location(secure_code, org_sc)
    if location == 'system':
        return jsonify({'success': False, 'error': _('系統級類別不可排序')}), 403
    if location is None:
        try:
            LookupOrgService.ensure_tables(org_sc)
        except OrgDatabaseUnavailable:
            logger.warning('[Lookup] reorder_items: 企業專屬資料庫不可用 org=%s', org_sc)
            return jsonify({
                'success': False,
                'error': _('企業專屬資料庫目前無法使用，請聯絡系統管理員'),
            }), 503
        return jsonify({'success': False, 'error': _('類別不存在')}), 404

    org_cat = LookupOrgService.get_category_by_secure_code(org_sc, secure_code)
    if not org_cat:
        return jsonify({'success': False, 'error': _('類別不存在')}), 404

    data = request.get_json() or {}
    order_list = data.get('order', [])
    if not order_list:
        return jsonify({'success': False, 'error': _('缺少 order 陣列')}), 400

    cat_code = org_cat['code']

    try:
        LookupOrgService.reorder_items(org_sc, cat_code, order_list)
        LookupService._invalidate_cache(cat_code, org_sc)
        return jsonify({'success': True, 'message': _('排序已更新')})
    except OrgDatabaseUnavailable:
        logger.warning('[Lookup] reorder_items: 企業專屬資料庫不可用 org=%s', org_sc)
        return jsonify({
            'success': False,
            'error': _('企業專屬資料庫目前無法使用，請聯絡系統管理員'),
        }), 503
    except Exception as e:
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
    回傳 active items，合併系統+企業，帶快取。
    """
    items = LookupService.get_items_merged(category_code, current_user.org_secure_code)
    return jsonify({
        'success': True,
        'data': items
    })
