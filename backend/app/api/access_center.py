"""
BeakPlatform Access Center API
權限管理中心 API
"""
from flask import Blueprint, jsonify, request
from flask_babel import gettext as _
from flask_login import current_user

from ..models.user import User
from ..security.decorators import admin_required
from ..services.role_assignment_service import (
    assign_role,
    list_account_roles,
    revoke_assignment,
)
from ..services.unit_resolver import resolve_role_holders


access_center_api_bp = Blueprint(
    'access_center_api',
    __name__,
    url_prefix='/api/access',
)


@access_center_api_bp.route('/ping', methods=['GET'])
@admin_required
def ping():
    """Access Center API smoke check."""
    return jsonify({'ok': True})


@access_center_api_bp.route('/account-roles', methods=['GET'])
@admin_required
def account_roles():
    """List account role assignments for the current organization."""
    data = list_account_roles(
        current_user.org_secure_code,
        account_type=request.args.get('account_type'),
        keyword=request.args.get('keyword'),
        page=request.args.get('page', 1, type=int),
    )
    return jsonify(data)


@access_center_api_bp.route('/assign', methods=['POST'])
@admin_required
def assign():
    """Assign a role to a user in the current organization."""
    data = request.get_json(silent=True) or {}
    user_sc = data.get('user_secure_code')
    role_sc = data.get('role_secure_code')

    if not user_sc or not role_sc:
        return jsonify({'success': False, 'error': _('缺少必要參數')}), 400

    # PF-251 第 3a 期：性質（regular／proxy／standby）與代理欄位；規則全部在 assign_role() 內判定
    try:
        result = assign_role(
            current_user.org_secure_code,
            user_sc,
            role_sc,
            unit_sc=data.get('unit_secure_code'),
            kind=data.get('kind') or 'regular',
            acting_for_sc=data.get('acting_for_secure_code'),
            valid_from=data.get('valid_from'),
            valid_until=data.get('valid_until'),
            allowed_form_templates=data.get('allowed_form_templates'),
            grant_reason=data.get('grant_reason'),
        )
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400

    return jsonify({'success': True, **result})


@access_center_api_bp.route('/revoke', methods=['POST'])
@admin_required
def revoke():
    """Revoke one role assignment (by assignment secure_code) in the current organization."""
    data = request.get_json(silent=True) or {}
    assignment_sc = data.get('assignment_secure_code')

    if not assignment_sc:
        return jsonify({'success': False, 'error': _('缺少必要參數')}), 400

    try:
        result = revoke_assignment(current_user.org_secure_code, assignment_sc)
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400

    return jsonify({'success': True, **result})


@access_center_api_bp.route('/role-holders', methods=['GET'])
@admin_required
def role_holders():
    """該角色@單位今天有效的正式（regular）持有者，供「被代理人」下拉（PF-251 第 3a 期）。"""
    role_sc = (request.args.get('role_secure_code') or '').strip()
    unit_sc = (request.args.get('unit_secure_code') or '').strip() or None
    if not role_sc:
        return jsonify({'success': False, 'error': _('缺少必要參數')}), 400

    org_sc = current_user.org_secure_code
    holders = resolve_role_holders(role_sc, org_sc, unit_sc, kinds=('regular',))
    users = []
    if holders:
        rows = User.query.filter(
            User.org_secure_code == org_sc,
            User.secure_code.in_(holders),
            User.is_deleted == False,  # noqa: E712
            User.is_active == True,  # noqa: E712
        ).all()
        by_sc = {u.secure_code: u for u in rows}
        users = [
            {
                'secure_code': sc,
                'display_name': by_sc[sc].display_name or by_sc[sc].username,
                'employee_id': by_sc[sc].employee_id,
            }
            for sc in holders if sc in by_sc
        ]
    return jsonify({'success': True, 'holders': users})
