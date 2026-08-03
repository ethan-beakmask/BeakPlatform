"""
NoCode Builder Portal Permission API
公開子系統權限碼 / 管理角色維運 API
"""
import logging

from flask import jsonify, request
from flask_babel import gettext as _

from app import csrf
from app.security.decorators import module_access_required

from . import api_bp
from .portal_org_api import _get_owned_sub_system, _portal_db_not_found
from ..services import portal_permission_admin_service as svc
from ..services.portal_permission_templates import list_templates

logger = logging.getLogger(__name__)


def _bad_request(error):
    return jsonify({'success': False, 'error': _(error)}), 400


def _ok(data=None, message='已儲存'):
    return jsonify({'success': True, 'data': data, 'message': _(message)})


@api_bp.route('/sub-systems/<ss_sc>/portal/permission-model')
@module_access_required('nocode_builder')
def get_portal_permission_model(ss_sc):
    if not _get_owned_sub_system(ss_sc):
        return jsonify({'success': False, 'error': _('Sub system not found')}), 404
    try:
        return _ok(svc.get_permission_model(ss_sc), '權限模型已取得')
    except FileNotFoundError:
        return _portal_db_not_found()


@api_bp.route('/sub-systems/<ss_sc>/portal/permission-templates')
@module_access_required('nocode_builder')
def get_portal_permission_templates(ss_sc):
    if not _get_owned_sub_system(ss_sc):
        return jsonify({'success': False, 'error': _('Sub system not found')}), 404
    return _ok(list_templates(), '權限模板已取得')


@api_bp.route('/sub-systems/<ss_sc>/portal/permissions', methods=['POST'])
@csrf.exempt
@module_access_required('nocode_builder')
def upsert_portal_permission(ss_sc):
    if not _get_owned_sub_system(ss_sc):
        return jsonify({'success': False, 'error': _('Sub system not found')}), 404
    data = request.get_json() or {}
    try:
        item, error = svc.upsert_permission(
            ss_sc,
            data.get('code', ''),
            data.get('description', ''),
            data.get('risk_level', 'normal'),
        )
    except FileNotFoundError:
        return _portal_db_not_found()
    if error:
        return _bad_request(error)
    return _ok(item, '權限碼已儲存')


@api_bp.route('/sub-systems/<ss_sc>/portal/permissions/<path:code>', methods=['DELETE'])
@csrf.exempt
@module_access_required('nocode_builder')
def delete_portal_permission(ss_sc, code):
    if not _get_owned_sub_system(ss_sc):
        return jsonify({'success': False, 'error': _('Sub system not found')}), 404
    if not svc._valid_permission_code(code):
        return _bad_request('權限碼格式不正確')
    try:
        ok, error = svc.delete_permission(ss_sc, code)
    except FileNotFoundError:
        return _portal_db_not_found()
    if error:
        status = 409 if error.startswith(svc.PERMISSION_IN_USE_ERROR) else 400
        return jsonify({'success': False, 'error': _(error)}), status
    return _ok({'code': code}, '權限碼已刪除')


@api_bp.route('/sub-systems/<ss_sc>/portal/admin-roles', methods=['POST'])
@csrf.exempt
@module_access_required('nocode_builder')
def upsert_portal_admin_role(ss_sc):
    if not _get_owned_sub_system(ss_sc):
        return jsonify({'success': False, 'error': _('Sub system not found')}), 404
    data = request.get_json() or {}
    try:
        item, error = svc.upsert_admin_role(
            ss_sc,
            data.get('code', ''),
            data.get('name', ''),
            data.get('description', ''),
            data.get('display_order', 0) or 0,
        )
    except FileNotFoundError:
        return _portal_db_not_found()
    except (TypeError, ValueError):
        return _bad_request('顯示順序格式不正確')
    if error:
        return _bad_request(error)
    return _ok(item, '角色已儲存')


@api_bp.route('/sub-systems/<ss_sc>/portal/admin-roles/<code>', methods=['DELETE'])
@csrf.exempt
@module_access_required('nocode_builder')
def delete_portal_admin_role(ss_sc, code):
    if not _get_owned_sub_system(ss_sc):
        return jsonify({'success': False, 'error': _('Sub system not found')}), 404
    try:
        ok, error = svc.delete_admin_role(ss_sc, code)
    except FileNotFoundError:
        return _portal_db_not_found()
    if error:
        return _bad_request(error)
    return _ok({'code': code}, '角色已刪除')


@api_bp.route('/sub-systems/<ss_sc>/portal/admin-roles/<code>/permissions', methods=['PUT'])
@csrf.exempt
@module_access_required('nocode_builder')
def set_portal_admin_role_permissions(ss_sc, code):
    if not _get_owned_sub_system(ss_sc):
        return jsonify({'success': False, 'error': _('Sub system not found')}), 404
    data = request.get_json() or {}
    try:
        ok, error = svc.set_role_permissions(ss_sc, code, data.get('codes'))
    except FileNotFoundError:
        return _portal_db_not_found()
    if error:
        return _bad_request(error)
    return _ok({'code': code, 'permissions': data.get('codes') or []}, '角色權限已更新')


@api_bp.route('/sub-systems/<ss_sc>/portal/levels/<code>/permissions', methods=['PUT'])
@csrf.exempt
@module_access_required('nocode_builder')
def set_portal_level_permissions(ss_sc, code):
    if not _get_owned_sub_system(ss_sc):
        return jsonify({'success': False, 'error': _('Sub system not found')}), 404
    data = request.get_json() or {}
    try:
        ok, error = svc.set_level_permissions(ss_sc, code, data.get('codes'))
    except FileNotFoundError:
        return _portal_db_not_found()
    if error:
        return _bad_request(error)
    return _ok({'code': code, 'permissions': data.get('codes') or []}, '階級權限已更新')


@api_bp.route('/sub-systems/<ss_sc>/portal/users/<user_sc>/roles', methods=['PUT'])
@csrf.exempt
@module_access_required('nocode_builder')
def set_portal_user_roles(ss_sc, user_sc):
    if not _get_owned_sub_system(ss_sc):
        return jsonify({'success': False, 'error': _('Sub system not found')}), 404
    data = request.get_json() or {}
    try:
        ok, error = svc.set_user_roles(ss_sc, user_sc, data.get('role_codes'))
    except FileNotFoundError:
        return _portal_db_not_found()
    if error:
        return _bad_request(error)
    return _ok({'secure_code': user_sc, 'roles': data.get('role_codes') or []}, '帳號角色已更新')


@api_bp.route('/sub-systems/<ss_sc>/portal/users/<user_sc>/permission-override', methods=['PUT'])
@csrf.exempt
@module_access_required('nocode_builder')
def set_portal_user_permission_override(ss_sc, user_sc):
    if not _get_owned_sub_system(ss_sc):
        return jsonify({'success': False, 'error': _('Sub system not found')}), 404
    data = request.get_json() or {}
    try:
        ok, error = svc.set_user_permission_override(
            ss_sc,
            user_sc,
            data.get('code', ''),
            data.get('effect'),
            data.get('reason', ''),
        )
    except FileNotFoundError:
        return _portal_db_not_found()
    if error:
        return _bad_request(error)
    return _ok({'secure_code': user_sc, 'code': data.get('code'), 'effect': data.get('effect')}, '帳號權限覆寫已更新')


@api_bp.route('/sub-systems/<ss_sc>/portal/permission-templates/<template_code>/apply', methods=['POST'])
@csrf.exempt
@module_access_required('nocode_builder')
def apply_portal_permission_template(ss_sc, template_code):
    if not _get_owned_sub_system(ss_sc):
        return jsonify({'success': False, 'error': _('Sub system not found')}), 404
    try:
        result, error = svc.apply_permission_template(ss_sc, template_code)
    except FileNotFoundError:
        return _portal_db_not_found()
    if error:
        return _bad_request(error)
    return _ok(result, '權限模板已套用')
