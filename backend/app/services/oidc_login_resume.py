"""Safe session-only continuation for OIDC authorization."""
import time

from flask import session, url_for


PENDING_MAX_AGE = 600


def pending_authorize_redirect() -> str | None:
    pending = session.get('oidc_pending')
    if not isinstance(pending, dict):
        return None
    try:
        valid = time.time() - float(pending['created_at']) <= PENDING_MAX_AGE
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        session.pop('oidc_pending', None)
        return None
    return url_for('oidc_provider.authorize_resume')
