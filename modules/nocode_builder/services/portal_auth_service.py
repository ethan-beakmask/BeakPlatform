"""
Portal Auth Service
公開子系統訪客認證服務

職責:
  - 訪客註冊 / 登入 / 登出
  - GUEST session 自動建立
  - 讀取 portal_settings (allow_anonymous, allow_registration)
  - 密碼 hash 使用 werkzeug.security

Session 結構 (flask session['portal_guest']):
  {
      'sub_system_sc': str,
      'user_id': int | None,
      'user_type': 'GUEST' | 'PUBLIC_USER',
      'roles': [str],
      'display_name': str,
  }

不使用 Flask-Login，與主系統 session 完全分離。
所有 portal.db 操作透過 DataSourceManager.get_session()。
"""
import logging
import secrets
from datetime import datetime, timezone

from flask import session
from sqlalchemy import text
from werkzeug.security import generate_password_hash, check_password_hash

from .data_source_manager import DataSourceManager

logger = logging.getLogger(__name__)

_SESSION_KEY = 'portal_guest'


# ── Session 操作 ──────────────────────────────────────────────

def get_current_portal_user(sub_system_sc: str) -> dict | None:
    """
    取得當前 portal session

    Returns:
        session dict (sub_system_sc, user_id, user_type, roles, display_name)
        若無 session 或 sub_system_sc 不符 → None
    """
    data = session.get(_SESSION_KEY)
    if not data or data.get('sub_system_sc') != sub_system_sc:
        return None
    return data


def create_guest_session(sub_system_sc: str) -> dict:
    """建立 GUEST (匿名) session，不寫入 portal.db"""
    data = {
        'sub_system_sc': sub_system_sc,
        'user_id': None,
        'user_type': 'GUEST',
        'roles': ['GUEST'],
        'display_name': '訪客',
    }
    session[_SESSION_KEY] = data
    return data


def logout(sub_system_sc: str):
    """清除 portal session (僅清除與該子系統相符的 session)"""
    data = session.get(_SESSION_KEY)
    if data and data.get('sub_system_sc') == sub_system_sc:
        session.pop(_SESSION_KEY, None)


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
        with mgr.get_session(sub_system_sc, 'portal') as sess:
            row = sess.execute(
                text(
                    'SELECT id, secure_code, username, display_name, '
                    'password_hash, role_code, is_active '
                    'FROM portal_users WHERE username = :u'
                ),
                {'u': username},
            ).mappings().first()
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
        'roles': [row['role_code']],
        'display_name': row['display_name'] or row['username'],
    }
    session[_SESSION_KEY] = data
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
                    ' role_code, is_active, created_at, updated_at) '
                    'VALUES (:sc, :username, :display_name, :email, :pw_hash, '
                    " 'PUBLIC_USER', 1, :now, :now)"
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
    except FileNotFoundError:
        logger.error('Portal DB not found for %s', sub_system_sc)
        return None, '系統尚未初始化'

    data = {
        'sub_system_sc': sub_system_sc,
        'user_id': user_id,
        'user_type': 'PUBLIC_USER',
        'roles': ['PUBLIC_USER'],
        'display_name': display_name,
    }
    session[_SESSION_KEY] = data
    logger.info('Portal register: user=%s sub_system=%s', username, sub_system_sc)
    return data, ''


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
