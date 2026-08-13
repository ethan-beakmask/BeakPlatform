"""
OpenDefense Module - Decision Service

封裝 OdDefenseDecision 的建立/查詢/狀態轉換邏輯。
所有寫入點集中於此,handler 與 API 都透過此處呼叫,
方便日後加入稽核 / 統一驗證 / 通知。
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from flask_babel import gettext as _

from app import db
from app.utils.security import generate_secure_code

from ..models import (
    OdDefenseDecision,
    VALID_ACTIONS,
    VALID_TARGET_TYPES,
    VALID_DECIDED_VIA,
    VALID_SEVERITIES,
)
from .protected_target_service import (
    CHECKED_ACTIONS,
    CHECKED_TARGET_TYPES,
    InvalidTargetValueError,
    check_block_target,
)

logger = logging.getLogger(__name__)


class DecisionValidationError(ValueError):
    """決策參數驗證失敗"""


class ProtectedTargetError(DecisionValidationError):
    """目標命中封鎖保護清單，拒絕寫入"""
    def __init__(self, message, hit=None):
        super().__init__(message)
        self.hit = hit


def _validate(action: str, target_type: str, target_value: str,
              decided_via: str, severity: Optional[str]) -> None:
    if action not in VALID_ACTIONS:
        raise DecisionValidationError(_('action 不合法: %(action)r', action=action))
    if target_type not in VALID_TARGET_TYPES:
        raise DecisionValidationError(_('target_type 不合法: %(target_type)r', target_type=target_type))
    if not target_value or not target_value.strip():
        raise DecisionValidationError(_('target_value 不可為空'))
    if len(target_value) > 500:
        raise DecisionValidationError(_('target_value 過長(>500)'))
    if decided_via not in VALID_DECIDED_VIA:
        raise DecisionValidationError(_('decided_via 不合法: %(decided_via)r', decided_via=decided_via))
    if severity is not None and severity not in VALID_SEVERITIES:
        raise DecisionValidationError(_('severity 不合法: %(severity)r', severity=severity))


def create_decision(
    *,
    org_secure_code: str,
    action: str,
    target_type: str,
    target_value: str,
    decided_via: str,
    enforcement_points: Optional[List[str]] = None,
    severity: Optional[str] = None,
    ttl_seconds: Optional[int] = None,
    reason: Optional[str] = None,
    decided_by_secure_code: Optional[str] = None,
    case_secure_code: Optional[str] = None,
    workflow_node_id: Optional[str] = None,
    intake_event_secure_code: Optional[str] = None,
    related_finding_ids: Optional[List[str]] = None,
    decision_metadata: Optional[Dict[str, Any]] = None,
    allow_protected_target: bool = False,
    protected_override_reason: Optional[str] = None,
    commit: bool = True,
) -> OdDefenseDecision:
    """
    建立一筆防禦決策。

    org_secure_code 必填,**呼叫端必須明確傳入**(handler 從 queue_item 取,
    API 從登入企業取)。本函式不從 g 自動推斷,避免跨租戶汙染。
    """
    if not org_secure_code:
        raise DecisionValidationError(_('org_secure_code 必填'))

    _validate(action, target_type, target_value, decided_via, severity)

    protected_hit = None
    if action in CHECKED_ACTIONS and target_type in CHECKED_TARGET_TYPES:
        try:
            protected_hit = check_block_target(
                org_secure_code=org_secure_code,
                action=action,
                target_type=target_type,
                target_value=target_value,
            )
        except InvalidTargetValueError:
            raise DecisionValidationError(
                _('target_value 不是合法的 IP 或 CIDR: %(v)s', v=target_value)
            )

        if protected_hit is not None and not allow_protected_target:
            logger.warning(
                'OpenDefense blocked a protected target org=%s action=%s target=%s/%s '
                'hit_source=%s hit_network=%s case=%s node=%s',
                org_secure_code, action, target_type, target_value,
                protected_hit.source, protected_hit.network,
                case_secure_code, workflow_node_id,
            )
            raise ProtectedTargetError(
                _('目標 %(target)s 命中封鎖保護清單（%(network)s），已拒絕寫入封鎖決策。'
                  '若確認要封鎖此位址，請由管理員在保護清單設定豁免項目，'
                  '或在流程節點明確允許覆寫。',
                  target=target_value, network=protected_hit.network),
                hit=protected_hit,
            )

        if protected_hit is not None:
            logger.warning(
                'OpenDefense protected-target override org=%s target=%s hit=%s reason=%s',
                org_secure_code, target_value, protected_hit.network, protected_override_reason,
            )
            decision_metadata = dict(decision_metadata or {})
            decision_metadata['protected_override'] = {
                'source': protected_hit.source,
                'network': protected_hit.network,
                'entry_secure_code': protected_hit.entry_secure_code,
                'reason': protected_override_reason or None,
            }

    if ttl_seconds is not None and ttl_seconds <= 0:
        raise DecisionValidationError(_('ttl_seconds 必須 > 0,或不傳'))

    decided_at = datetime.utcnow()
    expires_at = (
        decided_at + timedelta(seconds=ttl_seconds)
        if ttl_seconds is not None else None
    )

    decision = OdDefenseDecision(
        secure_code=generate_secure_code(),
        org_secure_code=org_secure_code,
        case_secure_code=case_secure_code,
        workflow_node_id=workflow_node_id,
        intake_event_secure_code=intake_event_secure_code,
        action=action,
        target_type=target_type,
        target_value=target_value.strip(),
        enforcement_points=enforcement_points or [],
        severity=severity,
        ttl_seconds=ttl_seconds,
        expires_at=expires_at,
        reason=reason,
        decided_via=decided_via,
        decided_by_secure_code=decided_by_secure_code,
        decided_at=decided_at,
        status='pending',
        related_finding_ids=related_finding_ids,
        decision_metadata=decision_metadata,
    )

    db.session.add(decision)
    if commit:
        db.session.commit()
    else:
        db.session.flush()

    logger.info(
        'OpenDefense decision created sc=%s org=%s action=%s target=%s/%s ttl=%s',
        decision.secure_code, org_secure_code, action,
        target_type, target_value, ttl_seconds,
    )

    return decision


# =============================================================================
# 查詢 / 狀態轉換(供執行端 API 用)
# =============================================================================

# 對外契約 §5.2 允許的狀態轉換
ALLOWED_TRANSITIONS = {
    'pending':   {'picked_up', 'applied', 'partial', 'failed'},
    'picked_up': {'applied', 'partial', 'failed'},
}

# 執行端禁止寫入(由 BeakPlatform 排程獨佔)
FORBIDDEN_TARGET_STATUSES = {'expired', 'revoked'}


class DecisionStatusError(Exception):
    """狀態轉換 / 樂觀鎖錯誤"""
    def __init__(self, message: str, code: str, status: int = 409):
        super().__init__(message)
        self.code = code
        self.status = status


def list_decisions_for_sa(
    *,
    org_secure_code: str,
    sa_allowed_eps: List[str],
    status: str = 'pending',
    enforcement_point: Optional[str] = None,
    limit: int = 100,
    since: Optional[datetime] = None,
) -> List[OdDefenseDecision]:
    """
    執行端拉取決策。

    過濾:
      - org 嚴格綁 SA 的 org(防跨租戶)
      - status(預設 pending)
      - enforcement_points 與 SA 的 allowed_enforcement_points 取交集
        - SA allowed_eps = [] 表示全部允許
      - enforcement_point 參數可進一步只取含此 EP 的決策
      - since 過濾 created_at
    """
    if limit <= 0 or limit > 500:
        limit = min(max(limit, 1), 500)

    q = OdDefenseDecision.query.filter_by(
        org_secure_code=org_secure_code,
        status=status,
        is_deleted=False,
    )

    # SA 的 allowed_eps 過濾:OR(enforcement_points @> ['ep1'], ... @> ['ep2'])
    # 空 list = 全部允許,不加過濾
    if sa_allowed_eps:
        from sqlalchemy import or_
        from sqlalchemy.dialects.postgresql import JSONB
        ep_clauses = [
            OdDefenseDecision.enforcement_points.op('@>')(
                db.cast([ep], JSONB)
            )
            for ep in sa_allowed_eps
        ]
        q = q.filter(or_(*ep_clauses))

    if enforcement_point:
        from sqlalchemy.dialects.postgresql import JSONB
        q = q.filter(
            OdDefenseDecision.enforcement_points.op('@>')(
                db.cast([enforcement_point], JSONB)
            )
        )

    if since is not None:
        q = q.filter(OdDefenseDecision.created_at > since)

    q = q.order_by(OdDefenseDecision.created_at.asc()).limit(limit)
    return q.all()


def get_decision_for_sa(
    *,
    secure_code: str,
    org_secure_code: str,
) -> Optional[OdDefenseDecision]:
    """執行端取單筆,綁 SA 的 org"""
    return OdDefenseDecision.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org_secure_code,
        is_deleted=False,
    ).first()


def update_decision_status(
    *,
    secure_code: str,
    org_secure_code: str,
    target_status: str,
    applied_by: Optional[str] = None,
    application_result: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None,
) -> OdDefenseDecision:
    """
    執行端回報狀態。

    安全規則:
      - 禁寫 expired / revoked(由 BeakPlatform 排程獨佔)
      - 只允許從 pending / picked_up 轉出
      - PATCH picked_up 用樂觀鎖(WHERE status='pending'),雙搶失敗回 409
    """
    if target_status in FORBIDDEN_TARGET_STATUSES:
        raise DecisionStatusError(
            _('禁止由執行端寫入 %(target_status)r', target_status=target_status),
            code='forbidden_status', status=403,
        )
    if target_status not in {'picked_up', 'applied', 'partial', 'failed'}:
        raise DecisionStatusError(
            _('不合法的目標狀態 %(target_status)r', target_status=target_status),
            code='invalid_status', status=400,
        )

    record = get_decision_for_sa(
        secure_code=secure_code,
        org_secure_code=org_secure_code,
    )
    if record is None:
        raise DecisionStatusError(
            _('決策不存在或不屬於本 SA 的 org'),
            code='not_found', status=404,
        )

    if record.status not in ALLOWED_TRANSITIONS:
        raise DecisionStatusError(
            _('從 %(status)r 不可轉至任何狀態(已結案)', status=record.status),
            code='not_transitionable', status=409,
        )
    if target_status not in ALLOWED_TRANSITIONS[record.status]:
        raise DecisionStatusError(
            _('不可從 %(status)r 轉至 %(target_status)r',
              status=record.status, target_status=target_status),
            code='invalid_transition', status=409,
        )

    now = datetime.utcnow()

    if target_status == 'picked_up':
        # 樂觀鎖:WHERE status='pending'
        from sqlalchemy import update
        rowcount = db.session.execute(
            update(OdDefenseDecision)
            .where(OdDefenseDecision.id == record.id)
            .where(OdDefenseDecision.status == 'pending')
            .values(
                status='picked_up',
                picked_up_at=now,
                applied_by=applied_by,
                updated_at=now,
            )
        ).rowcount
        db.session.commit()
        if rowcount == 0:
            raise DecisionStatusError(
                _('決策已被其他執行端搶先拾起'),
                code='race_lost', status=409,
            )
        db.session.refresh(record)
        return record

    # applied / partial / failed
    record.status = target_status
    record.applied_at = now
    record.updated_at = now
    if applied_by is not None:
        record.applied_by = applied_by
    if application_result is not None:
        record.application_result = application_result
    if error_message is not None:
        record.error_message = error_message
    db.session.commit()
    return record
