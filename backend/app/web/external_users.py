"""
BeakMask External User Management Web Routes
外部廠商帳號管理網頁路由

功能：
1. 管理外部廠商帳號（廠商、訪客、合作夥伴）
2. 必須指定群組歸屬
3. 必須使用「外部專用」編號規則
4. Email 由用戶自行輸入（不自動加 domain）
"""
from datetime import datetime
from flask import Blueprint, render_template, abort, request, flash, redirect, url_for
from flask_babel import gettext as _
from flask_login import current_user

from ..security.resource_gateway import ResourceGateway
from ..models.user import User, UserType
from ..models.organizational_unit import OrganizationalUnit
from ..models.user_numbering_rule import UserNumberingRule, NumberingUsageScope
from ..models.user_numbering_rule import UsedUserNumber
from ..models.user_unit_membership import UserUnitMembership, MembershipType, MembershipRole
from ..models.audit_log import AuditLog
from ..services.numbering_service import NumberingService
from ..services.password_policy_service import PasswordPolicyService
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
    """取得外部廠商預設編號規則"""
    return NumberingService.get_default_rule(org_secure_code, default_for='EXTERNAL')


def _get_groups(org_secure_code: str):
    """取得外部廠商社群 Tree 底下的群組列表（含 EXTERNAL_VENDORS 本身）"""
    ext_root = OrganizationalUnit.query.filter(
        OrganizationalUnit.org_secure_code == org_secure_code,
        OrganizationalUnit.code == 'EXTERNAL_VENDORS',
        OrganizationalUnit.unit_type == 'GROUP',
        OrganizationalUnit.is_deleted == False
    ).first()
    if not ext_root:
        return []
    return [ext_root] + [
        u for u in ext_root.get_descendants()
        if u.unit_type == 'GROUP'
    ]


def _assign_external_role(user, org):
    """自動指派 EXTERNAL_USERS 角色（鑰匙2: 外部廠商角色對齊）"""
    from ..models.role import Role
    from ..models.associations import UserRoleAssignment

    role = Role.query.filter(
        Role.org_secure_code == org.secure_code,
        Role.code == 'EXTERNAL_USERS',
        Role.is_deleted == False,
        Role.is_active == True,
    ).first()
    if not role:
        return

    assignment = UserRoleAssignment(
        org_secure_code=org.secure_code,
        user_secure_code=user.secure_code,
        role_secure_code=role.secure_code,
        assigned_by=current_user.secure_code if current_user and current_user.is_authenticated else None,
    )
    db.session.add(assignment)


def _revoke_memberships_and_roles(user):
    """停用/刪除時，退出所有社群並解除非 EXTERNAL_USERS 角色"""
    from ..models.role import Role
    from ..models.associations import UserRoleAssignment

    now = datetime.utcnow()

    # 1. 軟刪除所有社群成員關係
    memberships = UserUnitMembership.query.filter(
        UserUnitMembership.user_secure_code == user.secure_code,
        UserUnitMembership.org_secure_code == user.org_secure_code,
        UserUnitMembership.is_deleted == False
    ).all()

    revoked_groups = []
    for m in memberships:
        m.is_deleted = True
        m.deleted_at = now
        revoked_groups.append(m.unit_secure_code)

    # 2. 找出 EXTERNAL_USERS 角色 secure_code
    external_role = Role.query.filter(
        Role.org_secure_code == user.org_secure_code,
        Role.code == 'EXTERNAL_USERS',
        Role.is_deleted == False,
    ).first()
    external_role_code = external_role.secure_code if external_role else None

    # 3. 軟刪除非 EXTERNAL_USERS 的角色指派
    role_query = UserRoleAssignment.query.filter(
        UserRoleAssignment.user_secure_code == user.secure_code,
        UserRoleAssignment.org_secure_code == user.org_secure_code,
        UserRoleAssignment.is_deleted == False
    )
    if external_role_code:
        role_query = role_query.filter(
            UserRoleAssignment.role_secure_code != external_role_code
        )
    revoked_roles = role_query.all()
    for ra in revoked_roles:
        ra.is_deleted = True
        ra.deleted_at = now

    return len(revoked_groups), len(revoked_roles)


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
def list_external_users():
    """外部廠商列表"""
    users = User.query.filter(
        User.org_secure_code == current_user.org_secure_code,
        User.user_type == UserType.EXTERNAL,
        User.is_service_account == False,
        User.is_deleted == False,
        User.is_active == True
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
def create_external_user():
    """新增外部廠商"""
    org = current_user.organization
    if not org:
        flash(_('找不到所屬企業'), 'error')
        return redirect(url_for('external_users.list_external_users'))

    # 檢查是否有外部專用預設編號規則
    default_rule = _get_default_external_rule(org.secure_code)
    if not default_rule:
        flash(_('尚未設定「外部廠商」預設編號規則，請先到「用戶編號規則」頁面設定。'), 'error')
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

        # 密碼政策驗證
        pw_valid, pw_errors = (True, [])
        if password:
            pw_valid, pw_errors = PasswordPolicyService.validate_password(
                password, org.secure_code)

        # 驗證必填欄位
        if not display_name or not email or not password:
            flash(_('姓名、Email、密碼為必填'), 'error')
        elif '@' not in email:
            flash(_('請輸入有效的 Email 格式'), 'error')
        elif not pw_valid:
            for err in pw_errors:
                flash(err, 'error')
        elif not group_code:
            flash(_('必須選擇歸屬群組'), 'error')
        else:
            # 外部廠商的身分識別是完整 Email：同企業內 gg@a.com 與 gg@b.com 是兩個人，
            # username 直接等於 Email（2026-09-02 起，之前取 @ 前段會互撞）
            username = email

            # 檢查同企業內 email 是否已存在
            existing = User.query.filter_by(
                email=email,
                org_secure_code=org.secure_code,
                is_deleted=False
            ).first()
            if existing:
                flash(_('Email %(email)s 已存在', email=email), 'error')
            else:
                # 查找群組
                group = OrganizationalUnit.query.filter_by(
                    org_secure_code=org.secure_code,
                    code=group_code,
                    unit_type='GROUP',
                    is_deleted=False
                ).first()
                if not group:
                    flash(_('找不到群組 %(code)s', code=group_code), 'error')
                    return render_template(
                        'pages/external-users/create.html',
                        form_data=form_data,
                        default_rule=default_rule,
                        groups=groups
                    )

                if not org.can_create_user(UserType.EXTERNAL):
                    flash(_('已達帳號上限（%(limit)s），目前已使用 %(used)s 個',
                            limit=org.user_limit, used=org.get_active_user_count()), 'error')
                    return render_template(
                        'pages/external-users/create.html',
                        form_data=form_data,
                        default_rule=default_rule,
                        groups=groups
                    )

                # 處理編號：自動使用預設規則
                default_rule = _get_default_external_rule(org.secure_code)
                if not default_rule:
                    flash(_('找不到外部廠商預設編號規則，請先設定'), 'error')
                    return render_template(
                        'pages/external-users/create.html',
                        form_data=form_data,
                        default_rule=default_rule,
                        groups=groups
                    )

                try:
                    employee_id = NumberingService.get_next_number(default_rule, consume=True)
                except Exception as e:
                    flash(_('產生編號失敗: %(error)s', error=str(e)), 'error')
                    return render_template(
                        'pages/external-users/create.html',
                        form_data=form_data,
                        default_rule=default_rule,
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

                    # 自動指派 EXTERNAL_USERS 角色 (鑰匙2)
                    _assign_external_role(user, org)

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
                    _log_audit('CREATE', user, f'新增外部廠商: {display_name} ({email}), 編號: {employee_id}')

                    db.session.commit()

                    flash(_('已建立外部廠商 %(name)s（編號：%(employee_id)s）', name=display_name, employee_id=employee_id), 'success')
                    return redirect(url_for('external_users.list_external_users'))

                except Exception as e:
                    db.session.rollback()
                    flash(_('建立失敗: %(error)s', error=str(e)), 'error')

    return render_template(
        'pages/external-users/create.html',
        form_data=form_data,
        default_rule=default_rule,
        groups=groups
    )


@external_users_bp.route('/external-users/<secure_code>')
def view_external_user(secure_code: str):
    """查看外部廠商詳情"""
    try:
        user = ResourceGateway.get(User, secure_code)
    except Exception:
        abort(404)

    if user.user_type != UserType.EXTERNAL:
        flash(_('此帳號不是外部廠商'), 'error')
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
def edit_external_user(secure_code: str):
    """編輯外部廠商"""
    org = current_user.organization
    if not org:
        flash(_('找不到所屬企業'), 'error')
        return redirect(url_for('external_users.list_external_users'))

    try:
        user = ResourceGateway.get(User, secure_code)
    except Exception:
        abort(404)

    if user.user_type != UserType.EXTERNAL:
        flash(_('此帳號不是外部廠商'), 'error')
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
            flash(_('Email 為必填'), 'error')
        elif '@' not in new_email:
            flash(_('請輸入有效的 Email 格式'), 'error')
        else:
            # 檢查同企業內 email 是否與其他帳號重複
            existing = User.query.filter(
                User.email == new_email,
                User.org_secure_code == org.secure_code,
                User.secure_code != secure_code,
                User.is_deleted == False
            ).first()
            if existing:
                flash(_('Email %(email)s 已被其他帳號使用', email=new_email), 'error')
            else:
                try:
                    old_email = user.email
                    old_notes = user.notes

                    user.email = new_email
                    user.username = new_email
                    user.backup_email_1 = new_email
                    user.notes = new_notes if new_notes else None

                    # 稽核記錄
                    changes = []
                    if old_email != new_email:
                        changes.append(f'Email: {old_email} → {new_email}')
                    if old_notes != user.notes:
                        changes.append('備註已更新')
                    _log_audit('UPDATE', user, f'編輯外部廠商: {", ".join(changes)}')

                    db.session.commit()
                    flash(_('已更新外部廠商 %(name)s', name=user.display_name), 'success')
                    return redirect(url_for('external_users.list_external_users'))
                except Exception as e:
                    db.session.rollback()
                    flash(_('更新失敗: %(error)s', error=str(e)), 'error')

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
def add_to_group(secure_code: str):
    """將外部廠商加入群組"""
    try:
        user = ResourceGateway.get(User, secure_code)
    except Exception:
        abort(404)

    if user.user_type != UserType.EXTERNAL:
        flash(_('此帳號不是外部廠商'), 'error')
        return redirect(url_for('external_users.list_external_users'))

    group_code = request.form.get('group_code', '').strip()
    if not group_code:
        flash(_('請選擇群組'), 'error')
        return redirect(url_for('external_users.edit_external_user', secure_code=secure_code))

    org = current_user.organization
    group = OrganizationalUnit.query.filter_by(
        org_secure_code=org.secure_code,
        code=group_code,
        unit_type='GROUP',
        is_deleted=False
    ).first()

    if not group:
        flash(_('找不到群組'), 'error')
        return redirect(url_for('external_users.edit_external_user', secure_code=secure_code))

    # 檢查是否已加入
    existing = UserUnitMembership.query.filter_by(
        user_secure_code=user.secure_code,
        unit_secure_code=group.secure_code,
        membership_type=MembershipType.MEMBER,
        is_deleted=False
    ).first()

    if existing:
        flash(_('已是「%(name)s」的成員', name=group.name), 'error')
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
        flash(_('已加入群組「%(name)s」', name=group.name), 'success')
    except Exception as e:
        db.session.rollback()
        flash(_('操作失敗: %(error)s', error=str(e)), 'error')

    return redirect(url_for('external_users.edit_external_user', secure_code=secure_code))


@external_users_bp.route('/external-users/<secure_code>/remove-group', methods=['POST'])
def remove_from_group(secure_code: str):
    """將外部廠商從群組移除"""
    try:
        user = ResourceGateway.get(User, secure_code)
    except Exception:
        abort(404)

    if user.user_type != UserType.EXTERNAL:
        flash(_('此帳號不是外部廠商'), 'error')
        return redirect(url_for('external_users.list_external_users'))

    membership_code = request.form.get('membership_code', '').strip()
    if not membership_code:
        flash(_('參數錯誤'), 'error')
        return redirect(url_for('external_users.edit_external_user', secure_code=secure_code))

    membership = UserUnitMembership.query.filter_by(
        secure_code=membership_code,
        user_secure_code=user.secure_code,
        is_deleted=False
    ).first()

    if not membership:
        flash(_('找不到成員關係'), 'error')
        return redirect(url_for('external_users.edit_external_user', secure_code=secure_code))

    # 檢查是否還有其他群組（外部廠商必須至少屬於一個群組）
    other_memberships = UserUnitMembership.query.filter(
        UserUnitMembership.user_secure_code == user.secure_code,
        UserUnitMembership.membership_type == MembershipType.MEMBER,
        UserUnitMembership.secure_code != membership_code,
        UserUnitMembership.is_deleted == False
    ).count()

    if other_memberships == 0:
        flash(_('外部廠商必須至少屬於一個群組'), 'error')
        return redirect(url_for('external_users.edit_external_user', secure_code=secure_code))

    try:
        group_name = membership.unit.name if membership.unit else '未知'
        membership.is_deleted = True
        membership.deleted_at = datetime.utcnow()
        _log_audit('REMOVE_GROUP', user, f'移除群組: {group_name}')
        db.session.commit()
        flash(_('已從群組「%(name)s」移除', name=group_name), 'success')
    except Exception as e:
        db.session.rollback()
        flash(_('操作失敗: %(error)s', error=str(e)), 'error')

    return redirect(url_for('external_users.edit_external_user', secure_code=secure_code))


@external_users_bp.route('/external-users/<secure_code>/toggle-status', methods=['POST'])
def toggle_status(secure_code: str):
    """切換外部廠商啟用狀態"""
    try:
        user = ResourceGateway.get(User, secure_code)
    except Exception:
        abort(404)

    if user.user_type != UserType.EXTERNAL:
        flash(_('此帳號不是外部廠商'), 'error')
        return redirect(url_for('external_users.list_external_users'))

    # 帳號上限：重新啟用會增加使用中人數
    if not user.is_active:
        limit_org = user.organization
        if limit_org and not limit_org.can_create_user(user.user_type):
            flash(_('已達帳號上限（%(limit)s），目前已使用 %(used)s 個',
                    limit=limit_org.user_limit, used=limit_org.get_active_user_count()), 'error')
            return redirect(url_for('external_users.list_external_users'))

    try:
        old_status = user.is_active
        user.is_active = not user.is_active
        status = '啟用' if user.is_active else '停用'

        # 停用時：退出所有社群 + 解除非 EXTERNAL_USERS 角色
        revoke_detail = ''
        if not user.is_active:
            g_count, r_count = _revoke_memberships_and_roles(user)
            if g_count or r_count:
                revoke_detail = f'（自動退出 {g_count} 個社群、解除 {r_count} 個角色）'

        # 稽核記錄
        _log_audit('TOGGLE_STATUS', user,
                   f'狀態變更: {"啟用" if old_status else "停用"} → {status}{revoke_detail}')

        db.session.commit()
        status_label = _('啟用') if user.is_active else _('停用')
        revoke_detail_label = ''
        if revoke_detail:
            revoke_detail_label = _('（自動退出 %(g_count)s 個社群、解除 %(r_count)s 個角色）', g_count=g_count, r_count=r_count)
        flash(_('已%(status)s外部廠商 %(name)s%(detail)s', status=status_label, name=user.display_name, detail=revoke_detail_label), 'success')
    except Exception as e:
        db.session.rollback()
        flash(_('操作失敗: %(error)s', error=str(e)), 'error')

    return redirect(url_for('external_users.list_external_users'))


@external_users_bp.route('/external-users/<secure_code>/delete', methods=['POST'])
def delete_external_user(secure_code: str):
    """刪除外部廠商"""
    try:
        user = ResourceGateway.get(User, secure_code)
    except Exception:
        abort(404)

    if user.user_type != UserType.EXTERNAL:
        flash(_('此帳號不是外部廠商'), 'error')
        return redirect(url_for('external_users.list_external_users'))

    try:
        display_name = user.display_name
        email = user.email

        # 退出所有社群 + 解除非 EXTERNAL_USERS 角色
        g_count, r_count = _revoke_memberships_and_roles(user)

        user.is_deleted = True
        user.deleted_at = datetime.utcnow()

        # 稽核記錄
        revoke_detail = ''
        if g_count or r_count:
            revoke_detail = f'（自動退出 {g_count} 個社群、解除 {r_count} 個角色）'
        _log_audit('DELETE', user,
                   f'刪除外部廠商: {display_name} ({email}){revoke_detail}')

        db.session.commit()
        flash(_('已刪除外部廠商 %(name)s', name=display_name), 'success')
    except Exception as e:
        db.session.rollback()
        flash(_('刪除失敗: %(error)s', error=str(e)), 'error')

    return redirect(url_for('external_users.list_external_users'))


@external_users_bp.route('/external-users/<secure_code>/change-password', methods=['POST'])
def change_password(secure_code: str):
    """管理員變更外部廠商密碼（不需要舊密碼）"""
    try:
        user = ResourceGateway.get(User, secure_code)
    except Exception:
        abort(404)

    if user.user_type != UserType.EXTERNAL:
        flash(_('此帳號不是外部廠商'), 'error')
        return redirect(url_for('external_users.list_external_users'))

    new_password = request.form.get('new_password', '').strip()

    if not new_password:
        flash(_('請輸入新密碼'), 'error')
        return redirect(url_for('external_users.edit_external_user', secure_code=secure_code))

    pw_valid, pw_errors = PasswordPolicyService.validate_password(
        new_password, user.org_secure_code,
        user_secure_code=user.secure_code)
    if not pw_valid:
        for err in pw_errors:
            flash(err, 'error')
        return redirect(url_for('external_users.edit_external_user', secure_code=secure_code))

    try:
        user.set_password(new_password)
        _log_audit('CHANGE_PASSWORD', user, f'管理員變更密碼')
        db.session.commit()
        flash(_('已變更 %(name)s 的密碼', name=user.display_name), 'success')
    except Exception as e:
        db.session.rollback()
        flash(_('密碼變更失敗: %(error)s', error=str(e)), 'error')

    return redirect(url_for('external_users.edit_external_user', secure_code=secure_code))
