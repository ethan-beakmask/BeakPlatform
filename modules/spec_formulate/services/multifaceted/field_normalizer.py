"""
Field Normalizer - 欄位定義驗證與正規化

負責驗證 fields JSONB 的結構正確性，
以及正規化輸入資料（trim、型別轉換、預設值填充）。
"""
import re

from .data_class_registry import DATA_CLASS_REGISTRY, ALL_FACETS

# field_key 格式：英文字母/數字/底線，首字元為英文
FIELD_KEY_PATTERN = re.compile(r'^[a-zA-Z][a-zA-Z0-9_]*$')


class FieldValidationError(Exception):
    """欄位驗證錯誤"""
    def __init__(self, field_key, message):
        self.field_key = field_key
        self.message = message
        super().__init__(f'[{field_key}] {message}')


def validate_field(field, index=0):
    """
    驗證單一欄位定義

    Args:
        field: 欄位定義 dict
        index: 欄位在陣列中的位置（錯誤訊息用）

    Returns:
        list[str]: 警告訊息（非阻斷）

    Raises:
        FieldValidationError: 欄位結構不合法
    """
    warnings = []
    fk = field.get('field_key', f'(index={index})')

    # field_key 必填且格式正確
    if not field.get('field_key'):
        raise FieldValidationError(fk, 'field_key 必填')
    if not FIELD_KEY_PATTERN.match(field['field_key']):
        raise FieldValidationError(
            fk,
            'field_key 格式錯誤：僅允許英文字母、數字、底線，且首字元為英文'
        )

    # label 必填
    if not field.get('label', '').strip():
        raise FieldValidationError(fk, 'label 必填')

    # core 區塊
    core = field.get('core')
    if not core or not isinstance(core, dict):
        raise FieldValidationError(fk, 'core 區塊必填')

    # data_class 必須是已知值
    dc = core.get('data_class')
    if not dc or dc not in DATA_CLASS_REGISTRY:
        known = ', '.join(DATA_CLASS_REGISTRY.keys())
        raise FieldValidationError(
            fk,
            f'未知的 data_class: {dc}（可用值: {known}）'
        )

    # facets 區塊驗證
    facets = field.get('facets', {})
    if not isinstance(facets, dict):
        raise FieldValidationError(fk, 'facets 必須是 dict')

    for facet_name, facet_val in facets.items():
        if facet_name not in ALL_FACETS:
            warnings.append(f'[{fk}] 未知的 facet: {facet_name}')
            continue
        if not isinstance(facet_val, dict):
            raise FieldValidationError(fk, f'facets.{facet_name} 必須是 dict')

        # 檢查 data_class 是否支援此 facet
        reg = DATA_CLASS_REGISTRY[dc]['facets'].get(facet_name, {})
        if not reg.get('supported', False):
            warnings.append(
                f'[{fk}] data_class={dc} 不支援 {facet_name}，'
                f'facet 資料將保留但不生效'
            )

    return warnings


def normalize_field(field):
    """
    正規化單一欄位定義

    - 字串 trim
    - 布林轉換
    - 缺失的 core 欄位補預設值
    - facets 保持原樣（不自動填充）

    Returns:
        dict: 正規化後的欄位
    """
    result = {}

    # 基礎欄位
    result['field_key'] = str(field.get('field_key', '')).strip()
    result['label'] = str(field.get('label', '')).strip()
    result['sort_order'] = int(field.get('sort_order', 0))
    result['description'] = str(field.get('description', '')).strip()

    # core 區塊
    core = field.get('core', {})
    if not isinstance(core, dict):
        core = {}

    result['core'] = {
        'data_class': str(core.get('data_class', 'text')).strip(),
        'required': bool(core.get('required', False)),
        'is_pii': bool(core.get('is_pii', False)),
        'default_value': core.get('default_value'),
    }

    # facets 區塊（保持原樣，不自動填充）
    facets = field.get('facets', {})
    if not isinstance(facets, dict):
        facets = {}
    result['facets'] = facets

    return result


def normalize_fields(fields):
    """
    正規化整個欄位陣列

    Returns:
        tuple: (normalized_fields, warnings, errors)
            - normalized_fields: 正規化後的欄位列表
            - warnings: 非阻斷警告列表
            - errors: 阻斷錯誤列表
    """
    if not isinstance(fields, list):
        return [], [], ['fields 必須是陣列']

    normalized = []
    all_warnings = []
    all_errors = []
    seen_keys = set()

    for i, field in enumerate(fields):
        if not isinstance(field, dict):
            all_errors.append(f'fields[{i}] 不是有效的物件')
            continue

        # 正規化
        norm = normalize_field(field)

        # 跳過空白列（field_key 為空）
        if not norm['field_key']:
            continue

        # field_key 重複檢查
        if norm['field_key'] in seen_keys:
            all_errors.append(
                f'field_key 重複: {norm["field_key"]}'
            )
            continue
        seen_keys.add(norm['field_key'])

        # 驗證
        try:
            warnings = validate_field(norm, index=i)
            all_warnings.extend(warnings)
        except FieldValidationError as e:
            all_errors.append(str(e))
            continue

        # 重設 sort_order
        norm['sort_order'] = len(normalized)
        normalized.append(norm)

    return normalized, all_warnings, all_errors


def compute_diff(old_fields, new_fields):
    """
    計算兩個版本的欄位差異

    Returns:
        dict: {
            'added': [{'field_key': ..., 'label': ...}],
            'removed': [{'field_key': ..., 'label': ...}],
            'modified': [{'field_key': ..., 'changes': [...]}],
        }
    """
    old_map = {f['field_key']: f for f in (old_fields or []) if f.get('field_key')}
    new_map = {f['field_key']: f for f in (new_fields or []) if f.get('field_key')}

    old_keys = set(old_map.keys())
    new_keys = set(new_map.keys())

    added = [
        {'field_key': k, 'label': new_map[k].get('label', '')}
        for k in sorted(new_keys - old_keys)
    ]
    removed = [
        {'field_key': k, 'label': old_map[k].get('label', '')}
        for k in sorted(old_keys - new_keys)
    ]

    modified = []
    for k in sorted(old_keys & new_keys):
        changes = _diff_field(old_map[k], new_map[k])
        if changes:
            modified.append({'field_key': k, 'changes': changes})

    return {'added': added, 'removed': removed, 'modified': modified}


def _diff_field(old_f, new_f):
    """比較兩個欄位的差異"""
    changes = []

    # 比較基礎欄位
    for key in ('label', 'description'):
        old_val = old_f.get(key, '')
        new_val = new_f.get(key, '')
        if old_val != new_val:
            changes.append({
                'path': key,
                'old': old_val,
                'new': new_val,
            })

    # 比較 core
    old_core = old_f.get('core', {})
    new_core = new_f.get('core', {})
    for key in ('data_class', 'required', 'is_pii', 'default_value'):
        old_val = old_core.get(key)
        new_val = new_core.get(key)
        if old_val != new_val:
            changes.append({
                'path': f'core.{key}',
                'old': old_val,
                'new': new_val,
            })

    # 比較 facets（有的 facet 才比）
    old_facets = old_f.get('facets', {})
    new_facets = new_f.get('facets', {})
    all_facet_names = set(list(old_facets.keys()) + list(new_facets.keys()))

    for fn in sorted(all_facet_names):
        if fn not in old_facets:
            changes.append({
                'path': f'facets.{fn}',
                'old': None,
                'new': '(added)',
            })
        elif fn not in new_facets:
            changes.append({
                'path': f'facets.{fn}',
                'old': '(removed)',
                'new': None,
            })
        else:
            # 深層比較 facet 內容
            old_fv = old_facets[fn]
            new_fv = new_facets[fn]
            if old_fv != new_fv:
                changes.append({
                    'path': f'facets.{fn}',
                    'old': old_fv,
                    'new': new_fv,
                })

    return changes
