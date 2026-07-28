"""
Portal Auth Service
公開子系統訪客認證服務

職責:
  - 訪客註冊 / 登入 / 登出
  - GUEST session 自動建立
  - 讀取 portal_settings (allow_anonymous, allow_registration)
  - 密碼 hash 使用 werkzeug.security

Session 結構 (flask session['portal_sessions'][sub_system_sc]):
  可讓多個公開子系統並存登入；舊版 portal_guest slot 不再讀取。

不使用 Flask-Login，與主系統 session 完全分離。
所有 portal.db 操作透過 DataSourceManager.get_session()。
"""
import logging
import re
import secrets
from datetime import datetime, timezone

from flask import session
from sqlalchemy import text
from werkzeug.security import generate_password_hash, check_password_hash

from .data_source_manager import DataSourceManager, ensure_portal_schema

logger = logging.getLogger(__name__)

_SESSION_KEY = 'portal_sessions'
_CODE_RE = re.compile(r'^[A-Z][A-Z0-9_]{0,31}$')


# ── Session 操作 ──────────────────────────────────────────────

def get_current_portal_user(sub_system_sc: str) -> dict | None:
    """
    取得當前 portal session

    Returns:
        session dict (sub_system_sc, user_id, user_type, group_code,
        level_code, level_rank, roles, display_name)，若無該子系統 session → None
    """
    portal_sessions = session.get(_SESSION_KEY) or {}
    data = portal_sessions.get(sub_system_sc)
    return data if isinstance(data, dict) else None


def _store_session(sub_system_sc: str, data: dict) -> dict:
    portal_sessions = dict(session.get(_SESSION_KEY) or {})
    portal_sessions[sub_system_sc] = data
    session[_SESSION_KEY] = portal_sessions
    session.modified = True
    return data


def _level_rank(sess, level_code: str | None) -> tuple[str, int]:
    if not level_code:
        return 'GUEST', 0
    row = sess.execute(
        text('SELECT rank FROM portal_levels WHERE code = :code AND is_active = 1'),
        {'code': level_code},
    ).first()
    if not row:
        return 'GUEST', 0
    return level_code, int(row[0])


def _valid_code(code: str) -> bool:
    return bool(_CODE_RE.fullmatch((code or '').strip()))


def create_guest_session(sub_system_sc: str) -> dict:
    """建立 GUEST (匿名) session，不寫入 portal.db"""
    ensure_portal_schema(sub_system_sc)
    data = {
        'sub_system_sc': sub_system_sc,
        'user_id': None,
        'user_type': 'GUEST',
        'group_code': None,
        'level_code': 'GUEST',
        'level_rank': 0,
        'roles': ['GUEST'],
        'display_name': '訪客',
        'guest_token': secrets.token_urlsafe(16),
    }
    return _store_session(sub_system_sc, data)


def ensure_guest_token(sub_system_sc: str, portal_user: dict) -> str:
    """Return or issue the anonymous visitor token stored only in Flask session."""
    if not isinstance(portal_user, dict):
        portal_user = {}
    token = portal_user.get('guest_token')
    if token:
        return token
    updated = dict(portal_user)
    updated['guest_token'] = secrets.token_urlsafe(16)
    _store_session(sub_system_sc, updated)
    portal_user.update(updated)
    return updated['guest_token']


def logout(sub_system_sc: str):
    """清除 portal session (僅清除與該子系統相符的 session)"""
    portal_sessions = dict(session.get(_SESSION_KEY) or {})
    if sub_system_sc in portal_sessions:
        portal_sessions.pop(sub_system_sc, None)
        if portal_sessions:
            session[_SESSION_KEY] = portal_sessions
        else:
            session.pop(_SESSION_KEY, None)
        session.modified = True


# ── 登入 ──────────────────────────────────────────────────────

def login(sub_system_sc: str, username: str, password: str) -> tuple[dict | None, str]:
    """
    Portal 用戶登入

    Args:
        sub_system_sc: 子系統 secure_code
        username: 帳號
        password: 明文密碼

    Returns:
        (session_data, '') on success
        (None, error_message) on failure
    """
    username = username.strip()
    if not username or not password:
        return None, '請輸入帳號和密碼'

    mgr = DataSourceManager()
    try:
        ensure_portal_schema(sub_system_sc)
        with mgr.get_session(sub_system_sc, 'portal') as sess:
            row = sess.execute(
                text(
                    'SELECT id, secure_code, username, display_name, '
                    'password_hash, role_code, group_code, level_code, is_active '
                    'FROM portal_users WHERE username = :u'
                ),
                {'u': username},
            ).mappings().first()
            level_code, level_rank = _level_rank(sess, row['level_code'] if row else None)
    except FileNotFoundError:
        logger.error('Portal DB not found for %s', sub_system_sc)
        return None, '系統尚未初始化'

    if not row:
        return None, '帳號或密碼錯誤'

    if not row['is_active']:
        return None, '帳號已停用'

    if not check_password_hash(row['password_hash'], password):
        return None, '帳號或密碼錯誤'

    data = {
        'sub_system_sc': sub_system_sc,
        'user_id': row['id'],
        'user_type': 'PUBLIC_USER',
        'group_code': row['group_code'],
        'level_code': level_code,
        'level_rank': level_rank,
        'roles': [row['role_code']],
        'display_name': row['display_name'] or row['username'],
    }
    _store_session(sub_system_sc, data)
    logger.info('Portal login: user=%s sub_system=%s', username, sub_system_sc)
    return data, ''


# ── 註冊 ──────────────────────────────────────────────────────

def register(
    sub_system_sc: str,
    username: str,
    password: str,
    display_name: str = '',
    email: str = '',
) -> tuple[dict | None, str]:
    """
    Portal 用戶註冊

    Args:
        sub_system_sc: 子系統 secure_code
        username: 帳號 (portal.db 內唯一)
        password: 明文密碼 (hash 後存入)
        display_name: 顯示名稱
        email: Email

    Returns:
        (session_data, '') on success
        (None, error_message) on failure
    """
    username = username.strip()
    display_name = display_name.strip() or username
    email = email.strip()

    if not username:
        return None, '請輸入帳號'
    if len(username) < 3:
        return None, '帳號至少 3 個字元'
    if not password:
        return None, '請輸入密碼'
    if len(password) < 6:
        return None, '密碼至少 6 個字元'

    sc = secrets.token_urlsafe(16)
    pw_hash = generate_password_hash(password)
    now_utc = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    mgr = DataSourceManager()
    try:
        ensure_portal_schema(sub_system_sc)
        with mgr.get_session(sub_system_sc, 'portal') as sess:
            # 檢查帳號重複
            existing = sess.execute(
                text('SELECT id FROM portal_users WHERE username = :u'),
                {'u': username},
            ).first()
            if existing:
                return None, '此帳號已被使用'

            sess.execute(
                text(
                    'INSERT INTO portal_users '
                    '(secure_code, username, display_name, email, password_hash, '
                    ' role_code, group_code, level_code, is_active, created_at, updated_at) '
                    'VALUES (:sc, :username, :display_name, :email, :pw_hash, '
                    " 'PUBLIC_USER', 'GENERAL', 'MEMBER', 1, :now, :now)"
                ),
                {
                    'sc': sc,
                    'username': username,
                    'display_name': display_name,
                    'email': email,
                    'pw_hash': pw_hash,
                    'now': now_utc,
                },
            )
            # 取得新建的 user id
            row = sess.execute(
                text('SELECT id FROM portal_users WHERE secure_code = :sc'),
                {'sc': sc},
            ).first()
            user_id = row[0] if row else None
            level_code, level_rank = _level_rank(sess, 'MEMBER')
    except FileNotFoundError:
        logger.error('Portal DB not found for %s', sub_system_sc)
        return None, '系統尚未初始化'

    data = {
        'sub_system_sc': sub_system_sc,
        'user_id': user_id,
        'user_type': 'PUBLIC_USER',
        'group_code': 'GENERAL',
        'level_code': level_code,
        'level_rank': level_rank,
        'roles': ['PUBLIC_USER'],
        'display_name': display_name,
    }
    _store_session(sub_system_sc, data)
    logger.info('Portal register: user=%s sub_system=%s', username, sub_system_sc)
    return data, ''


# ── 群組 / 階級維運 ──────────────────────────────────────────

def list_groups(sub_system_sc: str) -> list[dict]:
    ensure_portal_schema(sub_system_sc)
    mgr = DataSourceManager()
    with mgr.get_session(sub_system_sc, 'portal') as sess:
        rows = sess.execute(
            text(
                'SELECT code, name, display_order, is_active, created_at '
                'FROM portal_groups ORDER BY display_order ASC, code ASC'
            )
        ).mappings().all()
        return [dict(row) for row in rows]


def list_levels(sub_system_sc: str) -> list[dict]:
    ensure_portal_schema(sub_system_sc)
    mgr = DataSourceManager()
    with mgr.get_session(sub_system_sc, 'portal') as sess:
        rows = sess.execute(
            text(
                'SELECT code, name, rank, display_order, is_active, created_at '
                'FROM portal_levels ORDER BY rank ASC, display_order ASC, code ASC'
            )
        ).mappings().all()
        return [dict(row) for row in rows]


def list_users(sub_system_sc: str) -> list[dict]:
    ensure_portal_schema(sub_system_sc)
    mgr = DataSourceManager()
    with mgr.get_session(sub_system_sc, 'portal') as sess:
        rows = sess.execute(
            text(
                'SELECT secure_code, username, display_name, email, role_code, '
                'group_code, level_code, is_active, created_at '
                'FROM portal_users ORDER BY username ASC'
            )
        ).mappings().all()
        return [dict(row) for row in rows]


def upsert_group(
    sub_system_sc: str,
    code: str,
    name: str,
    display_order: int = 0,
) -> tuple[dict | None, str]:
    code = (code or '').strip()
    name = (name or '').strip()
    if not _valid_code(code):
        return None, '群組代碼格式不正確'
    if not name:
        return None, '請輸入群組名稱'

    ensure_portal_schema(sub_system_sc)
    mgr = DataSourceManager()
    with mgr.get_session(sub_system_sc, 'portal') as sess:
        existing = sess.execute(
            text('SELECT id FROM portal_groups WHERE code = :code'),
            {'code': code},
        ).first()
        if existing:
            sess.execute(
                text(
                    'UPDATE portal_groups '
                    'SET name = :name, display_order = :display_order, is_active = 1 '
                    'WHERE code = :code'
                ),
                {'code': code, 'name': name, 'display_order': int(display_order)},
            )
        else:
            sess.execute(
                text(
                    'INSERT INTO portal_groups (code, name, display_order, is_active) '
                    'VALUES (:code, :name, :display_order, 1)'
                ),
                {'code': code, 'name': name, 'display_order': int(display_order)},
            )
        row = sess.execute(
            text(
                'SELECT code, name, display_order, is_active, created_at '
                'FROM portal_groups WHERE code = :code'
            ),
            {'code': code},
        ).mappings().first()
        return dict(row), ''


def upsert_level(
    sub_system_sc: str,
    code: str,
    name: str,
    rank: int,
    display_order: int = 0,
) -> tuple[dict | None, str]:
    code = (code or '').strip()
    name = (name or '').strip()
    if not _valid_code(code):
        return None, '階級代碼格式不正確'
    if not name:
        return None, '請輸入階級名稱'

    ensure_portal_schema(sub_system_sc)
    mgr = DataSourceManager()
    with mgr.get_session(sub_system_sc, 'portal') as sess:
        existing = sess.execute(
            text('SELECT id FROM portal_levels WHERE code = :code'),
            {'code': code},
        ).first()
        if existing:
            sess.execute(
                text(
                    'UPDATE portal_levels '
                    'SET name = :name, rank = :rank, display_order = :display_order, is_active = 1 '
                    'WHERE code = :code'
                ),
                {'code': code, 'name': name, 'rank': int(rank), 'display_order': int(display_order)},
            )
        else:
            sess.execute(
                text(
                    'INSERT INTO portal_levels (code, name, rank, display_order, is_active) '
                    'VALUES (:code, :name, :rank, :display_order, 1)'
                ),
                {'code': code, 'name': name, 'rank': int(rank), 'display_order': int(display_order)},
            )
        row = sess.execute(
            text(
                'SELECT code, name, rank, display_order, is_active, created_at '
                'FROM portal_levels WHERE code = :code'
            ),
            {'code': code},
        ).mappings().first()
        return dict(row), ''


def set_user_assignment(
    sub_system_sc: str,
    user_secure_code: str,
    group_code: str,
    level_code: str,
) -> bool:
    group_code = (group_code or '').strip()
    level_code = (level_code or '').strip()
    if not _valid_code(group_code) or not _valid_code(level_code):
        return False

    ensure_portal_schema(sub_system_sc)
    mgr = DataSourceManager()
    with mgr.get_session(sub_system_sc, 'portal') as sess:
        group_exists = sess.execute(
            text('SELECT 1 FROM portal_groups WHERE code = :code AND is_active = 1'),
            {'code': group_code},
        ).first()
        level_exists = sess.execute(
            text('SELECT 1 FROM portal_levels WHERE code = :code AND is_active = 1'),
            {'code': level_code},
        ).first()
        if not group_exists or not level_exists:
            return False
        result = sess.execute(
            text(
                'UPDATE portal_users '
                'SET group_code = :group_code, level_code = :level_code, updated_at = :now '
                'WHERE secure_code = :user_secure_code'
            ),
            {
                'group_code': group_code,
                'level_code': level_code,
                'user_secure_code': user_secure_code,
                'now': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            },
        )
        return result.rowcount > 0


# ── Portal 設定讀取 ───────────────────────────────────────────

def get_portal_setting(sub_system_sc: str, key: str, default: str = '') -> str:
    """
    讀取 portal_settings 單一設定值

    常用 key:
      - allow_anonymous: 'true'/'false' (預設 'false')
      - allow_registration: 'true'/'false' (預設 'false')
    """
    mgr = DataSourceManager()
    try:
        with mgr.get_session(sub_system_sc, 'portal') as sess:
            row = sess.execute(
                text('SELECT value FROM portal_settings WHERE key = :k'),
                {'k': key},
            ).first()
            return row[0] if row else default
    except FileNotFoundError:
        return default


def is_anonymous_allowed(sub_system_sc: str) -> bool:
    """檢查子系統是否允許匿名訪問"""
    return get_portal_setting(sub_system_sc, 'allow_anonymous', 'false') == 'true'


def is_registration_allowed(sub_system_sc: str) -> bool:
    """檢查子系統是否允許公開註冊"""
    return get_portal_setting(sub_system_sc, 'allow_registration', 'false') == 'true'
