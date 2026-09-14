"""
OpenDefense protected target defaults.

出廠保護清單資料值會寫入 DB，不包 gettext。
"""
import logging

from app import db
from app.utils.security import generate_secure_code

logger = logging.getLogger(__name__)


BUILTIN_PROTECTED_DEFAULTS = (
    ('0.0.0.0/8', '本網路'),
    ('10.0.0.0/8', '私有網段 (RFC1918)'),
    ('100.64.0.0/10', 'CGNAT (RFC6598)'),
    ('127.0.0.0/8', '回送位址'),
    ('169.254.0.0/16', 'Link-local'),
    ('172.16.0.0/12', '私有網段 (RFC1918)'),
    ('192.0.0.0/24', 'IETF 協定保留'),
    ('192.168.0.0/16', '私有網段 (RFC1918)'),
    ('198.18.0.0/15', '效能測試保留'),
    ('224.0.0.0/4', '群播位址'),
    ('240.0.0.0/4', '保留位址'),
    ('::/128', '未指定位址'),
    ('::1/128', '回送位址'),
    ('fc00::/7', '唯一區域位址 (ULA)'),
    ('fe80::/10', 'Link-local'),
    ('ff00::/8', '群播位址'),
)


def seed_org_builtin_protected_targets(
    org_secure_code,
    *,
    created_by_secure_code=None,
) -> int:
    """為單一企業種入 origin='builtin' 的保護條目（冪等，不 commit）。

    回傳實際新增的筆數。呼叫端負責 commit。
    """
    if not org_secure_code:
        return 0

    try:
        from modules.open_defense.models import OdProtectedTarget
    except ImportError:
        logger.warning('OpenDefense protected target defaults unavailable; skip seed')
        return 0

    created = 0
    for target_value, label in BUILTIN_PROTECTED_DEFAULTS:
        exists = OdProtectedTarget.query.filter_by(
            org_secure_code=org_secure_code,
            entry_type='protect',
            target_value=target_value,
            is_deleted=False,
        ).first()
        if exists:
            continue

        db.session.add(OdProtectedTarget(
            secure_code=generate_secure_code(),
            org_secure_code=org_secure_code,
            entry_type='protect',
            origin='builtin',
            target_value=target_value,
            name=label,
            is_active=True,
            note=None,
            created_by_secure_code=created_by_secure_code,
            is_deleted=False,
        ))
        created += 1

    if created:
        db.session.flush()
    logger.info(
        'OpenDefense builtin protected targets seeded org=%s created=%s',
        org_secure_code, created,
    )
    return created
