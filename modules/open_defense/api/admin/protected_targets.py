"""Admin API:protected targets CRUD + 試算"""
import logging
from datetime import datetime

from flask import jsonify, request
from flask_babel import gettext as _
from flask_login import current_user

from app import db
from app.security.decorators import admin_required
from app.services.capability_service import permission_required

from . import admin_bp
from ...models import OdProtectedTarget, VALID_PROTECTED_ENTRY_TYPES
from ...services.protected_target_service import (
    InvalidTargetValueError,
    describe_protection,
    list_effective_networks,
    parse_target_network,
)

logger = logging.getLogger(__name__)


def _error(code, message, status=400):
    return jsonify({'error': code, 'message': message}), status


def _string_or_none(value):
    if value in (None, ''):
        return None
    return str(value).strip() or None


def _normalize_target_value(value):
    if not value or not str(value).strip():
        raise InvalidTargetValueError('empty target_value')
    return str(parse_target_network(str(value)))


def _duplicate_target(org_sc, entry_type, target_value, exclude_secure_code=None):
    query = OdProtectedTarget.query.filter_by(
        org_secure_code=org_sc,
        entry_type=entry_type,
        target_value=target_value,
        is_deleted=False,
    )
    if exclude_secure_code:
        query = query.filter(OdProtectedTarget.secure_code != exclude_secure_code)
    return query.first() is not None


def _record_payload(record):
    return record.to_dict()


@admin_bp.route('/protected-targets', methods=['GET'])
@admin_required
@permission_required('open_defense.admin')
def list_protected_targets():
    rows = OdProtectedTarget.query.filter_by(
        org_secure_code=current_user.org_secure_code,
        is_deleted=False,
    ).order_by(
        OdProtectedTarget.entry_type.asc(),
        OdProtectedTarget.target_value.asc(),
        OdProtectedTarget.id.asc(),
    ).all()
    builtin, config = list_effective_networks()
    return jsonify({
        'protected_targets': [_record_payload(r) for r in rows],
        'builtin_networks': builtin,
        'config_networks': config,
    })


@admin_bp.route('/protected-targets', methods=['POST'])
@admin_required
@permission_required('open_defense.admin')
def create_protected_target():
    body = request.get_json(force=True, silent=True) or {}
    org_sc = current_user.org_secure_code

    entry_type = body.get('entry_type')
    if entry_type not in VALID_PROTECTED_ENTRY_TYPES:
        return _error('invalid_entry_type', _('entry_type 不合法'), 400)

    try:
        target_value = _normalize_target_value(body.get('target_value'))
    except InvalidTargetValueError:
        return _error('invalid_target_value', _('target_value 不是合法的 IP 或 CIDR'), 400)

    if _duplicate_target(org_sc, entry_type, target_value):
        return _error('duplicate', _('同類型目標已存在'), 409)

    record = OdProtectedTarget(
        org_secure_code=org_sc,
        entry_type=entry_type,
        target_value=target_value,
        name=_string_or_none(body.get('name')),
        is_active=bool(body.get('is_active', True)),
        note=_string_or_none(body.get('note')),
        created_by_secure_code=current_user.secure_code,
    )
    db.session.add(record)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception('create od protected target failed')
        return _error('save_failed', _('儲存保護清單失敗'), 500)

    return jsonify({'success': True, 'protected_target': _record_payload(record)}), 201


@admin_bp.route('/protected-targets/<secure_code>', methods=['PUT'])
@admin_required
@permission_required('open_defense.admin')
def update_protected_target(secure_code):
    org_sc = current_user.org_secure_code
    record = OdProtectedTarget.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org_sc,
        is_deleted=False,
    ).first()
    if not record:
        return _error('not_found', _('保護清單項目不存在'), 404)

    body = request.get_json(force=True, silent=True) or {}
    next_entry_type = record.entry_type
    next_target_value = record.target_value

    if 'entry_type' in body:
        if body.get('entry_type') not in VALID_PROTECTED_ENTRY_TYPES:
            return _error('invalid_entry_type', _('entry_type 不合法'), 400)
        next_entry_type = body.get('entry_type')

    if 'target_value' in body:
        try:
            next_target_value = _normalize_target_value(body.get('target_value'))
        except InvalidTargetValueError:
            return _error('invalid_target_value', _('target_value 不是合法的 IP 或 CIDR'), 400)

    if _duplicate_target(org_sc, next_entry_type, next_target_value, exclude_secure_code=secure_code):
        return _error('duplicate', _('同類型目標已存在'), 409)

    if 'entry_type' in body:
        record.entry_type = next_entry_type
    if 'target_value' in body:
        record.target_value = next_target_value
    if 'name' in body:
        record.name = _string_or_none(body.get('name'))
    if 'note' in body:
        record.note = _string_or_none(body.get('note'))
    if 'is_active' in body:
        record.is_active = bool(body.get('is_active'))

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception('update od protected target failed secure_code=%s', secure_code)
        return _error('save_failed', _('儲存保護清單失敗'), 500)

    return jsonify({'success': True, 'protected_target': _record_payload(record)})


@admin_bp.route('/protected-targets/<secure_code>', methods=['DELETE'])
@admin_required
@permission_required('open_defense.admin')
def delete_protected_target(secure_code):
    record = OdProtectedTarget.query.filter_by(
        secure_code=secure_code,
        org_secure_code=current_user.org_secure_code,
        is_deleted=False,
    ).first()
    if not record:
        return _error('not_found', _('保護清單項目不存在'), 404)

    record.is_deleted = True
    record.deleted_at = datetime.utcnow()
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception('delete od protected target failed secure_code=%s', secure_code)
        return _error('save_failed', _('刪除保護清單失敗'), 500)

    return jsonify({'success': True})


@admin_bp.route('/protected-targets/test', methods=['POST'])
@admin_required
@permission_required('open_defense.admin')
def test_protected_target():
    body = request.get_json(force=True, silent=True) or {}
    return jsonify(describe_protection(
        org_secure_code=current_user.org_secure_code,
        target_value=body.get('target_value') or '',
    ))
