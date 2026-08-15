"""
OpenDefense Module - Payload Profile Service

原生 SOC payload 的路徑取值、扁平化、明細抽取與共同軸線正規化。
"""
import hashlib
import logging
from typing import Any

from flask_babel import gettext as _

logger = logging.getLogger(__name__)

AXIS_FIELD_KEYS = {
    'severity_id',
    'actor_ip',
    'target_host',
    'source_system',
    'finding_rule_id',
    'occurred_at',
}
RESERVED_FORM_KEYS = AXIS_FIELD_KEYS | {'od_payload_profile'}
MAX_FLAT_DEPTH = 6
MAX_FLAT_KEYS = 500
MAX_STRING_LENGTH = 8000
MAX_DETAILS = 500


def get_path(payload: dict, path: str):
    """點號路徑取值。任一段不存在或不是 dict 回 None。空 path 回 None。"""
    if not path:
        return None
    current: Any = payload
    for part in path.split('.'):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current.get(part)
    return current


def _normalize_kv_expansions(kv_expansions: list = None) -> dict:
    by_path = {}
    for item in kv_expansions or []:
        if not isinstance(item, dict):
            continue
        path = item.get('path')
        key_field = item.get('key_field')
        value_field = item.get('value_field')
        if not path or not key_field or not value_field:
            continue
        by_path[path] = item
    return by_path


def _clip_string(value: str, key: str) -> str:
    if len(value) <= MAX_STRING_LENGTH:
        return value
    logger.warning('native payload string truncated key=%s length=%s', key, len(value))
    return value[:MAX_STRING_LENGTH]


def _put_flat(result: dict, key: str, value: Any) -> bool:
    if len(result) >= MAX_FLAT_KEYS:
        logger.warning('native payload flatten key limit reached key=%s', key)
        return False
    if isinstance(value, str):
        value = _clip_string(value, key)
    result[key] = value
    return True


def _expand_kv(result: dict, payload: dict, config: dict) -> None:
    rows = get_path(payload, config.get('path'))
    if not isinstance(rows, list):
        return

    prefix = config.get('prefix') or config.get('path')
    key_field = config.get('key_field')
    value_field = config.get('value_field')
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = row.get(key_field)
        if key in (None, ''):
            continue
        flat_key = f'{prefix}.{key}'
        if not _put_flat(result, flat_key, row.get(value_field)):
            return


def flatten_payload(payload: dict, kv_expansions: list = None,
                    detail_path: str = None) -> dict:
    """
    把巢狀 dict 攤平成 {'Summary.RuleId': 'AV-017A', ...}。

    list 預設不展開；detail_path 指到的 list 不放進結果，kv_expansions 指到的 list
    展開成 KV 後原始 list 不保留。超過防爆上限時記錄 warning 並停止該分支。
    """
    result = {}
    kv_by_path = _normalize_kv_expansions(kv_expansions)

    def walk(value: Any, prefix: str, depth: int) -> None:
        if len(result) >= MAX_FLAT_KEYS:
            logger.warning('native payload flatten key limit reached prefix=%s', prefix)
            return
        if depth > MAX_FLAT_DEPTH:
            logger.warning('native payload flatten depth limit reached prefix=%s', prefix)
            return

        if prefix and prefix in kv_by_path:
            _expand_kv(result, payload, kv_by_path[prefix])
            return
        if prefix and detail_path and prefix == detail_path:
            return

        if isinstance(value, dict):
            for key, child in value.items():
                child_key = str(key)
                next_prefix = f'{prefix}.{child_key}' if prefix else child_key
                walk(child, next_prefix, depth + 1)
                if len(result) >= MAX_FLAT_KEYS:
                    return
            return

        if isinstance(value, list):
            if prefix:
                _put_flat(result, prefix, value)
            return

        if prefix:
            _put_flat(result, prefix, value)

    walk(payload, '', 0)
    return result


def extract_details(payload: dict, detail_path: str,
                    detail_item_key: str = None) -> list:
    """
    取明細陣列。detail_path 指到的值不是 list 時回 []。
    detail_item_key 有值時，取每個元素的該鍵。
    """
    rows = get_path(payload, detail_path)
    if not isinstance(rows, list):
        return []
    if len(rows) > MAX_DETAILS:
        logger.warning('native payload details truncated path=%s length=%s',
                       detail_path, len(rows))
        rows = rows[:MAX_DETAILS]

    if not detail_item_key:
        return rows

    details = []
    for row in rows:
        if not isinstance(row, dict) or detail_item_key not in row:
            continue
        details.append(row.get(detail_item_key))
    return details


def _to_optional_str(value: Any):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_optional_int(value: Any):
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_axis_fields(payload: dict, profile) -> dict:
    """
    依 profile.field_map 產出共同軸線 6 欄的正規化值，回傳 dict。
    """
    field_map = profile.field_map or {}
    severity_value = get_path(payload, field_map.get('severity_id') or '')
    severity_map = profile.severity_map or {}
    mapped_severity = severity_map.get(str(severity_value))
    if mapped_severity is not None:
        severity_value = mapped_severity

    source_value = get_path(payload, field_map.get('source_system') or '')
    source_system = _to_optional_str(source_value) or profile.source_system

    return {
        'severity_id': _to_optional_int(severity_value),
        'actor_ip': _to_optional_str(get_path(payload, field_map.get('actor_ip') or '')),
        'target_host': _to_optional_str(get_path(payload, field_map.get('target_host') or '')),
        'source_system': source_system,
        'finding_rule_id': _to_optional_str(get_path(payload, field_map.get('finding_rule_id') or '')),
        'occurred_at': _to_optional_str(get_path(payload, field_map.get('occurred_at') or '')),
    }


def build_native_form_data(payload: dict, profile) -> dict:
    """
    產出要寫進 fw_form_instances.form_data 的完整 dict。
    """
    axis = normalize_axis_fields(payload, profile)
    form_data = dict(axis)
    form_data['od_payload_profile'] = profile.code

    # PF-105：完整 XFF 鏈原文（證據欄位）。刻意不進 AXIS_FIELD_KEYS/field_map——
    # 那是「SLA/聚合/風險分數會讀的判定欄位」的語意，XFF 只是證據，加進去會連帶
    # 膨脹 RESERVED_FORM_KEYS 並可能與既有表單欄位撞名。這裡固定讀 payload 裡
    # OCSF 慣例的 actor.xff 路徑，讀不到就不寫（不用空字串佔位，避免蓋掉
    # flatten_payload 可能自然產生的其他鍵）。
    actor_xff = _to_optional_str(get_path(payload, 'actor.xff'))
    if actor_xff is not None:
        form_data['actor_xff'] = actor_xff

    flat = flatten_payload(
        payload,
        kv_expansions=profile.kv_expansions,
        detail_path=profile.detail_path,
    )
    for key, value in flat.items():
        if key in RESERVED_FORM_KEYS:
            logger.info('native payload flat key discarded reserved_key=%s', key)
            continue
        form_data[key] = value

    if profile.detail_path:
        detail_key = profile.detail_path.split('.')[-1]
        if detail_key in RESERVED_FORM_KEYS:
            logger.info('native payload detail key discarded reserved_key=%s', detail_key)
        else:
            form_data[detail_key] = extract_details(
                payload,
                profile.detail_path,
                profile.detail_item_key,
            )

    return form_data


def resolve_correlation_id(payload: dict, profile) -> str | None:
    """
    依 profile.correlation_id_path 取冪等鍵。
    """
    value = get_path(payload, profile.correlation_id_path)
    if isinstance(value, (dict, list)) or value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > 64:
        return 'h:' + hashlib.sha256(text.encode('utf-8')).hexdigest()[:32]
    return text


def validate_profile_payload(body: dict) -> tuple[bool, str]:
    """
    供 admin CRUD 寫入端驗證，回傳 (是否合法, 錯誤訊息)。
    """
    for field in ('code', 'name', 'source_system', 'correlation_id_path'):
        value = body.get(field)
        if not isinstance(value, str) or not value.strip():
            return False, _('%(field)s 必填', field=field)

    field_map = body.get('field_map')
    if not isinstance(field_map, dict):
        return False, _('field_map 必須為物件')
    for key, value in field_map.items():
        if key not in AXIS_FIELD_KEYS:
            return False, _('field_map 含有不支援的 key: %(key)s', key=key)
        if not isinstance(value, str):
            return False, _('field_map 的 value 必須為字串')

    severity_map = body.get('severity_map')
    if severity_map is not None:
        if not isinstance(severity_map, dict):
            return False, _('severity_map 必須為物件')
        for value in severity_map.values():
            try:
                int(value)
            except (TypeError, ValueError):
                return False, _('severity_map 的 value 必須可轉為整數')

    kv_expansions = body.get('kv_expansions')
    if kv_expansions is not None:
        if not isinstance(kv_expansions, list):
            return False, _('kv_expansions 必須為陣列')
        for idx, item in enumerate(kv_expansions):
            if not isinstance(item, dict):
                return False, _('kv_expansions[%(idx)s] 必須為物件', idx=idx)
            for field in ('path', 'key_field', 'value_field'):
                value = item.get(field)
                if not isinstance(value, str) or not value.strip():
                    return False, _('kv_expansions[%(idx)s].%(field)s 必填',
                                    idx=idx, field=field)

    detail_columns = body.get('detail_columns')
    if detail_columns is not None:
        if not isinstance(detail_columns, list):
            return False, _('detail_columns 必須為陣列')
        for idx, item in enumerate(detail_columns):
            if not isinstance(item, dict):
                return False, _('detail_columns[%(idx)s] 必須為物件', idx=idx)
            key = item.get('key')
            if not isinstance(key, str) or not key.strip():
                return False, _('detail_columns[%(idx)s].key 必填', idx=idx)

    return True, ''
