"""
表單中心 - 簽核片語 CRUD
"""
import logging
import secrets

from flask import jsonify, request
from flask_login import current_user

from app.security.decorators import module_access_required
from app.platform.data import get_current_org
from app import csrf

from .form_center import form_center_bp
from flask_babel import gettext as _


_PHRASE_CATEGORY_CODE = 'APPROVAL_PHRASES'
_PHRASE_CATEGORY_NAME = '簽核片語'

logger = logging.getLogger(__name__)


def _has_org_db(org_sc):
    """檢查企業是否有專屬 DB"""
    from modules.form_workflow.models.org_database import FwOrgDatabase
    return FwOrgDatabase.query.filter_by(
        org_secure_code=org_sc, is_ready=True, is_deleted=False
    ).first() is not None


def _ensure_phrase_category(org_sc):
    """確保企業 DB 有 APPROVAL_PHRASES 類別，沒有則自動建立。
    回傳 True 表示 org DB 可用，False 表示無 org DB。
    """
    try:
        if not _has_org_db(org_sc):
            return False
        from app.services.lookup_org_service import LookupOrgService
        cat = LookupOrgService.get_category_by_code(org_sc, _PHRASE_CATEGORY_CODE)
        if not cat:
            LookupOrgService.create_category(
                org_sc,
                code=_PHRASE_CATEGORY_CODE,
                name=_PHRASE_CATEGORY_NAME,
                description='個人簽核片語庫',
            )
        return True
    except Exception as exc:
        logger.warning('[FCPhrases] 簽核片語類別初始化失敗 org=%s: %s', org_sc, exc)
        return False


def _phrase_to_dict(item):
    """將 lookup_item dict 轉為前端需要的簽核片語格式"""
    return {
        'secure_code': item['secure_code'],
        'text': item['label'],
        'sort_order': item['sort_order'],
    }


@form_center_bp.route('/canned-messages')
@module_access_required('form_workflow', False)
def list_canned_messages():
    """取得當前用戶的簽核片語列表"""
    from app.services.lookup_org_service import LookupOrgService

    try:
        org = get_current_org()
        if not org:
            return jsonify({'success': False, 'error': 'Organization not found'}), 400

        if not _ensure_phrase_category(org.secure_code):
            return jsonify({'success': True, 'data': []})

        items = LookupOrgService.get_items_by_user(
            org.secure_code, _PHRASE_CATEGORY_CODE, current_user.secure_code
        )

        return jsonify({
            'success': True,
            'data': [_phrase_to_dict(it) for it in items]
        })
    except Exception as exc:
        logger.warning('[FCPhrases] 讀取簽核片語失敗，降級為空結果：%s', exc)
        return jsonify({'success': True, 'data': []})


@form_center_bp.route('/canned-messages', methods=['POST'])
@csrf.exempt
@module_access_required('form_workflow', False)
def create_canned_message():
    """新增簽核片語"""
    from app.services.lookup_org_service import LookupOrgService, OrgDatabaseUnavailable

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    data = request.get_json() or {}
    text = (data.get('text') or '').strip()
    if not text:
        return jsonify({'success': False, 'error': _('片語內容不可為空')}), 400
    if len(text) > 200:
        return jsonify({'success': False, 'error': _('片語內容不可超過 200 字')}), 400

    has_org_db = _has_org_db(org.secure_code)
    if not _ensure_phrase_category(org.secure_code):
        if has_org_db:
            return jsonify({
                'success': False,
                'error': _('企業專屬資料庫目前無法使用，請聯絡系統管理員'),
            }), 503
        return jsonify({'success': False, 'error': _('企業尚未建立專屬資料庫')}), 400

    try:
        # 取得目前最大 sort_order
        existing = LookupOrgService.get_items_by_user(
            org.secure_code, _PHRASE_CATEGORY_CODE, current_user.secure_code
        )
        max_sort = max((it['sort_order'] for it in existing), default=0)

        item = LookupOrgService.create_item(
            org_secure_code=org.secure_code,
            category_code=_PHRASE_CATEGORY_CODE,
            code=secrets.token_urlsafe(12),
            label=text,
            user_secure_code=current_user.secure_code,
            sort_order=max_sort + 1,
        )
    except OrgDatabaseUnavailable:
        logger.warning('[FCPhrases] create_canned_message: 企業專屬資料庫不可用 org=%s', org.secure_code)
        return jsonify({
            'success': False,
            'error': _('企業專屬資料庫目前無法使用，請聯絡系統管理員'),
        }), 503

    return jsonify({'success': True, 'data': _phrase_to_dict(item)})


@form_center_bp.route('/canned-messages/<secure_code>', methods=['PUT'])
@csrf.exempt
@module_access_required('form_workflow', False)
def update_canned_message(secure_code):
    """修改簽核片語"""
    from app.services.lookup_org_service import LookupOrgService, OrgDatabaseUnavailable

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    if not _has_org_db(org.secure_code):
        return jsonify({'success': False, 'error': _('企業尚未建立專屬資料庫')}), 400
    if not _ensure_phrase_category(org.secure_code):
        return jsonify({
            'success': False,
            'error': _('企業專屬資料庫目前無法使用，請聯絡系統管理員'),
        }), 503

    try:
        # 驗證此片語屬於當前用戶
        item = LookupOrgService.get_item_by_secure_code(org.secure_code, secure_code)
        if not item or item.get('user_secure_code') != current_user.secure_code:
            return jsonify({'success': False, 'error': _('找不到此片語')}), 404

        data = request.get_json() or {}
        text = (data.get('text') or '').strip()
        if not text:
            return jsonify({'success': False, 'error': _('片語內容不可為空')}), 400
        if len(text) > 200:
            return jsonify({'success': False, 'error': _('片語內容不可超過 200 字')}), 400

        updated = LookupOrgService.update_item(
            org.secure_code, secure_code, label=text
        )
        if not updated:
            return jsonify({'success': False, 'error': _('更新失敗')}), 500
    except OrgDatabaseUnavailable:
        logger.warning('[FCPhrases] update_canned_message: 企業專屬資料庫不可用 org=%s', org.secure_code)
        return jsonify({
            'success': False,
            'error': _('企業專屬資料庫目前無法使用，請聯絡系統管理員'),
        }), 503

    return jsonify({'success': True, 'data': _phrase_to_dict(updated)})


@form_center_bp.route('/canned-messages/<secure_code>', methods=['DELETE'])
@csrf.exempt
@module_access_required('form_workflow', False)
def delete_canned_message(secure_code):
    """刪除簽核片語（軟刪除）"""
    from app.services.lookup_org_service import LookupOrgService, OrgDatabaseUnavailable

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    if not _has_org_db(org.secure_code):
        return jsonify({'success': False, 'error': _('企業尚未建立專屬資料庫')}), 400
    if not _ensure_phrase_category(org.secure_code):
        return jsonify({
            'success': False,
            'error': _('企業專屬資料庫目前無法使用，請聯絡系統管理員'),
        }), 503

    try:
        # 驗證此片語屬於當前用戶
        item = LookupOrgService.get_item_by_secure_code(org.secure_code, secure_code)
        if not item or item.get('user_secure_code') != current_user.secure_code:
            return jsonify({'success': False, 'error': _('找不到此片語')}), 404

        ok = LookupOrgService.delete_item(org.secure_code, secure_code)
        if not ok:
            return jsonify({'success': False, 'error': _('刪除失敗')}), 500
    except OrgDatabaseUnavailable:
        logger.warning('[FCPhrases] delete_canned_message: 企業專屬資料庫不可用 org=%s', org.secure_code)
        return jsonify({
            'success': False,
            'error': _('企業專屬資料庫目前無法使用，請聯絡系統管理員'),
        }), 503

    return jsonify({'success': True, 'message': _('已刪除')})
