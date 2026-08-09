"""
OpenDefense Module - Routing Service

依企業自訂規則將正規化 OCSF 事件路由到 form_template。
"""
import logging
from numbers import Number
from typing import Any, Optional, Tuple

from flask_babel import gettext as _

from ..models import OdFormTemplateMapping

logger = logging.getLogger(__name__)

SUPPORTED_OPS = {
    'eq', 'ne', 'in', 'not_in',
    'gt', 'gte', 'lt', 'lte',
    'contains', 'startswith', 'endswith',
    'exists',
}
NUMERIC_OPS = {'gt', 'gte', 'lt', 'lte'}


def validate_match_rules(match_rules) -> tuple[bool, str]:
    """驗證規則格式，回傳 (是否合法, 錯誤訊息)。供寫入端使用。"""
    if match_rules is None:
        return True, ''
    if not isinstance(match_rules, list):
        return False, _('match_rules 必須為陣列')

    for idx, condition in enumerate(match_rules):
        prefix = f'match_rules[{idx}]'
        if not isinstance(condition, dict):
            return False, _('%(prefix)s 必須為物件', prefix=prefix)

        field = condition.get('field')
        op = condition.get('op')
        if not isinstance(field, str) or not field.strip():
            return False, _('%(prefix)s.field 必填', prefix=prefix)
        if not isinstance(op, str) or not op.strip():
            return False, _('%(prefix)s.op 必填', prefix=prefix)
        if op not in SUPPORTED_OPS:
            return False, _('%(prefix)s.op 不支援', prefix=prefix)

        if op in ('in', 'not_in') and not isinstance(condition.get('value'), list):
            return False, _('%(prefix)s.value 必須為陣列', prefix=prefix)
        if op == 'exists' and not isinstance(condition.get('value'), bool):
            return False, _('%(prefix)s.value 必須為 boolean', prefix=prefix)
        if op != 'exists' and 'value' not in condition:
            return False, _('%(prefix)s.value 必填', prefix=prefix)

    return True, ''


def resolve_form_template(org_secure_code: str, body: dict) -> Optional[str]:
    """依規則決定這個事件要用哪張表單模板，回傳 form_template_secure_code。"""
    matched, _evaluated = evaluate_routing_rules(org_secure_code, body)
    return matched.form_template_secure_code if matched else None


def evaluate_routing_rules(org_secure_code: str, body: dict):
    """
    回傳 (matched_rule, evaluated)。

    evaluated 供管理 API 試算使用；實際 intake 與試算共用相同命中邏輯。
    """
    rules = OdFormTemplateMapping.query.filter_by(
        org_secure_code=org_secure_code,
        is_deleted=False,
        is_active=True,
    ).order_by(
        OdFormTemplateMapping.priority.desc(),
        OdFormTemplateMapping.id.asc(),
    ).all()

    evaluated = []
    for rule in rules:
        matched, failed_condition = _rule_matches(rule, body)
        evaluated.append({
            'secure_code': rule.secure_code,
            'name': rule.name,
            'matched': matched,
            'failed_condition': failed_condition,
        })
        if matched:
            return rule, evaluated

    return None, evaluated


def _rule_matches(rule: OdFormTemplateMapping, body: dict) -> Tuple[bool, Optional[dict]]:
    if rule.event_class is not None and rule.event_class != body.get('event_class'):
        return False, {
            'field': 'event_class',
            'op': 'eq',
            'value': rule.event_class,
        }

    match_rules = rule.match_rules
    ok, message = validate_match_rules(match_rules)
    if not ok:
        logger.warning(
            'od routing rule invalid secure_code=%s reason=%s',
            rule.secure_code, message,
        )
        return False, None

    for condition in match_rules or []:
        if not _condition_matches(body, condition):
            return False, condition

    return True, None


def _condition_matches(body: dict, condition: dict) -> bool:
    actual = _get_field_value(body, condition['field'])
    op = condition['op']
    expected = condition.get('value')

    if op == 'exists':
        exists = actual is not None and not (isinstance(actual, str) and actual == '')
        return exists is expected
    if actual is None:
        return False

    if op == 'eq':
        return _values_equal(actual, expected)
    if op == 'ne':
        return not _values_equal(actual, expected)
    if op == 'in':
        return any(_values_equal(actual, item) for item in expected)
    if op == 'not_in':
        return not any(_values_equal(actual, item) for item in expected)
    if op in NUMERIC_OPS:
        return _compare_number(actual, expected, op)

    actual_text = str(actual).lower()
    expected_text = str(expected).lower()
    if op == 'contains':
        return expected_text in actual_text
    if op == 'startswith':
        return actual_text.startswith(expected_text)
    if op == 'endswith':
        return actual_text.endswith(expected_text)

    return False


def _get_field_value(body: dict, field: str) -> Any:
    current: Any = body
    for part in field.split('.'):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current.get(part)
    return current


def _values_equal(actual: Any, expected: Any) -> bool:
    if _is_number(actual) and _is_number(expected):
        return float(actual) == float(expected)
    if isinstance(actual, str) or isinstance(expected, str):
        return str(actual).lower() == str(expected).lower()
    return actual == expected


def _compare_number(actual: Any, expected: Any, op: str) -> bool:
    if not _is_number(actual) or not _is_number(expected):
        return False

    left = float(actual)
    right = float(expected)
    if op == 'gt':
        return left > right
    if op == 'gte':
        return left >= right
    if op == 'lt':
        return left < right
    if op == 'lte':
        return left <= right
    return False


def _is_number(value: Any) -> bool:
    return isinstance(value, Number) and not isinstance(value, bool)
