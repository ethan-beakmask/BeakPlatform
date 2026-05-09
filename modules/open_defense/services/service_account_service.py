"""
OpenDefense Module - Service Account Service

外部執行端的登入機制:
  - 建立 SA(產生 sa_id + 32-byte secret;secret 一次性顯示後 bcrypt 雜湊存 DB)
  - 登入(secret 比對 + 失敗鎖帳)
  - 簽 / 解 JWT(HS256, 預設 15 分鐘)

JWT 簽章 secret 從環境變數 OD_SA_JWT_SECRET 取得,
**禁止**與 ENCRYPTION_MASTER_KEY 共用(不同信任域)。
"""
import logging
import os
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict, Any

import bcrypt
import jwt as pyjwt

from app import db
from app.utils.security import generate_secure_code

from ..models import OdServiceAccount

logger = logging.getLogger(__name__)

SA_ID_PREFIX = 'sa_'
SECRET_BYTES = 32

JWT_ALGORITHM = 'HS256'
JWT_DEFAULT_TTL_SEC = 900  # 15 分鐘

MAX_FAILED_LOGINS = 5
LOCK_DURATION_SEC = 900  # 15 分鐘


class ServiceAccountError(Exception):
    """Service Account 業務錯誤"""
    def __init__(self, message: str, code: str = 'sa_error'):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------

def _get_jwt_secret() -> bytes:
    """
    從環境變數取 JWT 簽章 secret(base64url 32-byte)。
    若未設定,直接拋例外 -- 安全敏感設定不允許 fallback 到固定值。
    """
    raw = os.getenv('OD_SA_JWT_SECRET')
    if not raw:
        raise RuntimeError(
            '未設定 OD_SA_JWT_SECRET 環境變數。產生方式: '
            'python3 -c "import secrets,base64; '
            'print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"'
        )
    import base64
    try:
        secret = base64.urlsafe_b64decode(raw)
    except Exception as exc:
        raise RuntimeError(
            f'OD_SA_JWT_SECRET 格式錯誤,必須為 base64url 編碼: {exc}'
        )
    if len(secret) < 32:
        raise RuntimeError(
            f'OD_SA_JWT_SECRET 長度過短({len(secret)} < 32 bytes)'
        )
    return secret


def _get_jwt_ttl_sec() -> int:
    raw = os.getenv('OD_SA_JWT_TTL_SEC')
    if not raw:
        return JWT_DEFAULT_TTL_SEC
    try:
        v = int(raw)
        if v <= 0 or v > 86400:
            return JWT_DEFAULT_TTL_SEC
        return v
    except ValueError:
        return JWT_DEFAULT_TTL_SEC


# ---------------------------------------------------------------------------
# Account CRUD
# ---------------------------------------------------------------------------

def _generate_sa_id(name_hint: str = '') -> str:
    """sa_<name_hint_slug>_<rand6>,如 sa_crowdsec_a1b2c3"""
    slug = ''.join(c for c in name_hint.lower() if c.isalnum() or c == '_')[:20]
    rand = secrets.token_hex(3)
    return f'{SA_ID_PREFIX}{slug}_{rand}' if slug else f'{SA_ID_PREFIX}{rand}'


def create_service_account(
    *,
    org_secure_code: str,
    name: str,
    allowed_enforcement_points: List[str],
    created_by_secure_code: Optional[str] = None,
    sa_id_hint: str = '',
) -> Tuple[OdServiceAccount, str]:
    """
    建立 service account。

    Returns:
        (record, plaintext_secret_b64)  -- plaintext 只在建立時顯示一次
    """
    if not org_secure_code:
        raise ServiceAccountError('org_secure_code 必填', code='invalid_org')
    if not name or not name.strip():
        raise ServiceAccountError('name 必填', code='invalid_name')
    if not isinstance(allowed_enforcement_points, list):
        raise ServiceAccountError(
            'allowed_enforcement_points 必須為 list', code='invalid_eps')

    secret_bytes = secrets.token_bytes(SECRET_BYTES)
    secret_hash = bcrypt.hashpw(secret_bytes, bcrypt.gensalt()).decode('ascii')

    record = OdServiceAccount(
        secure_code=generate_secure_code(),
        org_secure_code=org_secure_code,
        sa_id=_generate_sa_id(sa_id_hint or name),
        name=name.strip(),
        secret_hash=secret_hash,
        allowed_enforcement_points=allowed_enforcement_points,
        is_active=True,
        failed_login_count=0,
        created_by_secure_code=created_by_secure_code,
    )
    db.session.add(record)
    db.session.commit()

    import base64
    plaintext_b64 = base64.urlsafe_b64encode(secret_bytes).decode('ascii')

    logger.info(
        'OpenDefense SA created sc=%s sa_id=%s org=%s',
        record.secure_code, record.sa_id, org_secure_code,
    )
    return record, plaintext_b64


def lookup_active_sa(sa_id: str) -> Optional[OdServiceAccount]:
    if not sa_id:
        return None
    return OdServiceAccount.query.filter_by(
        sa_id=sa_id,
        is_active=True,
        is_deleted=False,
    ).first()


# ---------------------------------------------------------------------------
# 登入
# ---------------------------------------------------------------------------

def _is_locked(record: OdServiceAccount, now: datetime) -> bool:
    return record.lock_until is not None and record.lock_until > now


def _record_failed_login(record: OdServiceAccount) -> None:
    record.failed_login_count = (record.failed_login_count or 0) + 1
    if record.failed_login_count >= MAX_FAILED_LOGINS:
        record.lock_until = datetime.utcnow() + timedelta(seconds=LOCK_DURATION_SEC)
        logger.warning(
            'OpenDefense SA locked sa_id=%s until=%s',
            record.sa_id, record.lock_until.isoformat(),
        )
    db.session.commit()


def _record_success_login(record: OdServiceAccount,
                          source_ip: Optional[str]) -> None:
    record.failed_login_count = 0
    record.lock_until = None
    record.last_login_at = datetime.utcnow()
    record.last_login_ip = source_ip
    db.session.commit()


def authenticate(sa_id: str, secret_b64: str,
                 source_ip: Optional[str] = None
                 ) -> Tuple[OdServiceAccount, str]:
    """
    驗 secret 並回傳 (record, jwt_token)。

    Raises:
        ServiceAccountError(code='locked'):帳號鎖定中
        ServiceAccountError(code='invalid_credentials'):帳號或密碼錯
    """
    import base64
    record = lookup_active_sa(sa_id)
    now = datetime.utcnow()

    if record is None:
        # 為避免 timing 洩漏 sa_id 是否存在,做一次假 bcrypt 計算
        bcrypt.checkpw(b'_dummy_secret_padding_', bcrypt.hashpw(
            b'_dummy', bcrypt.gensalt()))
        raise ServiceAccountError('sa_id 或 secret 錯誤',
                                  code='invalid_credentials')

    if _is_locked(record, now):
        raise ServiceAccountError(
            f'帳號鎖定中,解鎖時間 {record.lock_until.isoformat()}',
            code='locked',
        )

    try:
        secret_bytes = base64.urlsafe_b64decode(secret_b64)
    except Exception:
        _record_failed_login(record)
        raise ServiceAccountError('secret 格式錯誤',
                                  code='invalid_credentials')

    if not bcrypt.checkpw(secret_bytes,
                          record.secret_hash.encode('ascii')):
        _record_failed_login(record)
        raise ServiceAccountError('sa_id 或 secret 錯誤',
                                  code='invalid_credentials')

    _record_success_login(record, source_ip)
    token = issue_jwt(record)
    return record, token


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

def issue_jwt(record: OdServiceAccount,
              ttl_sec: Optional[int] = None) -> str:
    """簽發 JWT(HS256)"""
    ttl = ttl_sec if ttl_sec is not None else _get_jwt_ttl_sec()
    # 用 time.time()(真正的 UTC unix 秒);切勿用 datetime.utcnow().timestamp(),
    # 後者把 naive datetime 當成 local time 轉換,會差一個時區偏移量。
    now_ts = int(time.time())
    payload = {
        'sub': record.sa_id,
        'sa_sc': record.secure_code,
        'org': record.org_secure_code,
        'eps': record.allowed_enforcement_points or [],
        'iat': now_ts,
        'exp': now_ts + ttl,
        'iss': 'beakplatform-open-defense',
    }
    return pyjwt.encode(payload, _get_jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_jwt(token: str) -> Dict[str, Any]:
    """
    驗 JWT 並回傳 claims。
    過期 / 簽章錯 / 格式錯都拋 ServiceAccountError。
    """
    if not token:
        raise ServiceAccountError('token 為空', code='token_missing')
    try:
        return pyjwt.decode(
            token, _get_jwt_secret(),
            algorithms=[JWT_ALGORITHM],
            issuer='beakplatform-open-defense',
            options={'require': ['exp', 'iat', 'sub']},
        )
    except pyjwt.ExpiredSignatureError:
        raise ServiceAccountError('token 已過期', code='token_expired')
    except pyjwt.InvalidTokenError as exc:
        raise ServiceAccountError(f'token 無效: {exc}', code='token_invalid')
