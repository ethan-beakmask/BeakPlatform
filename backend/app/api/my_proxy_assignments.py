"""Personal proxy assignment endpoints."""
import logging
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_babel import gettext as _
from flask_login import current_user

from app.models.user import User, UserType
from app.security.decorators import login_required
from app.security.resource_gateway import ResourceGateway
from app.services import proxy_assignment_service

logger = logging.getLogger(__name__)

my_proxy_assignments_bp = Blueprint(
    'api_my_proxy_assignments',
    __name__,
    url_prefix='/api/my-proxy-assignments',
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


@my_proxy_assignments_bp.route('', methods=['GET'])
@login_required
def list_my_proxy_assignments():
    denied = _deny_non_member()
    if denied:
        return denied
    data = proxy_assignment_service.list_proxy_assignments(
        current_user.org_secure_code,
        current_user.secure_code,
    )
    return jsonify({'success': True, 'data': data})


@my_proxy_assignments_bp.route('/candidates', methods=['GET'])
@login_required
def list_my_proxy_assignment_candidates():
    denied = _deny_non_member()
    if denied:
        return denied
    return jsonify({
        'success': True,
        'data': [_candidate_payload(user) for user in _candidate_users()],
    })


@my_proxy_assignments_bp.route('/my-roles', methods=['GET'])
@login_required
def list_my_proxyable_roles():
    denied = _deny_non_member()
    if denied:
        return denied
    today = current_user.organization.local_today()
    rows = proxy_assignment_service.proxyable_regular_assignments(
        current_user.org_secure_code,
        current_user.secure_code,
        today,
    )
    return jsonify({
        'success': True,
        'data': [
            {
                'role_secure_code': row.role.secure_code if row.role else row.role_secure_code,
                'role_name': row.role.name if row.role else row.role_secure_code,
                'unit_secure_code': row.unit_secure_code,
                'unit_name': row.unit.name if row.unit else '',
            }
            for row in rows
        ],
    })


@my_proxy_assignments_bp.route('', methods=['POST'])
@login_required
def create_my_proxy_assignment():
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
            'message': _('代理人無效'),
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

    reason = (payload.get('reason') or '').strip()
    if not reason:
        return jsonify({
            'success': False,
            'error': 'reason_required',
            'message': _('請填寫指派事由'),
        }), 400

    try:
        result = proxy_assignment_service.create_full_proxy(
            current_user.org_secure_code,
            current_user._get_current_object(),
            delegate_sc,
            effective_from,
            effective_until,
            reason[:1000],
        )
        return jsonify({
            'success': True,
            'data': {'created': result['created'], 'skipped': result['skipped']},
        }), 201
    except ValueError as exc:
        return jsonify({
            'success': False,
            'error': 'invalid_request',
            'message': str(exc),
        }), 400
    except Exception:
        logger.exception('my_proxy_assignments: create failed user_sc=%s', current_user.secure_code)
        return jsonify({
            'success': False,
            'error': 'server_error',
            'message': _('建立失敗'),
        }), 500


@my_proxy_assignments_bp.route('/<assignment_sc>/revoke', methods=['POST'])
@login_required
def revoke_my_proxy_assignment(assignment_sc):
    denied = _deny_non_member()
    if denied:
        return denied

    try:
        result = proxy_assignment_service.revoke_own_proxy(
            current_user.org_secure_code,
            current_user.secure_code,
            assignment_sc,
        )
        return jsonify({'success': True, 'data': result})
    except LookupError:
        return jsonify({
            'success': False,
            'error': 'not_found',
            'message': _('找不到代理指派'),
        }), 404
    except Exception:
        logger.exception('my_proxy_assignments: revoke failed assignment_sc=%s', assignment_sc)
        return jsonify({
            'success': False,
            'error': 'server_error',
            'message': _('撤銷失敗'),
        }), 500
