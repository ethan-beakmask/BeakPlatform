"""
One-time API Key claim service.

Claims only authorize a beneficiary to retrieve an existing ApiKey secret once.
No plaintext, ciphertext, or hash of the secret is stored or logged here.
"""
import base64
import logging
from datetime import datetime, timedelta
from typing import Optional

from flask_babel import gettext as _

from app import db
from app.models.api_key import ApiKey, STATUS_ACTIVE
from app.models.api_key_claim import ApiKeyClaim
from app.utils.security import generate_secure_code
from app.services import api_key_service

logger = logging.getLogger(__name__)

# 注意:訊息在拋出點才包 _(),不要寫成 _(常數)——
# pybabel extract 抓不到以變數為引數的 gettext,該 msgid 不會進語系檔。
CLAIM_ERROR_MESSAGE = '無法領取 API Key'


class ClaimError(Exception):
    """API Key claim failure with a uniform public message."""


def create_claim(*, api_key_secure_code, org_secure_code,
                 beneficiary_user_secure_code, form_instance_secure_code=None,
                 ttl_hours=72):
    """核發後建立一次性領取憑證。回傳 ApiKeyClaim。"""
    if not api_key_secure_code:
        raise ClaimError(_('api_key_secure_code 必填'))
    if not org_secure_code:
        raise ClaimError(_('org_secure_code 必填'))
    if not beneficiary_user_secure_code:
        raise ClaimError(_('beneficiary_user_secure_code 必填'))

    claim = ApiKeyClaim(
        secure_code=generate_secure_code(),
        org_secure_code=org_secure_code,
        api_key_secure_code=api_key_secure_code,
        beneficiary_user_secure_code=beneficiary_user_secure_code,
        form_instance_secure_code=form_instance_secure_code or None,
        expires_at=datetime.utcnow() + timedelta(hours=int(ttl_hours or 72)),
    )
    db.session.add(claim)
    db.session.commit()

    logger.info(
        'api_key_claim created claim_sc=%s api_key_sc=%s org=%s beneficiary=%s form=%s',
        claim.secure_code, api_key_secure_code, org_secure_code,
        beneficiary_user_secure_code, form_instance_secure_code,
    )
    return claim


def list_claims_for_user(user_secure_code, org_secure_code):
    """該使用者名下的領取記錄(含已領取與已過期,供清單顯示)。"""
    if not user_secure_code or not org_secure_code:
        return []
    return ApiKeyClaim.query.filter_by(
        beneficiary_user_secure_code=user_secure_code,
        org_secure_code=org_secure_code,
        is_deleted=False,
    ).order_by(ApiKeyClaim.created_at.desc()).all()


def _deny_claim(reason: str, *, secure_code: Optional[str],
                user_secure_code: Optional[str], org_secure_code: Optional[str]):
    logger.warning(
        'api_key_claim denied reason=%s claim_sc=%s user=%s org=%s',
        reason, secure_code, user_secure_code, org_secure_code,
    )
    raise ClaimError(_('無法領取 API Key'))


def claim_once(secure_code, user_secure_code, org_secure_code, source_ip=None):
    """
    領取 secret,一次性。

    成功回傳 (api_key_record, plaintext_secret_b64)。
    失敗一律 raise ClaimError,且錯誤訊息不得洩漏「這筆存不存在」的差異。
    """
    claim = ApiKeyClaim.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org_secure_code,
    ).first()
    if claim is None:
        _deny_claim(
            'claim_not_found_or_org_mismatch',
            secure_code=secure_code,
            user_secure_code=user_secure_code,
            org_secure_code=org_secure_code,
        )
    if claim.is_deleted:
        _deny_claim(
            'claim_deleted',
            secure_code=secure_code,
            user_secure_code=user_secure_code,
            org_secure_code=org_secure_code,
        )
    if claim.org_secure_code != org_secure_code:
        _deny_claim(
            'org_mismatch',
            secure_code=secure_code,
            user_secure_code=user_secure_code,
            org_secure_code=org_secure_code,
        )
    if claim.beneficiary_user_secure_code != user_secure_code:
        _deny_claim(
            'beneficiary_mismatch',
            secure_code=secure_code,
            user_secure_code=user_secure_code,
            org_secure_code=org_secure_code,
        )
    if claim.claimed_at is not None:
        _deny_claim(
            'already_claimed',
            secure_code=secure_code,
            user_secure_code=user_secure_code,
            org_secure_code=org_secure_code,
        )
    if claim.expires_at < datetime.utcnow():
        _deny_claim(
            'claim_expired',
            secure_code=secure_code,
            user_secure_code=user_secure_code,
            org_secure_code=org_secure_code,
        )

    api_key_record = ApiKey.query.filter_by(
        secure_code=claim.api_key_secure_code,
        org_secure_code=org_secure_code,
    ).first()
    if api_key_record is None:
        _deny_claim(
            'api_key_not_found',
            secure_code=secure_code,
            user_secure_code=user_secure_code,
            org_secure_code=org_secure_code,
        )
    if api_key_record.is_deleted:
        _deny_claim(
            'api_key_deleted',
            secure_code=secure_code,
            user_secure_code=user_secure_code,
            org_secure_code=org_secure_code,
        )
    if api_key_record.status != STATUS_ACTIVE:
        _deny_claim(
            'api_key_not_active',
            secure_code=secure_code,
            user_secure_code=user_secure_code,
            org_secure_code=org_secure_code,
        )

    claim.claimed_at = datetime.utcnow()
    claim.claimed_ip = source_ip
    db.session.commit()

    plaintext_secret = api_key_service.decrypt_secret(api_key_record)
    plaintext_secret_b64 = base64.urlsafe_b64encode(plaintext_secret).decode('ascii')
    logger.info(
        'api_key_claim claimed claim_sc=%s api_key_sc=%s org=%s beneficiary=%s',
        claim.secure_code, api_key_record.secure_code, org_secure_code,
        user_secure_code,
    )
    return api_key_record, plaintext_secret_b64
