"""
OpenDefense Module - Expiry Service

掃描已 applied 且過期的決策,自動建立對應的 unblock 決策(status='pending')
讓執行端拉走後解除阻擋。原決策 status 改為 'expired',並回填
revoked_by_decision_secure_code 指向新 unblock 決策。

對外契約 §6.4:過期由 BeakPlatform 排程獨佔下發 unblock,執行端不可自行判過期。
"""
import logging
from datetime import datetime
from typing import List, Tuple, Dict, Any

from app import db
from app.utils.security import generate_secure_code

from ..models import OdDefenseDecision

logger = logging.getLogger(__name__)


def find_expired_applied(limit: int = 500) -> List[OdDefenseDecision]:
    """
    找出待處理的過期決策:
      status='applied' AND expires_at IS NOT NULL AND expires_at < now()
      AND revoked_by_decision_secure_code IS NULL
    """
    return OdDefenseDecision.query.filter(
        OdDefenseDecision.status == 'applied',
        OdDefenseDecision.expires_at.isnot(None),
        OdDefenseDecision.expires_at < datetime.utcnow(),
        OdDefenseDecision.revoked_by_decision_secure_code.is_(None),
        OdDefenseDecision.is_deleted.is_(False),
    ).order_by(OdDefenseDecision.expires_at.asc()).limit(limit).all()


def expire_one(record: OdDefenseDecision) -> OdDefenseDecision:
    """
    為單筆過期決策產生 unblock,並標原決策為 expired。

    回傳新建的 unblock decision。每筆獨立 commit(避免長交易卡其他 worker)。
    """
    if record.action == 'unblock':
        # unblock 本身過期不需要再 unblock(避免無限鏈)
        record.status = 'expired'
        record.updated_at = datetime.utcnow()
        db.session.commit()
        logger.info(
            'OpenDefense expire(unblock-self) sc=%s target=%s/%s',
            record.secure_code, record.target_type, record.target_value,
        )
        return record

    now = datetime.utcnow()
    unblock = OdDefenseDecision(
        secure_code=generate_secure_code(),
        org_secure_code=record.org_secure_code,
        case_secure_code=record.case_secure_code,
        workflow_node_id=None,
        intake_event_secure_code=record.intake_event_secure_code,
        action='unblock',
        target_type=record.target_type,
        target_value=record.target_value,
        enforcement_points=record.enforcement_points or [],
        severity=record.severity,
        ttl_seconds=None,
        expires_at=None,
        reason=f'TTL expired auto-unblock (原決策 {record.secure_code})',
        decided_via='auto',
        decided_by_secure_code=None,
        decided_at=now,
        status='pending',
        related_finding_ids=record.related_finding_ids,
        decision_metadata={'expired_from': record.secure_code},
    )
    db.session.add(unblock)
    db.session.flush()

    record.status = 'expired'
    record.revoked_by_decision_secure_code = unblock.secure_code
    record.updated_at = now

    db.session.commit()

    logger.info(
        'OpenDefense expire sc=%s -> unblock=%s target=%s/%s ep=%s',
        record.secure_code, unblock.secure_code,
        record.target_type, record.target_value,
        record.enforcement_points,
    )
    return unblock


def run_expiry_pass(*, dry_run: bool = False, limit: int = 500
                    ) -> Dict[str, Any]:
    """
    執行一輪過期掃描。

    Returns:
        {'scanned': N, 'unblocked': M, 'errors': [...], 'dry_run': bool}
    """
    rows = find_expired_applied(limit=limit)
    result = {
        'scanned': len(rows),
        'unblocked': 0,
        'errors': [],
        'dry_run': dry_run,
    }
    if not rows:
        return result

    for r in rows:
        try:
            if dry_run:
                logger.info(
                    '[DRY-RUN] would expire sc=%s target=%s/%s ep=%s',
                    r.secure_code, r.target_type, r.target_value,
                    r.enforcement_points,
                )
            else:
                expire_one(r)
            result['unblocked'] += 1
        except Exception as exc:
            db.session.rollback()
            logger.exception('expire failed sc=%s', r.secure_code)
            result['errors'].append({
                'decision_secure_code': r.secure_code,
                'error': str(exc),
            })

    return result
