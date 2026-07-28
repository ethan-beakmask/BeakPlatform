"""NoCode portal workflow service account management."""
from __future__ import annotations

import logging

from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Organization, User
from app.utils.security import generate_secure_code

logger = logging.getLogger(__name__)


def _org_code(org_secure_code: str) -> str:
    org = Organization.query.filter_by(
        secure_code=org_secure_code,
        is_deleted=False,
    ).first()
    if org and org.code:
        return org.code.lower()
    return (org_secure_code or 'nocode')[:8].lower()


def get_or_create(org_secure_code: str) -> User:
    """Return the per-org NoCode public workflow applicant account."""
    existing = User.query.filter_by(
        org_secure_code=org_secure_code,
        is_service_account=True,
        is_deleted=False,
    ).first()
    if existing:
        return existing

    org_code = _org_code(org_secure_code)
    user = User(
        secure_code=generate_secure_code(),
        org_secure_code=org_secure_code,
        username=f'nocode-svc-{org_code}',
        email=f'nocode-svc@{org_code}.local',
        display_name='NoCode 公用帳號',
        user_type='EXTERNAL',
        is_active=True,
        is_deleted=False,
        is_service_account=True,
        password_hash='!nologin',
    )
    db.session.add(user)
    try:
        db.session.commit()
        logger.info('NoCode service account created org=%s user=%s', org_secure_code, user.secure_code)
        return user
    except IntegrityError:
        db.session.rollback()
        existing = User.query.filter_by(
            org_secure_code=org_secure_code,
            is_service_account=True,
            is_deleted=False,
        ).first()
        if existing:
            return existing
        raise
