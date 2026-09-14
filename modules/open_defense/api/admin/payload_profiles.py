"""Admin API:payload profiles CRUD + 試算"""
import logging
from datetime import datetime

from flask import jsonify, request
from flask_babel import gettext as _
from flask_login import current_user

from app import db
from app.security.decorators import admin_required
from app.services.capability_service import permission_required

from . import admin_bp
from ...models import OdFormTemplateMapping, OdPayloadProfile
from ...services import payload_profile_service

logger = logging.getLogger(__name__)


def _error(code, message, status=400):
    return jsonify({'error': code, 'message': message}), status


def _profile_payload(record):
    return record.to_dict()


def _string_or_none(value):
    if value in (None, ''):
        return None
    return str(value).strip() or None


def _duplicate_code(org_sc, code, exclude_secure_code=None):
    query = OdPayloadProfile.query.filter_by(
        org_secure_code=org_sc,
        code=code,
        is_deleted=False,
    )
    if exclude_secure_code:
        query = query.filter(OdPayloadProfile.secure_code != exclude_secure_code)
    return query.first() is not None


@admin_bp.route('/payload-profiles', methods=['GET'])
@admin_required
@permission_required('open_defense.admin')
def list_payload_profiles():
    rows = OdPayloadProfile.query.filter_by(
        org_secure_code=current_user.org_secure_code,
        is_deleted=False,
    ).order_by(
        OdPayloadProfile.code.asc(),
        OdPayloadProfile.id.asc(),
    ).all()
    return jsonify({'payload_profiles': [_profile_payload(r) for r in rows]})


@admin_bp.route('/payload-profiles', methods=['POST'])
@admin_required
@permission_required('open_defense.admin')
def create_payload_profile():
    body = request.get_json(force=True, silent=True) or {}
    ok, message = payload_profile_service.validate_profile_payload(body)
    if not ok:
        return _error('invalid_payload_profile', message, 400)

    org_sc = current_user.org_secure_code
    code = body.get('code').strip()
    if _duplicate_code(org_sc, code):
        return _error('duplicate_code', _('code 在本企業內已存在'), 400)

    record = OdPayloadProfile(
        org_secure_code=org_sc,
        code=code,
        name=body.get('name').strip(),
        source_system=body.get('source_system').strip(),
        correlation_id_path=body.get('correlation_id_path').strip(),
        field_map=body.get('field_map') or {},
        severity_map=body.get('severity_map'),
        detail_path=_string_or_none(body.get('detail_path')),
        detail_item_key=_string_or_none(body.get('detail_item_key')),
        detail_columns=body.get('detail_columns'),
        subject_detail_key=_string_or_none(body.get('subject_detail_key')),
        kv_expansions=body.get('kv_expansions'),
        is_active=bool(body.get('is_active', True)),
        note=_string_or_none(body.get('note')),
    )
    db.session.add(record)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception('create od payload profile failed')
        return _error('save_failed', _('儲存來源格式設定檔失敗'), 500)

    return jsonify({'success': True, 'payload_profile': _profile_payload(record)}), 201


@admin_bp.route('/payload-profiles/<secure_code>', methods=['GET'])
@admin_required
@permission_required('open_defense.admin')
def get_payload_profile(secure_code):
    record = OdPayloadProfile.query.filter_by(
        secure_code=secure_code,
        org_secure_code=current_user.org_secure_code,
        is_deleted=False,
    ).first()
    if not record:
        return _error('not_found', _('來源格式設定檔不存在'), 404)
    return jsonify({'payload_profile': _profile_payload(record)})


@admin_bp.route('/payload-profiles/<secure_code>', methods=['PUT'])
@admin_required
@permission_required('open_defense.admin')
def update_payload_profile(secure_code):
    org_sc = current_user.org_secure_code
    record = OdPayloadProfile.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org_sc,
        is_deleted=False,
    ).first()
    if not record:
        return _error('not_found', _('來源格式設定檔不存在'), 404)

    body = request.get_json(force=True, silent=True) or {}
    merged = record.to_dict()
    merged.update(body)
    ok, message = payload_profile_service.validate_profile_payload(merged)
    if not ok:
        return _error('invalid_payload_profile', message, 400)

    code = merged.get('code').strip()
    if _duplicate_code(org_sc, code, exclude_secure_code=secure_code):
        return _error('duplicate_code', _('code 在本企業內已存在'), 400)

    record.code = code
    record.name = merged.get('name').strip()
    record.source_system = merged.get('source_system').strip()
    record.correlation_id_path = merged.get('correlation_id_path').strip()
    record.field_map = merged.get('field_map') or {}
    record.severity_map = merged.get('severity_map')
    record.detail_path = _string_or_none(merged.get('detail_path'))
    record.detail_item_key = _string_or_none(merged.get('detail_item_key'))
    record.detail_columns = merged.get('detail_columns')
    record.subject_detail_key = _string_or_none(merged.get('subject_detail_key'))
    record.kv_expansions = merged.get('kv_expansions')
    record.is_active = bool(merged.get('is_active', True))
    record.note = _string_or_none(merged.get('note'))

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception('update od payload profile failed secure_code=%s', secure_code)
        return _error('save_failed', _('儲存來源格式設定檔失敗'), 500)

    return jsonify({'success': True, 'payload_profile': _profile_payload(record)})


@admin_bp.route('/payload-profiles/<secure_code>', methods=['DELETE'])
@admin_required
@permission_required('open_defense.admin')
def delete_payload_profile(secure_code):
    record = OdPayloadProfile.query.filter_by(
        secure_code=secure_code,
        org_secure_code=current_user.org_secure_code,
        is_deleted=False,
    ).first()
    if not record:
        return _error('not_found', _('來源格式設定檔不存在'), 404)

    has_native_rules = OdFormTemplateMapping.query.filter_by(
        org_secure_code=current_user.org_secure_code,
        payload_kind='native',
        is_deleted=False,
        is_active=True,
    ).first() is not None

    record.is_deleted = True
    record.deleted_at = datetime.utcnow()
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception('delete od payload profile failed secure_code=%s', secure_code)
        return _error('save_failed', _('刪除來源格式設定檔失敗'), 500)

    response = {'success': True}
    if has_native_rules:
        response['warning'] = _('目前仍有啟用中的 native 路由規則,請確認規則設定')
    return jsonify(response)


@admin_bp.route('/payload-profiles/<secure_code>/test', methods=['POST'])
@admin_required
@permission_required('open_defense.admin')
def test_payload_profile(secure_code):
    record = OdPayloadProfile.query.filter_by(
        secure_code=secure_code,
        org_secure_code=current_user.org_secure_code,
        is_deleted=False,
    ).first()
    if not record:
        return _error('not_found', _('來源格式設定檔不存在'), 404)

    body = request.get_json(force=True, silent=True) or {}
    payload = body.get('payload')
    if not isinstance(payload, dict):
        return _error('invalid_payload', _('payload 必須為物件'), 400)

    correlation_id = payload_profile_service.resolve_correlation_id(payload, record)
    axis = payload_profile_service.normalize_axis_fields(payload, record)
    details = payload_profile_service.extract_details(
        payload,
        record.detail_path,
        record.detail_item_key,
    ) if record.detail_path else []
    flat = payload_profile_service.flatten_payload(
        payload,
        kv_expansions=record.kv_expansions,
        detail_path=record.detail_path,
    )
    form_data = payload_profile_service.build_native_form_data(payload, record)
    preview = dict(list(form_data.items())[:50])

    return jsonify({
        'correlation_id': correlation_id,
        'axis': axis,
        'detail_count': len(details),
        'flat_key_count': len(flat),
        'form_data_preview': preview,
    })
