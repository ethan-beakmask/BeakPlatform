"""
Spec Generator — 雙向轉換器

核心功能：
1. spec field -> FormIO component（正向）
2. FormIO component -> spec field（反向）
3. 完整 schema 雙向轉換
4. apply spec to existing schema（Replace 模式）
"""
import logging
from ..sql_sync.converter import FORMIO_TO_PG, SKIP_TYPES, GRID_TYPES

logger = logging.getLogger(__name__)


def derive_pg_type(formio_type, constraints=None):
    """
    從 formio_type 推導 pg_type

    Args:
        formio_type: form.io 元件類型
        constraints: 約束條件 dict

    Returns:
        str: PostgreSQL 型別字串
    """
    if formio_type in GRID_TYPES:
        return 'JSONB'

    pg_type = FORMIO_TO_PG.get(formio_type, 'TEXT')

    # 根據 constraints 微調
    if constraints and formio_type == 'textfield':
        max_len = constraints.get('maxLength')
        if max_len and isinstance(max_len, int):
            pg_type = f'VARCHAR({max_len})'

    return pg_type


def spec_field_to_formio_component(field_spec):
    """
    單一 spec 欄位 -> FormIO component

    Args:
        field_spec: spec 欄位 dict

    Returns:
        dict: FormIO component
    """
    ftype = field_spec.get('formio_type', 'textfield')
    key = field_spec.get('field_key', '')
    label = field_spec.get('label', key)
    constraints = field_spec.get('constraints') or {}

    comp = {
        'type': ftype,
        'key': key,
        'label': label,
        'input': True,
        'tableView': True,
    }

    # PII 標記
    if field_spec.get('is_pii'):
        comp['properties'] = {'pii': 'true'}

    # 描述
    desc = field_spec.get('description', '')
    if desc:
        comp['description'] = desc

    # 預設值
    default_val = field_spec.get('default_value')
    if default_val is not None:
        comp['defaultValue'] = default_val

    # 驗證
    validate = {}
    if constraints.get('required'):
        validate['required'] = True
    if constraints.get('maxLength') is not None:
        validate['maxLength'] = constraints['maxLength']
    if constraints.get('minLength') is not None:
        validate['minLength'] = constraints['minLength']
    if constraints.get('min') is not None:
        validate['min'] = constraints['min']
    if constraints.get('max') is not None:
        validate['max'] = constraints['max']
    if constraints.get('pattern'):
        validate['pattern'] = constraints['pattern']
    if constraints.get('customValidation'):
        validate['custom'] = constraints['customValidation']
    if validate:
        comp['validate'] = validate

    # select / radio: options
    options = field_spec.get('options')
    if options and ftype in ('select', 'radio', 'selectboxes'):
        if ftype == 'select':
            comp['data'] = {
                'values': [
                    {'label': o.get('label', ''), 'value': o.get('value', '')}
                    for o in options
                ]
            }
        elif ftype in ('radio', 'selectboxes'):
            comp['values'] = [
                {'label': o.get('label', ''), 'value': o.get('value', '')}
                for o in options
            ]

    # datagrid / editgrid: 子欄位
    if ftype in GRID_TYPES:
        children = field_spec.get('grid_children') or []
        comp['components'] = [
            spec_field_to_formio_component(child)
            for child in children
        ]

    return comp


def spec_to_formio_schema(fields):
    """
    整個 spec fields -> FormIO schema dict

    Args:
        fields: spec fields list

    Returns:
        dict: FormIO schema (含 components)
    """
    components = []
    for f in (fields or []):
        comp = spec_field_to_formio_component(f)
        components.append(comp)

    return {'components': components}


def formio_component_to_spec_field(comp, sort_order=0):
    """
    FormIO component -> spec field（反向）

    Args:
        comp: FormIO component dict
        sort_order: 排序位置

    Returns:
        dict: spec field
    """
    ftype = comp.get('type', 'textfield')
    key = comp.get('key', '')
    label = comp.get('label', key)
    validate = comp.get('validate') or {}
    properties = comp.get('properties') or {}

    constraints = {
        'required': validate.get('required', False),
        'maxLength': validate.get('maxLength'),
        'minLength': validate.get('minLength'),
        'min': validate.get('min'),
        'max': validate.get('max'),
        'pattern': validate.get('pattern'),
        'customValidation': validate.get('custom'),
    }

    is_pii = str(properties.get('pii', '')).lower() in ('true', '1')

    pg_type = derive_pg_type(ftype, constraints)

    # options
    options = None
    if ftype == 'select':
        data = comp.get('data') or {}
        values = data.get('values') or []
        if values:
            options = [
                {'label': v.get('label', ''), 'value': v.get('value', '')}
                for v in values
            ]
    elif ftype in ('radio', 'selectboxes'):
        values = comp.get('values') or []
        if values:
            options = [
                {'label': v.get('label', ''), 'value': v.get('value', '')}
                for v in values
            ]

    # grid children
    grid_children = None
    if ftype in GRID_TYPES:
        children_comps = comp.get('components') or []
        grid_children = []
        for i, child in enumerate(children_comps):
            child_type = child.get('type', '')
            if child_type in SKIP_TYPES:
                continue
            grid_children.append(formio_component_to_spec_field(child, i))

    return {
        'field_key': key,
        'label': label,
        'formio_type': ftype,
        'pg_type': pg_type,
        'constraints': constraints,
        'is_pii': is_pii,
        'description': comp.get('description', ''),
        'default_value': comp.get('defaultValue'),
        'options': options,
        'grid_children': grid_children,
        'sort_order': sort_order,
    }


def formio_schema_to_spec_fields(form_schema):
    """
    FormIO schema -> spec fields list（反向）

    遞迴處理 components，跳過 layout 元件，只抽取 data fields。
    與 converter.py 的 schema_to_columns 邏輯對齊。

    Args:
        form_schema: FormIO schema dict

    Returns:
        list: spec fields list
    """
    fields = []
    seen_keys = set()
    sort_counter = [0]

    def _extract(components):
        for comp in (components or []):
            comp_type = comp.get('type', '')

            # datagrid/editgrid: 完整轉換含子欄位
            if comp_type in GRID_TYPES:
                key = comp.get('key')
                if key and key not in seen_keys:
                    seen_keys.add(key)
                    field = formio_component_to_spec_field(comp, sort_counter[0])
                    fields.append(field)
                    sort_counter[0] += 1
                continue

            # layout 容器: 遞迴
            if comp_type in SKIP_TYPES or (
                comp_type not in FORMIO_TO_PG and 'components' in comp
            ):
                _extract(comp.get('components', []))
                for col in comp.get('columns', []):
                    if isinstance(col, dict):
                        _extract(col.get('components', []))
                continue

            key = comp.get('key')
            if not key or key in seen_keys:
                continue
            if comp_type in SKIP_TYPES:
                continue

            seen_keys.add(key)
            field = formio_component_to_spec_field(comp, sort_counter[0])
            fields.append(field)
            sort_counter[0] += 1

    _extract(form_schema.get('components', []))
    return fields


def apply_spec_to_existing_schema(spec_fields, existing_schema):
    """
    Replace 模式：保留 layout 容器，data fields 用 spec 重建

    策略：
    1. 掃描 existing_schema，識別 layout 容器（panel, columns 等）
    2. 收集所有非 layout 元件的位置
    3. 移除所有舊 data fields
    4. 用 spec 生成新 data fields，插入最頂層

    Args:
        spec_fields: spec fields list
        existing_schema: 現有 FormIO schema dict

    Returns:
        dict: 新的 FormIO schema
    """
    import copy

    schema = copy.deepcopy(existing_schema or {'components': []})
    old_components = schema.get('components', [])

    # 保留 layout 和非資料元件（htmlelement, content, button 等）
    layout_components = []
    for comp in old_components:
        comp_type = comp.get('type', '')
        if comp_type in SKIP_TYPES:
            layout_components.append(comp)

    # 用 spec 生成新 data fields
    new_data_components = []
    for f in (spec_fields or []):
        comp = spec_field_to_formio_component(f)
        new_data_components.append(comp)

    # 組合：layout 在前，data fields 在後
    schema['components'] = layout_components + new_data_components

    return schema
