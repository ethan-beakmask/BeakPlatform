"""
OpenDefense Module - Intake Schema

驗證 POST /api/open_defense/intake 的 body(對外契約 §4.3)。
不引入 marshmallow,維持輕量,直接遞迴檢查 dict。
"""
from typing import Any, Dict, List, Tuple

from flask_babel import gettext as _


VALID_EVENT_CLASSES = (
    'detection_finding',
    'network_activity',
    'web_activity',
    'process_activity',
)

# 需要 actor.ip 的事件類型
EVENT_CLASS_REQUIRE_ACTOR_IP = ('network_activity', 'web_activity')


class IntakeValidationError(ValueError):
    """Body 不符 schema"""
    def __init__(self, message: str, details: List[Dict] = None):
        super().__init__(message)
        self.details = details or []


def _err(field: str, msg: str) -> Dict:
    return {'field': field, 'error': msg}


def validate_intake_body(body: Any) -> Dict[str, Any]:
    """
    驗證並正規化 webhook body。

    Args:
        body: 反序列化後的 JSON dict
    Returns:
        正規化後的 dict(僅含已知欄位,未知欄位被丟棄但不報錯)
    Raises:
        IntakeValidationError: 任一必要欄位缺失或型別錯誤
    """
    errors: List[Dict] = []

    if not isinstance(body, dict):
        raise IntakeValidationError(_('body 必須為 JSON object'),
                                    [_err('', 'not a dict')])

    # 必填頂層欄位
    correlation_id = body.get('correlation_id')
    if not isinstance(correlation_id, str) or not correlation_id.strip():
        errors.append(_err('correlation_id', _('必填,字串')))
    elif len(correlation_id) > 64:
        errors.append(_err('correlation_id', _('長度 > 64')))

    source_system = body.get('source_system')
    if not isinstance(source_system, str) or not source_system.strip():
        errors.append(_err('source_system', _('必填,字串')))
    elif len(source_system) > 50:
        errors.append(_err('source_system', _('長度 > 50')))

    event_class = body.get('event_class')
    if event_class not in VALID_EVENT_CLASSES:
        errors.append(_err('event_class',
                          _('必須為 %(classes)s 之一', classes=VALID_EVENT_CLASSES)))

    occurred_at = body.get('occurred_at')
    if not isinstance(occurred_at, str) or not occurred_at:
        errors.append(_err('occurred_at', _('必填,ISO-8601 UTC 字串')))

    severity_id = body.get('severity_id')
    if not isinstance(severity_id, int):
        errors.append(_err('severity_id', _('必填,int 0-6')))
    elif severity_id < 0 or severity_id > 6:
        errors.append(_err('severity_id', _('必須在 0-6 範圍')))

    confidence = body.get('confidence')
    if confidence is not None:
        if not isinstance(confidence, int) or confidence < 0 or confidence > 100:
            errors.append(_err('confidence', _('若提供須為 0-100 int')))

    # finding(必填,title 必填)
    finding = body.get('finding')
    if not isinstance(finding, dict):
        errors.append(_err('finding', _('必填,object')))
    else:
        title = finding.get('title')
        if not isinstance(title, str) or not title.strip():
            errors.append(_err('finding.title', _('必填,字串')))
        elif len(title) > 200:
            errors.append(_err('finding.title', _('長度 > 200')))

    # actor / target(視 event_class 而定)
    actor = body.get('actor') or {}
    target = body.get('target') or {}
    if not isinstance(actor, dict):
        errors.append(_err('actor', _('必須為 object')))
        actor = {}
    if not isinstance(target, dict):
        errors.append(_err('target', _('必須為 object')))
        target = {}

    if event_class in EVENT_CLASS_REQUIRE_ACTOR_IP:
        if not actor.get('ip'):
            errors.append(_err('actor.ip',
                              _('event_class=%(event_class)s 時必填', event_class=event_class)))

    # evidence / detector_hint:可選,僅做型別檢查
    evidence = body.get('evidence')
    if evidence is not None and not isinstance(evidence, dict):
        errors.append(_err('evidence', _('若提供須為 object')))
    detector_hint = body.get('detector_hint')
    if detector_hint is not None and not isinstance(detector_hint, dict):
        errors.append(_err('detector_hint', _('若提供須為 object')))

    if errors:
        raise IntakeValidationError('schema validation failed', errors)

    # 正規化:只保留已知欄位
    return {
        'correlation_id': correlation_id.strip(),
        'source_system': source_system.strip(),
        'event_class': event_class,
        'occurred_at': occurred_at,
        'severity_id': severity_id,
        'confidence': confidence,
        'finding': finding,
        'actor': actor,
        'target': target,
        'evidence': evidence or {},
        'detector_hint': detector_hint or {},
    }
