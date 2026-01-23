"""
BeakMask External User Management Web Routes
非公司成員帳號管理網頁路由

功能：
1. 管理外部人員帳號（廠商、訪客、合作夥伴）
2. 必須指定群組歸屬
3. 必須使用「外部專用」編號規則
4. Email 由用戶自行輸入（不自動加 domain）
"""
from datetime import datetime
from flask import Blueprint, render_template, abort, request, flash, redirect, url_for
from flask_login import current_user

from ..security.decorators import admin_required
from ..security.resource_gateway import ResourceGateway
from ..models.user import User, UserType
from ..models.organizational_unit import OrganizationalUnit
from ..models.user_numbering_rule import UserNumberingRule, NumberingUsageScope
from ..models.user_numbering_rule import UsedUserNumber
from ..models.user_unit_membership import UserUnitMembership, MembershipType, MembershipRole
from ..models.audit_log import AuditLog
from ..services.numbering_service import NumberingService
from .. import db

external_users_bp = Blueprint('external_users', __name__)


def _get_external_numbering_rules(org_secure_code: str):
    """取得外部專用的編號規則"""
    return UserNumberingRule.query.filter(
        UserNumberingRule.org_secure_code == org_secure_code,
        UserNumberingRule.usage_scope == NumberingUsageScope.EXTERNAL_ONLY,
        UserNumberingRule.is_active == True,
        UserNumberingRule.is_deleted == False
    ).order_by(
        UserNumberingRule.default_for.desc().nullslast(),
        UserNumberingRule.name
    ).all()


def _get_default_external_rule(org_secure_code: str):
    """取得外部人員預設編號規則"""
    return NumberingService.get_default_rule(org_secure_code, default_for='EXTERNAL')


def _get_groups(org_secure_code: str):
    """取得群組列表"""
    return OrganizationalUnit.query.filter(
        OrganizationalUnit.org_secure_code == org_secure_code,
        OrganizationalUnit.unit_type == 'GROUP',
        OrganizationalUnit.is_deleted == False
    ).order_by(OrganizationalUnit.name).all()


def _log_audit(action: str, target_user: User, details: str = None):
    """記錄稽核日誌"""
    try:
        log = AuditLog(
            org_secure_code=current_user.org_secure_code,
            user_secure_code=current_user.secure_code,
            action=action,
            resource_type='EXTERNAL_USER',
            resource_id=target_user.secure_code,
            details=details or f'{action}: {target_user.display_name} ({target_user.email})',
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string[:500] if request.user_agent else None
        )
        db.session.add(log)
    except Exception:
        # 稽核失敗不影響主流程
        pass


@external_users_bp.route('/external-users')
@admin_required
def list_external_users():
    """非公司成員列表"""
    users = User.query.filter(
        User.org_secure_code == current_user.org_secure_code,
        User.user_type == UserType.EXTERNAL,
        User.is_deleted == False
    ).order_by(User.created_at.desc()).all()

    # 查詢每個用戶的群組歸屬
    for user in users:
        memberships = UserUnitMembership.query.filter(
            UserUnitMembership.user_secure_code == user.secure_code,
            UserUnitMembership.membership_type == MembershipType.MEMBER,
            UserUnitMembership.is_deleted == False
        ).all()
        user.groups = [m.unit for m in memberships if m.unit and m.unit.unit_type == 'GROUP']

    return render_template(
        'pages/external-users/list.html',
        users=users
    )


@external_users_bp.route('/external-users/create', methods=['GET', 'POST'])
@admin_required
def create_external_user():
    """新增非公司成員"""
    org = current_user.organization
    if not org:
        flash('找不到所屬企業', 'error')
        return redirect(url_for('external_users.list_external_users'))

    # 檢查是否有外部專用預設編號規則
    default_rule = _get_default_external_rule(org.secure_code)
    if not default_rule:
        flash('尚未設定「外部人員」預設編號規則，請先到「用戶編號規則」頁面設定。', 'error')
        return redirect(url_for('numbering.list_rules'))

    groups = _get_groups(org.secure_code)

    form_data = {}

    if request.method == 'POST':
        form_data = {
            'display_name': request.form.get('display_name', '').strip(),
            'email': request.form.get('email', '').strip(),
            'group_code': request.form.get('group_code', '').strip(),
            'notes': request.form.get('notes', '').strip(),
        }

        display_name = form_data['display_name']
        email = form_data['email'].lower()
        password = request.form.get('password', '').strip()
        group_code = form_data['group_code']
        notes = form_data['notes']

        # 驗證必填欄位
        if not display_name or not email or not password:
            flash('姓名、Email、密碼為必填', 'error')
        elif '@' not in email:
            flash('請輸入有效的 Email 格式', 'error')
        elif len(password) < 8:
            flash('密碼至少需要 8 個字元', 'error')
        elif not group_code:
            flash('必須選擇歸屬群組', 'error')
        else:
            # 從 email 提取 username
            username = email.split('@')[0]

            # 檢查帳號是否已存在
            existing = User.query.filter_by(email=email, is_deleted=False).first()
            if existing:
                flash(f'Email {email} 已存在', 'error')
            else:
                # 處理編號：自動使用預設規則
                default_rule = _get_default_external_rule(org.secure_code)
                if not default_rule:
                    flash('找不到外部人員預設編號規則，請先設定', 'error')
                    return render_template(
                        'pages/external-users/create.html',
                        form_data=form_data,
                        default_rule=default_rule,
                        groups=groups
                    )

                try:
                    employee_id = NumberingService.get_next_number(default_rule, consume=True)
                except Exception as e:
                    flash(f'產生編號失敗: {str(e)}', 'error')
                    return render_template(
                        'pages/external-users/create.html',
                        form_data=form_data,
                        default_rule=default_rule,
                        groups=groups
                    )

                # 查找群組
                group = OrganizationalUnit.query.filter_by(
                    org_secure_code=org.secure_code,
                    code=group_code,
                    unit_type='GROUP',
                    is_deleted=False
                ).first()
                if not group:
                    flash(f'找不到群組 {group_code}', 'error')
                    return render_template(
                        'pages/external-users/create.html',
                        form_data=form_data,
                        numbering_rules=numbering_rules,
                        groups=groups
                    )

                try:
                    # 建立用戶
                    user = User(
                        username=username,
                        email=email,
                        display_name=display_name,
                        org_secure_code=org.secure_code,
                        user_type=UserType.EXTERNAL,
                        is_active=True,
                        employee_id=employee_id,
                        backup_email_1=email,
                        notes=notes if notes else None,
                    )
                    user.set_password(password)
                    db.session.add(user)
                    db.session.flush()

                    # 編號已在 NumberingService.get_next_number 中自動記錄

                    # 建立群組成員關係
                    membership = UserUnitMembership(
                        org_secure_code=org.secure_code,
                        user_secure_code=user.secure_code,
                        unit_secure_code=group.secure_code,
                        membership_type=MembershipType.MEMBER,
                        role_type=MembershipRole.MEMBER,
                        start_date=datetime.utcnow().date(),
                    )
                    db.session.add(membership)

                    # 稽核記錄
                    _log_audit('CREATE', user, f'新增外部人員: {display_name} ({email}), 編號: {employee_id}')

                    db.session.commit()

                    flash(f'已建立外部人員 {display_name}（編號：{employee_id}）', 'success')
                    return redirect(url_for('external_users.list_external_users'))

                except Exception as e:
                    db.session.rollback()
                    flash(f'建立失敗: {str(e)}', 'error')

    return render_template(
        'pages/external-users/create.html',
        form_data=form_data,
        default_rule=default_rule,
        groups=groups
    )


@external_users_bp.route('/external-users/<secure_code>')
@admin_required
def view_external_user(secure_code: str):
    """查看非公司成員詳情"""
    try:
        user = ResourceGateway.get(User, secure_code)
    except Exception:
        abort(404)

    if user.user_type != UserType.EXTERNAL:
        flash('此帳號不是外部人員', 'error')
        return redirect(url_for('external_users.list_external_users'))

    # 查詢群組歸屬
    memberships = UserUnitMembership.query.filter(
        UserUnitMembership.user_secure_code == user.secure_code,
        UserUnitMembership.membership_type == MembershipType.MEMBER,
        UserUnitMembership.is_deleted == False
    ).all()
    groups = [m.unit for m in memberships if m.unit and m.unit.unit_type == 'GROUP']

    return render_template(
        'pages/external-users/view.html',
        user=user,
        groups=groups
    )


@external_users_bp.route('/external-users/<secure_code>/edit', methods=['GET', 'POST'])
@admin_required
def edit_external_user(secure_code: str):
    """編輯外部人員"""
    org = current_user.organization
    if not org:
        flash('找不到所屬企業', 'error')
        return redirect(url_for('external_users.list_external_users'))

    try:
        user = ResourceGateway.get(User, secure_code)
    except Exception:
        abort(404)

    if user.user_type != UserType.EXTERNAL:
        flash('此帳號不是外部人員', 'error')
        return redirect(url_for('external_users.list_external_users'))

    # 查詢群組歸屬（含角色）
    memberships = UserUnitMembership.query.filter(
        UserUnitMembership.user_secure_code == user.secure_code,
        UserUnitMembership.membership_type == MembershipType.MEMBER,
        UserUnitMembership.is_deleted == False
    ).all()

    # 整理成員資訊（包含角色）
    current_groups = []
    for m in memberships:
        if m.unit and m.unit.unit_type == 'GROUP':
            current_groups.append({
                'unit': m.unit,
                'role_type': m.role_type,
                'role_name': _get_role_name(m.role_type),
                'membership_code': m.secure_code,
                'start_date': m.start_date
            })

    # 取得所有可用群組
    all_groups = _get_groups(org.secure_code)

    # 目前已加入的群組 code 列表
    joined_group_codes = [g['unit'].code for g in current_groups]

    if request.method == 'POST':
        new_email = request.form.get('email', '').strip().lower()
        new_notes = request.form.get('notes', '').strip()

        if not new_email:
            flash('Email 為必填', 'error')
        elif '@' not in new_email:
            flash('請輸入有效的 Email 格式', 'error')
        else:
            # 檢查 email 是否與其他帳號重複
            existing = User.query.filter(
                User.email == new_email,
                User.secure_code != secure_code,
                User.is_deleted == False
            ).first()
            if existing:
                flash(f'Email {new_email} 已被其他帳號使用', 'error')
            else:
                try:
                    old_email = user.email
                    old_notes = user.notes

                    user.email = new_email
                    user.username = new_email.split('@')[0]
                    user.backup_email_1 = new_email
                    user.notes = new_notes if new_notes else None

                    # 稽核記錄
                    changes = []
                    if old_email != new_email:
                        changes.append(f'Email: {old_email} → {new_email}')
                    if old_notes != user.notes:
                        changes.append('備註已更新')
                    _log_audit('UPDATE', user, f'編輯外部人員: {", ".join(changes)}')

                    db.session.commit()
                    flash(f'已更新外部人員 {user.display_name}', 'success')
                    return redirect(url_for('external_users.view_external_user', secure_code=secure_code))
                except Exception as e:
                    db.session.rollback()
                    flash(f'更新失敗: {str(e)}', 'error')

    return render_template(
        'pages/external-users/edit.html',
        user=user,
        current_groups=current_groups,
        all_groups=all_groups,
        joined_group_codes=joined_group_codes
    )


def _get_role_name(role_type: str) -> str:
    """取得角色顯示名稱"""
    role_names = {
        MembershipRole.MANAGER: '團長',
        MembershipRole.DEPUTY: '副團長',
        MembershipRole.PROXY1: '代理人一',
        MembershipRole.PROXY2: '代理人二',
        MembershipRole.MEMBER: '團員',
    }
    return role_names.get(role_type, '團員')


@external_users_bp.route('/external-users/<secure_code>/add-group', methods=['POST'])
@admin_required
def add_to_group(secure_code: str):
    """將外部人員加入群組"""
    try:
        user = ResourceGateway.get(User, secure_code)
    except Exception:
        abort(404)

    if user.user_type != UserType.EXTERNAL:
        flash('此帳號不是外部人員', 'error')
        return redirect(url_for('external_users.list_external_users'))

    group_code = request.form.get('group_code', '').strip()
    if not group_code:
        flash('請選擇群組', 'error')
        return redirect(url_for('external_users.edit_external_user', secure_code=secure_code))

    org = current_user.organization
    group = OrganizationalUnit.query.filter_by(
        org_secure_code=org.secure_code,
        code=group_code,
        unit_type='GROUP',
        is_deleted=False
    ).first()

    if not group:
        flash('找不到群組', 'error')
        return redirect(url_for('external_users.edit_external_user', secure_code=secure_code))

    # 檢查是否已加入
    existing = UserUnitMembership.query.filter_by(
        user_secure_code=user.secure_code,
        unit_secure_code=group.secure_code,
        membership_type=MembershipType.MEMBER,
        is_deleted=False
    ).first()

    if existing:
        flash(f'已是「{group.name}」的成員', 'error')
        return redirect(url_for('external_users.edit_external_user', secure_code=secure_code))

    try:
        membership = UserUnitMembership(
            org_secure_code=org.secure_code,
            user_secure_code=user.secure_code,
            unit_secure_code=group.secure_code,
            membership_type=MembershipType.MEMBER,
            role_type=MembershipRole.MEMBER,
            start_date=datetime.utcnow().date(),
        )
        db.session.add(membership)
        _log_audit('ADD_GROUP', user, f'加入群組: {group.name}')
        db.session.commit()
        flash(f'已加入群組「{group.name}」', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'操作失敗: {str(e)}', 'error')

    return redirect(url_for('external_users.edit_external_user', secure_code=secure_code))


@external_users_bp.route('/external-users/<secure_code>/remove-group', methods=['POST'])
@admin_required
def remove_from_group(secure_code: str):
    """將外部人員從群組移除"""
    try:
        user = ResourceGateway.get(User, secure_code)
    except Exception:
        abort(404)

    if user.user_type != UserType.EXTERNAL:
        flash('此帳號不是外部人員', 'error')
        return redirect(url_for('external_users.list_external_users'))

    membership_code = request.form.get('membership_code', '').strip()
    if not membership_code:
        flash('參數錯誤', 'error')
        return redirect(url_for('external_users.edit_external_user', secure_code=secure_code))

    membership = UserUnitMembership.query.filter_by(
        secure_code=membership_code,
        user_secure_code=user.secure_code,
        is_deleted=False
    ).first()

    if not membership:
        flash('找不到成員關係', 'error')
        return redirect(url_for('external_users.edit_external_user', secure_code=secure_code))

    # 檢查是否還有其他群組（外部人員必須至少屬於一個群組）
    other_memberships = UserUnitMembership.query.filter(
        UserUnitMembership.user_secure_code == user.secure_code,
        UserUnitMembership.membership_type == MembershipType.MEMBER,
        UserUnitMembership.secure_code != membership_code,
        UserUnitMembership.is_deleted == False
    ).count()

    if other_memberships == 0:
        flash('外部人員必須至少屬於一個群組', 'error')
        return redirect(url_for('external_users.edit_external_user', secure_code=secure_code))

    try:
        group_name = membership.unit.name if membership.unit else '未知'
        membership.is_deleted = True
        membership.deleted_at = datetime.utcnow()
        _log_audit('REMOVE_GROUP', user, f'移除群組: {group_name}')
        db.session.commit()
        flash(f'已從群組「{group_name}」移除', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'操作失敗: {str(e)}', 'error')

    return redirect(url_for('external_users.edit_external_user', secure_code=secure_code))


@external_users_bp.route('/external-users/<secure_code>/toggle-status', methods=['POST'])
@admin_required
def toggle_status(secure_code: str):
    """切換外部人員啟用狀態"""
    try:
        user = ResourceGateway.get(User, secure_code)
    except Exception:
        abort(404)

    if user.user_type != UserType.EXTERNAL:
        flash('此帳號不是外部人員', 'error')
        return redirect(url_for('external_users.list_external_users'))

    try:
        old_status = user.is_active
        user.is_active = not user.is_active
        status = '啟用' if user.is_active else '停用'

        # 稽核記錄
        _log_audit('TOGGLE_STATUS', user, f'狀態變更: {"啟用" if old_status else "停用"} → {status}')

        db.session.commit()
        flash(f'已{status}外部人員 {user.display_name}', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'操作失敗: {str(e)}', 'error')

    return redirect(url_for('external_users.list_external_users'))


@external_users_bp.route('/external-users/<secure_code>/delete', methods=['POST'])
@admin_required
def delete_external_user(secure_code: str):
    """刪除外部人員"""
    try:
        user = ResourceGateway.get(User, secure_code)
    except Exception:
        abort(404)

    if user.user_type != UserType.EXTERNAL:
        flash('此帳號不是外部人員', 'error')
        return redirect(url_for('external_users.list_external_users'))

    try:
        display_name = user.display_name
        email = user.email

        user.is_deleted = True
        user.deleted_at = datetime.utcnow()

        # 稽核記錄
        _log_audit('DELETE', user, f'刪除外部人員: {display_name} ({email})')

        db.session.commit()
        flash(f'已刪除外部人員 {display_name}', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'刪除失敗: {str(e)}', 'error')

    return redirect(url_for('external_users.list_external_users'))


@external_users_bp.route('/external-users/<secure_code>/change-password', methods=['POST'])
@admin_required
def change_password(secure_code: str):
    """管理員變更外部人員密碼（不需要舊密碼）"""
    try:
        user = ResourceGateway.get(User, secure_code)
    except Exception:
        abort(404)

    if user.user_type != UserType.EXTERNAL:
        flash('此帳號不是外部人員', 'error')
        return redirect(url_for('external_users.list_external_users'))

    new_password = request.form.get('new_password', '').strip()

    if not new_password:
        flash('請輸入新密碼', 'error')
        return redirect(url_for('external_users.edit_external_user', secure_code=secure_code))

    if len(new_password) < 8:
        flash('密碼至少需要 8 個字元', 'error')
        return redirect(url_for('external_users.edit_external_user', secure_code=secure_code))

    try:
        user.set_password(new_password)
        _log_audit('CHANGE_PASSWORD', user, f'管理員變更密碼')
        db.session.commit()
        flash(f'已變更 {user.display_name} 的密碼', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'密碼變更失敗: {str(e)}', 'error')

    return redirect(url_for('external_users.edit_external_user', secure_code=secure_code))
