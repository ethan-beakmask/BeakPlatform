"""
BeakPlatform API Key Management API

企業級 API Key 管理(/security/api-keys 頁面後端)。
規格: docs/API_KEY_TRIGGER_SPEC.md §4

安全設計:
- 所有端點 @admin_required,強制以 current_user.org_secure_code 為租戶軸
- secret 僅建立當下回傳一次,任何查詢端點都不回 secret
- scopes 為 JSONB 原樣存放,語意由消費端(如 form_workflow 閘道)解釋
"""
import logging
from datetime import datetime

from flask import Blueprint, request, jsonify
from flask_babel import gettext as _
from flask_login import current_user

from ..security.decorators import admin_required
from ..services import api_key_service
from ..services.api_key_service import ApiKeyError
from ..models.user import User

logger = logging.getLogger(__name__)

api_keys_bp = Blueprint(
    'api_api_keys', __name__,
    url_prefix='/api/security/api-keys'
)


def _parse_expires_at(value):
    """解析期限輸入(ISO 日期或 datetime 字串);空值回 None"""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        raise ApiKeyError(_('expires_at 格式錯誤(需 ISO 8601)'))
    return dt


def _validate_applicant(applicant_sc):
    """驗證綁定帳號屬同企業且可用(DATA-01);空值回 None"""
    if not applicant_sc:
        return None
    user = User.query.filter_by(
        secure_code=applicant_sc,
        org_secure_code=current_user.org_secure_code,
        is_deleted=False,
        is_active=True,
    ).first()
    if not user:
        raise ApiKeyError(_('綁定的系統帳號不存在或已停用'))
    return user.secure_code


def _get_key_or_404(secure_code):
    record = api_key_service.get_key_by_sc(
        secure_code, current_user.org_secure_code)
    return record


@api_keys_bp.route('', methods=['GET'])
@admin_required
def list_api_keys():
    """列出本企業所有 API Key(不含已撤銷)"""
    records = api_key_service.list_keys(current_user.org_secure_code)
    return jsonify({'success': True, 'data': [r.to_dict() for r in records]})


@api_keys_bp.route('', methods=['POST'])
@admin_required
def create_api_key():
    """建立 API Key,secret 僅此回應顯示一次"""
    data = request.get_json() or {}
    try:
        record, secret = api_key_service.create_api_key(
            org_secure_code=current_user.org_secure_code,
            name=data.get('name') or '',
            consumer_label=data.get('consumer_label'),
            description=data.get('description'),
            scopes=data.get('scopes') or {},
            allowed_ips=data.get('allowed_ips'),
            applicant_user_secure_code=_validate_applicant(
                data.get('applicant_user_secure_code')),
            expires_at=_parse_expires_at(data.get('expires_at')),
            created_by_secure_code=current_user.secure_code,
        )
    except ApiKeyError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400

    payload = record.to_dict()
    payload['secret'] = secret  # 一次性,前端須立即提示保存
    return jsonify({'success': True, 'data': payload}), 201


@api_keys_bp.route('/<secure_code>', methods=['PATCH'])
@admin_required
def update_api_key(secure_code):
    """更新 key 屬性(secret 不可改)"""
    record = _get_key_or_404(secure_code)
    if not record:
        return jsonify({'success': False, 'error': _('找不到指定的 API Key')}), 404

    data = request.get_json() or {}
    kwargs = {}
    if 'name' in data:
        kwargs['name'] = data.get('name') or ''
    if 'consumer_label' in data:
        kwargs['consumer_label'] = data.get('consumer_label') or ''
    if 'description' in data:
        kwargs['description'] = data.get('description') or ''
    if 'scopes' in data:
        kwargs['scopes'] = data.get('scopes') or {}
    if 'allowed_ips' in data:
        kwargs['allowed_ips'] = data.get('allowed_ips')
    try:
        if 'applicant_user_secure_code' in data:
            kwargs['applicant_user_secure_code'] = _validate_applicant(
                data.get('applicant_user_secure_code'))
        if 'expires_at' in data:
            kwargs['expires_at'] = _parse_expires_at(data.get('expires_at'))
        record = api_key_service.update_key(record, **kwargs)
    except ApiKeyError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400

    return jsonify({'success': True, 'data': record.to_dict()})


@api_keys_bp.route('/<secure_code>/suspend', methods=['POST'])
@admin_required
def suspend_api_key(secure_code):
    """暫停 key(可復原)"""
    record = _get_key_or_404(secure_code)
    if not record:
        return jsonify({'success': False, 'error': _('找不到指定的 API Key')}), 404

    data = request.get_json() or {}
    reason = (data.get('reason') or '').strip()
    if not reason:
        return jsonify({'success': False, 'error': _('請填寫暫停原因')}), 400
    try:
        api_key_service.suspend_key(
            record, reason, operator_secure_code=current_user.secure_code)
    except ApiKeyError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    return jsonify({'success': True, 'data': record.to_dict()})


@api_keys_bp.route('/<secure_code>/resume', methods=['POST'])
@admin_required
def resume_api_key(secure_code):
    """復原被暫停的 key"""
    record = _get_key_or_404(secure_code)
    if not record:
        return jsonify({'success': False, 'error': _('找不到指定的 API Key')}), 404
    try:
        api_key_service.resume_key(
            record, operator_secure_code=current_user.secure_code)
    except ApiKeyError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    return jsonify({'success': True, 'data': record.to_dict()})


@api_keys_bp.route('/<secure_code>', methods=['DELETE'])
@admin_required
def revoke_api_key(secure_code):
    """撤銷 key(不可復原)"""
    record = _get_key_or_404(secure_code)
    if not record:
        return jsonify({'success': False, 'error': _('找不到指定的 API Key')}), 404
    api_key_service.revoke_key(
        record, operator_secure_code=current_user.secure_code)
    return jsonify({'success': True})
