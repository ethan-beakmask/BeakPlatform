"""Personal proxy assignment endpoints."""
import logging

from flask import Blueprint, jsonify
from flask_babel import gettext as _
from flask_login import current_user

from app.security.decorators import login_required
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
