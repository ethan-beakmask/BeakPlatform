"""Admin API:service accounts CRUD"""
from datetime import datetime

from flask import request, jsonify
from flask_login import current_user

from app import db
from app.security.decorators import admin_required

from . import admin_bp
from ...models import OdServiceAccount
from ...services.service_account_service import (
    create_service_account, ServiceAccountError,
)


@admin_bp.route('/service-accounts', methods=['GET'])
@admin_required
def list_service_accounts():
    rows = OdServiceAccount.query.filter_by(
        org_secure_code=current_user.org_secure_code,
        is_deleted=False,
    ).order_by(OdServiceAccount.created_at.desc()).all()
    out = []
    for r in rows:
        d = r.to_dict()
        # 加 lock 狀態 flag,前端方便顯示
        d['is_locked'] = bool(r.lock_until and r.lock_until > datetime.utcnow())
        d['failed_login_count'] = r.failed_login_count or 0
        out.append(d)
    return jsonify({'accounts': out})


@admin_bp.route('/service-accounts', methods=['POST'])
@admin_required
def create_service_account_api():
    body = request.get_json(force=True, silent=True) or {}
    name = (body.get('name') or '').strip()
    eps = body.get('allowed_enforcement_points') or []
    if isinstance(eps, str):
        eps = [s.strip() for s in eps.split(',') if s.strip()]
    sa_id_hint = (body.get('sa_id_hint') or '').strip()

    try:
        record, secret_b64 = create_service_account(
            org_secure_code=current_user.org_secure_code,
            name=name,
            allowed_enforcement_points=eps,
            created_by_secure_code=current_user.secure_code,
            sa_id_hint=sa_id_hint,
        )
    except ServiceAccountError as exc:
        return jsonify({'error': 'validation_error',
                        'message': str(exc)}), 400

    return jsonify({
        'success': True,
        'account': record.to_dict(),
        'sa_secret_b64': secret_b64,  # 一次性
    }), 201


@admin_bp.route('/service-accounts/<secure_code>/unlock', methods=['POST'])
@admin_required
def unlock_service_account_api(secure_code):
    record = OdServiceAccount.query.filter_by(
        secure_code=secure_code,
        org_secure_code=current_user.org_secure_code,
        is_deleted=False,
    ).first()
    if not record:
        return jsonify({'error': 'not_found'}), 404
    record.lock_until = None
    record.failed_login_count = 0
    db.session.commit()
    return jsonify({'success': True})


@admin_bp.route('/service-accounts/<secure_code>', methods=['DELETE'])
@admin_required
def revoke_service_account_api(secure_code):
    record = OdServiceAccount.query.filter_by(
        secure_code=secure_code,
        org_secure_code=current_user.org_secure_code,
        is_deleted=False,
    ).first()
    if not record:
        return jsonify({'error': 'not_found'}), 404
    record.is_active = False
    record.is_deleted = True
    record.deleted_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'success': True})
