"""Personal delegation endpoints."""
import logging
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_babel import gettext as _
from flask_login import current_user

from app import db
from ..models.delegation import Delegation, DelegationStatus, DelegationType
from ..models.user import User, UserType
from ..security.decorators import login_required
from ..security.resource_gateway import ResourceGateway

logger = logging.getLogger(__name__)

my_delegations_bp = Blueprint(
    'api_my_delegations',
    __name__,
    url_prefix='/api/my-delegations',
)


def _deny_non_member():
    if current_user.is_employee or current_user.is_org_admin:
        return None
    return jsonify({
        'success': False,
        'error': 'forbidden',
        'message': _('此功能僅限企業成員使用'),
    }), 403


def _candidate_users():
    # EMPLOYEE 不持有 user:read；候選集合已由登入者企業與成員身分限縮。
    users = ResourceGateway.filter(
        User,
        is_deleted=False,
        is_active=True,
        is_service_account=False,
        order_by='display_name',
        check_permission=False,
    )
    return [
        user for user in users
        if user.user_type in (UserType.EMPLOYEE, UserType.ORG_ADMIN)
        and user.secure_code != current_user.secure_code
    ]


def _candidate_payload(user):
    return {
        'secure_code': user.secure_code,
        'display_name': user.display_name,
        'employee_id': user.employee_id,
    }


def _parse_date(value):
    return datetime.strptime((value or '').strip(), '%Y-%m-%d').date()


@my_delegations_bp.route('', methods=['GET'])
@login_required
def list_my_delegations():
    denied = _deny_non_member()
    if denied:
        return denied

    # EMPLOYEE 不持有 delegation:read；本端點以 delegator/delegate＝本人限縮，不需集合權限
    given = ResourceGateway.filter(
        Delegation,
        delegator_secure_code=current_user.secure_code,
        is_deleted=False,
        order_by='-created_at',
        check_permission=False,
    )
    # EMPLOYEE 不持有 delegation:read；本端點以 delegator/delegate＝本人限縮，不需集合權限
    received = ResourceGateway.filter(
        Delegation,
        delegate_secure_code=current_user.secure_code,
        is_deleted=False,
        order_by='-created_at',
        check_permission=False,
    )
    return jsonify({
        'success': True,
        'data': {
            'given': [d.to_dict() for d in given],
            'received': [d.to_dict() for d in received],
            'today': current_user.organization.local_today().isoformat(),
        },
    })


@my_delegations_bp.route('/candidates', methods=['GET'])
@login_required
def list_my_delegation_candidates():
    denied = _deny_non_member()
    if denied:
        return denied
    return jsonify({
        'success': True,
        'data': [_candidate_payload(user) for user in _candidate_users()],
    })


@my_delegations_bp.route('', methods=['POST'])
@login_required
def create_my_delegation():
    denied = _deny_non_member()
    if denied:
        return denied

    payload = request.get_json(silent=True) or {}
    delegate_sc = (payload.get('delegate_secure_code') or '').strip()
    candidates = {user.secure_code for user in _candidate_users()}
    if delegate_sc not in candidates:
        return jsonify({
            'success': False,
            'error': 'invalid_delegate',
            'message': _('被授權人無效'),
        }), 400

    try:
        effective_from = _parse_date(payload.get('effective_from'))
        effective_until = _parse_date(payload.get('effective_until'))
    except ValueError:
        return jsonify({
            'success': False,
            'error': 'invalid_date',
            'message': _('日期格式錯誤'),
        }), 400

    if effective_from > effective_until:
        return jsonify({
            'success': False,
            'error': 'invalid_range',
            'message': _('生效開始日期不能晚於結束日期'),
        }), 400

    if effective_until < current_user.organization.local_today():
        return jsonify({
            'success': False,
            'error': 'expired_range',
            'message': _('生效結束日期不能早於今天'),
        }), 400

    reason = (payload.get('reason') or '').strip()[:1000] or None
    try:
        delegation = ResourceGateway.create(
            Delegation,
            check_permission=False,  # EMPLOYEE 不持有 delegation:create；授權人強制為本人，見上方身分規則
            delegator_secure_code=current_user.secure_code,
            delegate_secure_code=delegate_sc,
            delegation_type=DelegationType.FULL,
            status=DelegationStatus.PENDING,
            effective_from=effective_from,
            effective_until=effective_until,
            approval_limit=None,
            reason=reason,
            created_by=current_user.display_name,
        )
        delegation.check_and_update_status()
        db.session.commit()
        return jsonify({'success': True, 'data': delegation.to_dict()}), 201
    except Exception:
        db.session.rollback()
        logger.exception('my_delegations: create failed user_sc=%s', current_user.secure_code)
        return jsonify({
            'success': False,
            'error': 'server_error',
            'message': _('建立失敗'),
        }), 500


@my_delegations_bp.route('/<secure_code>/revoke', methods=['POST'])
@login_required
def revoke_my_delegation(secure_code):
    denied = _deny_non_member()
    if denied:
        return denied

    # EMPLOYEE 不持有 delegation:read；本端點取回後仍強制 delegator＝本人。
    delegation = ResourceGateway.get(
        Delegation,
        secure_code,
        raise_on_not_found=False,
        check_permission=False,
    )
    if (
        delegation is None
        or delegation.is_deleted
        or delegation.delegator_secure_code != current_user.secure_code
    ):
        return jsonify({
            'success': False,
            'error': 'not_found',
            'message': _('找不到代理授權'),
        }), 404

    if delegation.status == DelegationStatus.REVOKED:
        return jsonify({
            'success': False,
            'error': 'already_revoked',
            'message': _('這筆代理授權已撤銷'),
        }), 400

    payload = request.get_json(silent=True) or {}
    revoke_reason = (payload.get('revoke_reason') or '').strip()[:500] or None
    try:
        delegation.revoke(current_user.display_name, revoke_reason)
        db.session.commit()
        return jsonify({'success': True, 'data': delegation.to_dict()})
    except Exception:
        db.session.rollback()
        logger.exception('my_delegations: revoke failed delegation_sc=%s', secure_code)
        return jsonify({
            'success': False,
            'error': 'server_error',
            'message': _('撤銷失敗'),
        }), 500
