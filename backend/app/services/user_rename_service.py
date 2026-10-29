"""帳號改名服務。

所有員工帳號與外部廠商 Email 的改名都必須由此服務處理，確保帳號、通知
信箱、密碼重設憑證與稽核紀錄在同一筆交易內一致更新。
"""
from datetime import datetime

from flask import has_request_context, request
from flask_babel import gettext as _
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import AuditLog, PasswordResetToken, User, UserType
from app.security.client_ip import get_client_ip


def check_rename_allowed(target_user, actor):
    """檢查 actor 是否可替 target_user 改名。"""
    if target_user.is_original_admin:
        return False, _('原始管理員帳號不可變更')
    if target_user.user_type == UserType.SYSTEM_ADMIN:
        return False, _('系統管理員帳號不可變更')
    if target_user.is_service_account:
        return False, _('服務帳號不可變更')
    if actor and target_user.secure_code == actor.secure_code:
        return False, _('不可變更自己的帳號')
    return True, ''


def _error(message):
    return {'success': False, 'changed': False, 'message': message}


def _occupant_description(user):
    if user.is_deleted:
        status = _('已刪除')
    elif not user.is_active:
        status = _('停用')
    else:
        status = _('啟用')
    return _('%(name)s（%(status)s）', name=user.display_name, status=status)


def find_account_occupant(org_secure_code, username, email, exclude_secure_code=None):
    """同企業內佔用此帳號名或 Email 的帳號（含停用與已刪除，與 DB 唯一約束一致）。"""
    query = User.query.filter(
        User.org_secure_code == org_secure_code,
        or_(User.username == username, User.email == email),
    )
    if exclude_secure_code:
        query = query.filter(User.secure_code != exclude_secure_code)
    return query.first()


def occupied_message(occupant):
    """帳號被佔用時給管理員的訊息；佔用者已停用或刪除時提示先改名。"""
    if occupant.is_active and not occupant.is_deleted:
        return _('帳號已被使用：%(occupant)s', occupant=_occupant_description(occupant))
    return _(
        '帳號已被另一個帳號使用（含已停用或已刪除的帳號）：%(occupant)s；'
        '要把它給新人，請先將該帳號改名',
        occupant=_occupant_description(occupant),
    )


def rename_user(target_user, *, actor, new_username=None, new_email=None, reason=None):
    """變更帳號，但保留 secure_code 與所有既有關聯。

    本函式只 flush、不 commit。呼叫端必須依回傳結果 commit 或 rollback。
    """
    allowed, block_reason = check_rename_allowed(target_user, actor)
    if not allowed:
        return _error(block_reason)

    org = target_user.organization
    if not org:
        return _error(_('找不到帳號所屬企業'))

    old_username = target_user.username
    old_email = target_user.email

    if target_user.user_type == UserType.EXTERNAL:
        if new_username is not None:
            return _error(_('外部廠商帳號只能使用完整 Email 變更'))
        normalized_email = (new_email or '').strip().lower()
        if not normalized_email or '@' not in normalized_email:
            return _error(_('請輸入有效的 Email 格式'))
        normalized_username = normalized_email
    else:
        if new_email is not None:
            return _error(_('員工帳號只能使用新帳號名稱變更'))
        normalized_username = ''.join((new_username or '').split()).lower()
        if not normalized_username:
            return _error(_('新帳號不可為空'))
        if '@' in normalized_username:
            return _error(_('員工帳號不可包含 @'))
        if normalized_username in {'admin', 'enterprise'}:
            return _error(_('此帳號名稱為系統保留字'))
        if normalized_username.startswith('admin-') and target_user.user_type != UserType.ORG_ADMIN:
            return _error(_('只有企業管理員可使用 admin- 開頭的帳號'))
        normalized_email = f'{normalized_username}@{org.domain_name}'
        if len(normalized_email) > 255:
            return _error(_('帳號 Email 長度不可超過 255 個字元'))

    if old_username == normalized_username and old_email == normalized_email:
        return {
            'success': True,
            'changed': False,
            'message': _('帳號未變更'),
            'old_username': old_username,
            'new_username': normalized_username,
        }

    occupant = find_account_occupant(
        target_user.org_secure_code, normalized_username, normalized_email,
        exclude_secure_code=target_user.secure_code,
    )
    if occupant:
        return _error(occupied_message(occupant))

    now = datetime.utcnow()
    account_before = old_email if target_user.user_type == UserType.EXTERNAL else old_username
    account_after = normalized_email if target_user.user_type == UserType.EXTERNAL else normalized_username

    try:
        target_user.username = normalized_username
        target_user.email = normalized_email
        if (
            target_user.backup_email_1
            and target_user.backup_email_1.lower() == old_email.lower()
        ):
            target_user.backup_email_1 = normalized_email
        if org.get_setting('display_name_field', 'native_name') == 'username':
            target_user.display_name = normalized_username

        PasswordResetToken.query.filter(
            PasswordResetToken.org_secure_code == target_user.org_secure_code,
            func.lower(PasswordResetToken.email) == old_email.lower(),
            PasswordResetToken.used_at.is_(None),
        ).update(
            {'expires_at': now, 'used_at': now},
            synchronize_session=False,
        )

        details = f'帳號改名: {account_before} -> {account_after}'
        cleaned_reason = (reason or '').strip()
        if cleaned_reason:
            details += f'; 原因: {cleaned_reason}'

        user_agent = None
        if has_request_context() and request.user_agent:
            user_agent = request.user_agent.string[:500]
        db.session.add(AuditLog(
            org_secure_code=target_user.org_secure_code,
            user_secure_code=actor.secure_code,
            action='RENAME',
            resource_type=(
                'EXTERNAL_USER'
                if target_user.user_type == UserType.EXTERNAL else 'USER'
            ),
            resource_id=target_user.secure_code,
            details=details,
            ip_address=get_client_ip() if has_request_context() else None,
            user_agent=user_agent,
        ))
        db.session.flush()
    except IntegrityError:
        return _error(_(
            '新帳號已被另一個帳號使用（含已停用或已刪除的帳號）；'
            '要把它給新人，請先將該帳號改名'
        ))

    return {
        'success': True,
        'changed': True,
        'message': _('帳號已變更'),
        'old_username': old_username,
        'new_username': normalized_username,
        'old_email': old_email,
        'new_email': normalized_email,
    }
