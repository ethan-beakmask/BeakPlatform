"""Personal API Key listing and one-time secret claim endpoints."""
import logging
from datetime import datetime

from flask import Blueprint, jsonify
from flask_babel import gettext as _
from flask_login import current_user

from app import db
from ..models.api_key import ApiKey, STATUS_ACTIVE
from ..models.api_key_claim import ApiKeyClaim
from ..security.client_ip import get_client_ip
from ..security.decorators import login_required
from ..services import api_key_claim_service, api_key_service
from ..services.api_key_claim_service import ClaimError

logger = logging.getLogger(__name__)

my_api_keys_bp = Blueprint(
    'api_my_api_keys',
    __name__,
    url_prefix='/api/my-api-keys'
)


def _my_keys_query():
    return ApiKey.query.filter_by(
        org_secure_code=current_user.org_secure_code,
        applicant_user_secure_code=current_user.secure_code,
        is_deleted=False,
    )


def _get_my_key_or_404(key_secure_code):
    if not key_secure_code:
        return None
    return _my_keys_query().filter_by(secure_code=key_secure_code).first()


def _latest_claim(record):
    return ApiKeyClaim.query.filter_by(
        org_secure_code=current_user.org_secure_code,
        api_key_secure_code=record.secure_code,
        is_deleted=False,
    ).order_by(ApiKeyClaim.created_at.desc()).first()


def _claim_state(claim):
    if claim is None:
        return 'none'
    if claim.claimed_at is not None:
        return 'claimed'
    if claim.expires_at < datetime.utcnow():
        return 'expired'
    return 'pending'


def _claim_payload(claim):
    state = _claim_state(claim)
    return {
        'state': state,
        'secure_code': claim.secure_code if claim else None,
        'claimed_at': claim.claimed_at.isoformat() if claim and claim.claimed_at else None,
        'expires_at': claim.expires_at.isoformat() if claim and claim.expires_at else None,
    }


def _triggerable_forms(record):
    try:
        from modules.form_workflow.services.trigger_scope_service import (
            list_triggerable_forms,
        )
    except Exception as exc:
        logger.warning('my_api_keys: trigger scope service unavailable: %s', exc)
        return []

    try:
        return list_triggerable_forms(record, current_user.org_secure_code)
    except Exception:
        logger.exception('my_api_keys: triggerable forms failed key_sc=%s',
                         record.secure_code)
        return []


def _form_instance_payload(claim):
    if not claim or not claim.form_instance_secure_code:
        return None
    try:
        from modules.form_workflow.models import FwFormInstance
    except Exception as exc:
        logger.warning('my_api_keys: form workflow models unavailable: %s', exc)
        return None

    try:
        instance = FwFormInstance.query.filter_by(
            secure_code=claim.form_instance_secure_code,
            org_secure_code=current_user.org_secure_code,
            is_deleted=False,
        ).first()
    except Exception:
        logger.exception('my_api_keys: form instance lookup failed claim_sc=%s',
                         claim.secure_code)
        return None

    if not instance:
        return None
    return {
        'secure_code': instance.secure_code,
        'serial_number': instance.serial_number,
    }


def _key_payload(record):
    claim = _latest_claim(record)
    return {
        'secure_code': record.secure_code,
        'key_id': record.key_id,
        'name': record.name,
        'description': record.description,
        'status': record.status,
        'expires_at': record.expires_at.isoformat() if record.expires_at else None,
        'created_at': record.created_at.isoformat() if record.created_at else None,
        'last_used_at': record.last_used_at.isoformat() if record.last_used_at else None,
        'allowed_ips': record.allowed_ips or [],
        'form_instance': _form_instance_payload(claim),
        'triggerable_forms': _triggerable_forms(record),
        'claim': _claim_payload(claim),
    }


@my_api_keys_bp.route('', methods=['GET'])
@login_required
def list_my_api_keys():
    records = _my_keys_query().order_by(ApiKey.created_at.desc()).all()
    return jsonify({'success': True, 'data': [_key_payload(r) for r in records]})


@my_api_keys_bp.route('/<key_secure_code>/claim', methods=['POST'])
@login_required
def claim_my_api_key(key_secure_code):
    record = _get_my_key_or_404(key_secure_code)
    if not record:
        return jsonify({'success': False, 'error': _('找不到指定的 API Key')}), 404

    claim = _latest_claim(record)
    if _claim_state(claim) != 'pending':
        return jsonify({
            'success': False,
            'error': _('這筆領取憑證已失效或已領取過'),
        }), 400

    try:
        record, secret_b64 = api_key_claim_service.claim_once(
            claim.secure_code,
            current_user.secure_code,
            current_user.org_secure_code,
            source_ip=get_client_ip(),
        )
    except ClaimError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400

    return jsonify({
        'success': True,
        'data': {
            'key_id': record.key_id,
            'secret': secret_b64,
            'claimed_at': claim.claimed_at.isoformat() if claim.claimed_at else None,
        }
    })


@my_api_keys_bp.route('/<key_secure_code>/regenerate', methods=['POST'])
@login_required
def regenerate_my_api_key(key_secure_code):
    record = _get_my_key_or_404(key_secure_code)
    if not record:
        return jsonify({'success': False, 'error': _('找不到指定的 API Key')}), 404
    if record.status != STATUS_ACTIVE:
        return jsonify({'success': False, 'error': _('已停用的 API Key 不可重新產生金鑰')}), 400

    latest_claim = _latest_claim(record)
    record, secret_b64 = api_key_service.regenerate_secret(
        record,
        actor_secure_code=current_user.secure_code,
    )
    claim = api_key_claim_service.create_claim(
        api_key_secure_code=record.secure_code,
        org_secure_code=current_user.org_secure_code,
        beneficiary_user_secure_code=current_user.secure_code,
        form_instance_secure_code=(
            latest_claim.form_instance_secure_code if latest_claim else None
        ),
        ttl_hours=1,
    )
    claim.claimed_at = datetime.utcnow()
    claim.claimed_ip = get_client_ip()
    db.session.commit()

    return jsonify({
        'success': True,
        'data': {
            'key_id': record.key_id,
            'secret': secret_b64,
            'claimed_at': claim.claimed_at.isoformat() if claim.claimed_at else None,
        }
    })
