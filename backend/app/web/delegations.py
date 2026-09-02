"""
BeakMask Delegation Management Web Routes
代理授權管理網頁路由

代理授權用於：
- 主管休假/出差時的職務代理
- 確保簽核流程不會卡住
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from flask import Blueprint, render_template, abort, request, flash, redirect, url_for
from flask_babel import gettext as _
from flask_login import current_user

from ..security.resource_gateway import ResourceGateway
from ..models.delegation import Delegation, DelegationType, DelegationStatus
from ..models.user import User
from .. import db

delegations_bp = Blueprint('delegations', __name__)


@delegations_bp.route('/')
def list_delegations():
    """代理授權列表頁面"""
    result = ResourceGateway.list(
        Delegation,
        page=1,
        per_page=100,
        order_by='-created_at'
    )

    return render_template(
        'pages/delegations/list.html',
        delegations=result['items'],
        pagination=result
    )


@delegations_bp.route('/<secure_code>')
def view_delegation(secure_code: str):
    """查看代理授權詳情"""
    try:
        delegation = ResourceGateway.get(Delegation, secure_code)
    except Exception:
        abort(404)

    return render_template('pages/delegations/view.html', delegation=delegation)


@delegations_bp.route('/create', methods=['GET', 'POST'])
def create_delegation():
    """建立代理授權頁面"""
    users = User.query.filter_by(
        org_secure_code=current_user.org_secure_code,
        is_deleted=False,
        is_active=True
    ).order_by(User.display_name).all()

    delegation_types = [
        (DelegationType.FULL, '全權代理 - 代理所有權限'),
        (DelegationType.APPROVAL, '限額代理 - 設定簽核金額上限'),
        (DelegationType.SPECIFIC, '特定代理 - 限定特定流程類型'),
    ]

    if request.method == 'POST':
        delegator_secure_code = request.form.get('delegator_secure_code', '').strip()
        delegate_secure_code = request.form.get('delegate_secure_code', '').strip()
        delegation_type = request.form.get('delegation_type', DelegationType.FULL)
        effective_from_str = request.form.get('effective_from', '').strip()
        effective_until_str = request.form.get('effective_until', '').strip()
        approval_limit_str = request.form.get('approval_limit', '').strip()
        reason = request.form.get('reason', '').strip() or None

        errors = []

        if not delegator_secure_code:
            errors.append(_('請選擇授權人'))
        if not delegate_secure_code:
            errors.append(_('請選擇被授權人'))
        if delegator_secure_code == delegate_secure_code:
            errors.append(_('授權人和被授權人不能相同'))
        if not effective_from_str:
            errors.append(_('生效開始日期為必填'))
        if not effective_until_str:
            errors.append(_('生效結束日期為必填'))

        effective_from = None
        effective_until = None

        if effective_from_str:
            try:
                effective_from = datetime.strptime(effective_from_str, '%Y-%m-%d').date()
            except ValueError:
                errors.append(_('生效開始日期格式錯誤'))

        if effective_until_str:
            try:
                effective_until = datetime.strptime(effective_until_str, '%Y-%m-%d').date()
            except ValueError:
                errors.append(_('生效結束日期格式錯誤'))

        if effective_from and effective_until and effective_from > effective_until:
            errors.append(_('生效開始日期不能晚於結束日期'))

        approval_limit = None
        if delegation_type == DelegationType.APPROVAL and approval_limit_str:
            try:
                approval_limit = Decimal(approval_limit_str)
                if approval_limit < 0:
                    errors.append(_('簽核金額上限不可為負數'))
            except InvalidOperation:
                errors.append(_('簽核金額上限格式錯誤'))

        if errors:
            for err in errors:
                flash(err, 'error')
        else:
            try:
                delegation = Delegation(
                    org_secure_code=current_user.org_secure_code,
                    delegator_secure_code=delegator_secure_code,
                    delegate_secure_code=delegate_secure_code,
                    delegation_type=delegation_type,
                    status=DelegationStatus.PENDING,
                    effective_from=effective_from,
                    effective_until=effective_until,
                    approval_limit=approval_limit,
                    reason=reason,
                    created_by=current_user.display_name
                )
                # status 只是儲存當下的快照；生效與畫面顯示一律走 effective_status（依企業當地日期）
                delegation.check_and_update_status()
                db.session.add(delegation)
                db.session.commit()

                flash(_('已建立代理授權'), 'success')
                return redirect(url_for('delegations.list_delegations'))
            except Exception as e:
                db.session.rollback()
                flash(_('建立失敗: %(error)s', error=str(e)), 'error')

    return render_template(
        'pages/delegations/create.html',
        users=users,
        delegation_types=delegation_types
    )


@delegations_bp.route('/<secure_code>/edit', methods=['GET', 'POST'])
def edit_delegation(secure_code: str):
    """編輯代理授權頁面"""
    try:
        delegation = ResourceGateway.get(Delegation, secure_code)
    except Exception:
        abort(404)

    users = User.query.filter_by(
        org_secure_code=current_user.org_secure_code,
        is_deleted=False,
        is_active=True
    ).order_by(User.display_name).all()

    delegation_types = [
        (DelegationType.FULL, '全權代理'),
        (DelegationType.APPROVAL, '限額代理'),
        (DelegationType.SPECIFIC, '特定代理'),
    ]

    if request.method == 'POST':
        delegation_type = request.form.get('delegation_type', DelegationType.FULL)
        effective_from_str = request.form.get('effective_from', '').strip()
        effective_until_str = request.form.get('effective_until', '').strip()
        approval_limit_str = request.form.get('approval_limit', '').strip()
        reason = request.form.get('reason', '').strip() or None

        errors = []

        effective_from = delegation.effective_from
        effective_until = delegation.effective_until

        if effective_from_str:
            try:
                effective_from = datetime.strptime(effective_from_str, '%Y-%m-%d').date()
            except ValueError:
                errors.append(_('生效開始日期格式錯誤'))

        if effective_until_str:
            try:
                effective_until = datetime.strptime(effective_until_str, '%Y-%m-%d').date()
            except ValueError:
                errors.append(_('生效結束日期格式錯誤'))

        if effective_from > effective_until:
            errors.append(_('生效開始日期不能晚於結束日期'))

        approval_limit = None
        if delegation_type == DelegationType.APPROVAL and approval_limit_str:
            try:
                approval_limit = Decimal(approval_limit_str)
            except InvalidOperation:
                errors.append(_('簽核金額上限格式錯誤'))

        if errors:
            for err in errors:
                flash(err, 'error')
        else:
            try:
                delegation.delegation_type = delegation_type
                delegation.effective_from = effective_from
                delegation.effective_until = effective_until
                delegation.approval_limit = approval_limit
                delegation.reason = reason

                # 同步 status 快照（依企業當地日期；已撤銷不變更）
                delegation.check_and_update_status()

                db.session.commit()
                flash(_('已更新代理授權'), 'success')
                return redirect(url_for('delegations.view_delegation', secure_code=secure_code))
            except Exception as e:
                db.session.rollback()
                flash(_('更新失敗: %(error)s', error=str(e)), 'error')

    return render_template(
        'pages/delegations/edit.html',
        delegation=delegation,
        users=users,
        delegation_types=delegation_types
    )


@delegations_bp.route('/<secure_code>/revoke', methods=['POST'])
def revoke_delegation(secure_code: str):
    """撤銷代理授權"""
    try:
        delegation = ResourceGateway.get(Delegation, secure_code)
    except Exception:
        abort(404)

    revoke_reason = request.form.get('revoke_reason', '').strip()

    try:
        delegation.status = DelegationStatus.REVOKED
        delegation.revoked_at = datetime.utcnow()
        delegation.revoked_by = current_user.display_name
        delegation.revoke_reason = revoke_reason
        db.session.commit()
        flash(_('已撤銷代理授權'), 'success')
        return redirect(url_for('delegations.view_delegation', secure_code=secure_code))
    except Exception as e:
        db.session.rollback()
        flash(_('撤銷失敗: %(error)s', error=str(e)), 'error')
        return redirect(url_for('delegations.edit_delegation', secure_code=secure_code))


@delegations_bp.route('/<secure_code>/delete', methods=['POST'])
def delete_delegation(secure_code: str):
    """刪除代理授權"""
    try:
        delegation = ResourceGateway.get(Delegation, secure_code)
    except Exception:
        abort(404)

    try:
        delegation.is_deleted = True
        delegation.deleted_at = datetime.utcnow()
        db.session.commit()
        flash(_('已刪除代理授權'), 'success')
        return redirect(url_for('delegations.list_delegations'))
    except Exception as e:
        db.session.rollback()
        flash(_('刪除失敗: %(error)s', error=str(e)), 'error')
        return redirect(url_for('delegations.edit_delegation', secure_code=secure_code))
