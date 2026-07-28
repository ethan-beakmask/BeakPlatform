"""
NoCode Builder Portal Org API
公開子系統帳號群組 / 階級矩陣維運 API
"""
import logging

from flask import jsonify, request
from flask_babel import gettext as _

from app import csrf
from app.platform.data import get_current_org
from app.security.decorators import module_access_required

from . import api_bp

logger = logging.getLogger(__name__)


def _get_owned_sub_system(ss_sc):
    from ..models import DcSubSystem

    org = get_current_org()
    if not org:
        return None

    return DcSubSystem.query.filter_by(
        secure_code=ss_sc,
        org_secure_code=org.secure_code,
        is_deleted=False,
    ).first()


def _portal_db_not_found():
    return jsonify({
        'success': False,
        'error': _('子系統 portal.db 不存在，請先初始化 Portal'),
    }), 400


@api_bp.route('/sub-systems/<ss_sc>/portal/org')
@module_access_required('nocode_builder')
def get_portal_org(ss_sc):
    """取得 portal 群組、階級與帳號清單。"""
    if not _get_owned_sub_system(ss_sc):
        return jsonify({'success': False, 'error': _('Sub system not found')}), 404

    from ..services import portal_auth_service as svc

    try:
        return jsonify({
            'success': True,
            'data': {
                'groups': svc.list_groups(ss_sc),
                'levels': svc.list_levels(ss_sc),
                'users': svc.list_users(ss_sc),
            },
        })
    except FileNotFoundError:
        return _portal_db_not_found()


@api_bp.route('/sub-systems/<ss_sc>/portal/groups', methods=['POST'])
@csrf.exempt
@module_access_required('nocode_builder')
def upsert_portal_group(ss_sc):
    """新增或更新 portal 群組。"""
    if not _get_owned_sub_system(ss_sc):
        return jsonify({'success': False, 'error': _('Sub system not found')}), 404

    from ..services import portal_auth_service as svc

    data = request.get_json() or {}
    try:
        group, error = svc.upsert_group(
            ss_sc,
            data.get('code', ''),
            data.get('name', ''),
            data.get('display_order', 0) or 0,
        )
    except FileNotFoundError:
        return _portal_db_not_found()
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': _('顯示順序格式不正確')}), 400

    if error:
        return jsonify({'success': False, 'error': _(error)}), 400

    return jsonify({
        'success': True,
        'data': group,
        'message': _('群組已儲存'),
    })


@api_bp.route('/sub-systems/<ss_sc>/portal/levels', methods=['POST'])
@csrf.exempt
@module_access_required('nocode_builder')
def upsert_portal_level(ss_sc):
    """新增或更新 portal 階級。"""
    if not _get_owned_sub_system(ss_sc):
        return jsonify({'success': False, 'error': _('Sub system not found')}), 404

    from ..services import portal_auth_service as svc

    data = request.get_json() or {}
    try:
        level, error = svc.upsert_level(
            ss_sc,
            data.get('code', ''),
            data.get('name', ''),
            data.get('rank', 0),
            data.get('display_order', 0) or 0,
        )
    except FileNotFoundError:
        return _portal_db_not_found()
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': _('rank 或顯示順序格式不正確')}), 400

    if error:
        return jsonify({'success': False, 'error': _(error)}), 400

    return jsonify({
        'success': True,
        'data': level,
        'message': _('階級已儲存'),
    })


@api_bp.route('/sub-systems/<ss_sc>/portal/users/<user_sc>/assignment', methods=['PUT'])
@csrf.exempt
@module_access_required('nocode_builder')
def update_portal_user_assignment(ss_sc, user_sc):
    """更新 portal 帳號所屬群組與階級。"""
    if not _get_owned_sub_system(ss_sc):
        return jsonify({'success': False, 'error': _('Sub system not found')}), 404

    from ..services import portal_auth_service as svc

    data = request.get_json() or {}
    try:
        ok = svc.set_user_assignment(
            ss_sc,
            user_sc,
            data.get('group_code', ''),
            data.get('level_code', ''),
        )
    except FileNotFoundError:
        return _portal_db_not_found()

    if not ok:
        return jsonify({'success': False, 'error': _('帳號或群組階級不存在')}), 400

    return jsonify({
        'success': True,
        'data': {
            'secure_code': user_sc,
            'group_code': data.get('group_code', ''),
            'level_code': data.get('level_code', ''),
        },
        'message': _('帳號歸屬已更新'),
    })
