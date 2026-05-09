"""Admin API:intake keys CRUD"""
from datetime import datetime

from flask import request, jsonify
from flask_login import current_user

from app import db, csrf
from app.security.decorators import admin_required

from . import admin_bp
from ...models import OdIntakeKey
from ...services.intake_key_service import (
    create_intake_key, revoke_key, IntakeKeyError,
)


@admin_bp.route('/intake-keys', methods=['GET'])
@admin_required
def list_intake_keys():
    org_sc = current_user.org_secure_code
    rows = OdIntakeKey.query.filter_by(
        org_secure_code=org_sc, is_deleted=False,
    ).order_by(OdIntakeKey.created_at.desc()).all()
    return jsonify({
        'keys': [r.to_dict() for r in rows],
    })


@admin_bp.route('/intake-keys', methods=['POST'])
@admin_required
def create_intake_key_api():
    body = request.get_json(force=True, silent=True) or {}
    name = (body.get('name') or '').strip()
    sources = body.get('allowed_source_systems') or []
    if isinstance(sources, str):
        sources = [s.strip() for s in sources.split(',') if s.strip()]
    expires_at_str = body.get('expires_at')
    expires_at = None
    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(
                expires_at_str.replace('Z', '+00:00'))
            if expires_at.tzinfo is not None:
                expires_at = expires_at.astimezone(tz=None).replace(tzinfo=None)
        except ValueError:
            return jsonify({'error': 'invalid_expires_at'}), 400

    try:
        record, secret_b64 = create_intake_key(
            org_secure_code=current_user.org_secure_code,
            name=name,
            allowed_source_systems=sources,
            created_by_secure_code=current_user.secure_code,
            expires_at=expires_at,
        )
    except IntakeKeyError as exc:
        return jsonify({'error': 'validation_error',
                        'message': str(exc)}), 400

    return jsonify({
        'success': True,
        'key': record.to_dict(),
        'secret_b64': secret_b64,  # 一次性顯示
    }), 201


@admin_bp.route('/intake-keys/<secure_code>', methods=['DELETE'])
@admin_required
def revoke_intake_key_api(secure_code):
    org_sc = current_user.org_secure_code
    record = OdIntakeKey.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org_sc,
        is_deleted=False,
    ).first()
    if not record:
        return jsonify({'error': 'not_found'}), 404
    revoke_key(record)
    return jsonify({'success': True})
