"""
Multifaceted API - Helper Functions
共用輔助函式與 FormIO 轉換邏輯
"""
import json
import logging

from app import db
from app.platform.auth import current_user

logger = logging.getLogger(__name__)


# ── Helper ──

def _get_user_info():
    """取得當前用戶資訊"""
    user_sc = current_user.secure_code
    user_name = (
        getattr(current_user, 'display_name', None)
        or current_user.username
    )
    return user_sc, user_name


def _fields_identical(old_fields, new_fields):
    """比較兩版 fields 是否完全一致"""
    return json.dumps(old_fields, sort_keys=True) == json.dumps(
        new_fields, sort_keys=True
    )


def _merge_formio_into_fields(old_fields, formio_fields):
    """
    將 FormIO 反向轉出的欄位合併到現有 spec fields

    策略：
    - 以 formio_fields 的順序和欄位清單為準（新增、刪除、排序）
    - 已存在的欄位保留 core 和其他 facets（postgresql、excel、csv）
    - formio facet 以最新值覆蓋
    - 新欄位直接採用 formio 反向轉出的結果
    """
    old_map = {}
    for f in (old_fields or []):
        key = f.get('field_key')
        if key:
            old_map[key] = f

    merged = []
    for i, nf in enumerate(formio_fields or []):
        key = nf.get('field_key')
        if not key:
            continue

        old = old_map.get(key)
        if old:
            # 已存在：保留 old 的 core 和其他 facets，更新 formio facet + 排序
            field = json.loads(json.dumps(old))
            field['sort_order'] = i
            field['label'] = nf.get('label') or field.get('label', '')
            field['description'] = nf.get('description') or field.get('description', '')
            # 更新 core.required（FormIO 可能改了）
            if 'core' not in field:
                field['core'] = {}
            field['core']['required'] = nf.get('core', {}).get('required', False)
            # 更新 formio facet
            if 'facets' not in field:
                field['facets'] = {}
            field['facets']['formio'] = nf.get('facets', {}).get('formio', {})
        else:
            # 新欄位：直接用 formio 反向轉出的結果
            field = nf
            field['sort_order'] = i

        merged.append(field)

    return merged


def _sync_form_to_spec(spec, ft_sc, org_sc):
    """從表單模板同步最新 schema 到 spec（合併式，保留其他 facets）"""
    from modules.form_workflow.models import FwFormTemplate
    from modules.spec_formulate.models import FwSpecMultifacetedHistory

    template = FwFormTemplate.query.filter_by(
        secure_code=ft_sc,
        org_secure_code=org_sc,
    ).first()
    if not template or not template.schema:
        return

    formio_fields = _formio_schema_to_multifaceted_fields(template.schema)
    merged = _merge_formio_into_fields(spec.fields, formio_fields)

    # 比較合併結果與現有欄位
    if _fields_identical(spec.fields, merged):
        return

    # 寫入歷史
    history = FwSpecMultifacetedHistory(
        org_secure_code=org_sc,
        spec_secure_code=spec.secure_code,
        version=spec.version,
        fields_snapshot=spec.fields or [],
        active_facets_snapshot=spec.active_facets or [],
        change_description='從表單設計器同步',
        changed_by=current_user.secure_code,
        changed_by_name=(
            getattr(current_user, 'display_name', None)
            or current_user.username
        ),
    )
    db.session.add(history)

    spec.fields = merged
    spec.version = (spec.version or 0) + 1
    if 'formio' not in (spec.active_facets or []):
        spec.active_facets = list(spec.active_facets or []) + ['formio']
    db.session.commit()

    logger.info(
        'Synced form %s -> spec %s (v%d, %d fields)',
        ft_sc, spec.secure_code, spec.version, len(merged),
    )


# FormIO component_type -> data_class 反向映射
_FORMIO_TO_DC = {
    'textfield': 'text',
    'textarea': 'text_long',
    'number': 'integer',
    'currency': 'currency',
    'checkbox': 'boolean',
    'radio': 'enum_single',
    'select': 'enum_single',
    'selectboxes': 'enum_multi',
    'day': 'date',
    'datetime': 'datetime',
    'email': 'email',
    'phoneNumber': 'phone',
    'phone': 'phone',
    'url': 'url',
    'tags': 'tags',
    'signature': 'signature',
    'file': 'binary',
    'password': 'text',
    'hidden': 'text',
}

# 不轉為 spec 欄位的 component types（佈局/裝飾用）
_FORMIO_SKIP_TYPES = {
    'htmlelement', 'content', 'button', 'panel', 'columns',
    'fieldset', 'tabs', 'well', 'table',
}


def _formio_schema_to_multifaceted_fields(schema):
    """
    從 FormIO schema 反向轉為 multifaceted spec fields

    遞迴處理巢狀 components（panel/columns 等容器內的欄位也提取）。
    """
    if not schema:
        return []

    components = schema.get('components', [])
    fields = []
    _extract_components(components, fields, 0)
    return fields


def _extract_components(components, fields, sort_start):
    """遞迴提取 FormIO components 為 multifaceted fields"""
    for comp in (components or []):
        ctype = comp.get('type', '')

        # 容器型：遞迴進入子 components
        if ctype in ('panel', 'fieldset', 'well', 'tabs'):
            _extract_components(
                comp.get('components', []), fields, len(fields)
            )
            continue
        if ctype == 'columns':
            for col in (comp.get('columns') or []):
                _extract_components(
                    col.get('components', []), fields, len(fields)
                )
            continue
        if ctype == 'table':
            for row_list in (comp.get('rows') or []):
                for cell in (row_list or []):
                    _extract_components(
                        cell.get('components', []), fields, len(fields)
                    )
            continue

        # 跳過裝飾/佈局元件
        if ctype in _FORMIO_SKIP_TYPES:
            continue

        key = comp.get('key', '')
        if not key:
            continue

        label = comp.get('label', '') or key
        validate = comp.get('validate') or {}
        properties = comp.get('properties') or {}
        dc = _FORMIO_TO_DC.get(ctype, 'text')

        # 帶小數驗證的 number -> decimal
        if ctype == 'number' and validate.get('step') and '.' in str(validate['step']):
            dc = 'decimal'

        field = {
            'field_key': key,
            'label': label,
            'description': comp.get('description', '') or '',
            'sort_order': len(fields),
            'core': {
                'data_class': dc,
                'required': bool(validate.get('required')),
                'is_pii': properties.get('pii') == 'true',
                'default_value': comp.get('defaultValue'),
            },
            'facets': {
                'formio': {
                    'component_type': ctype,
                },
            },
        }

        # 保留 formio 驗證設定
        formio_validate = {}
        for vk in ('maxLength', 'minLength', 'min', 'max', 'pattern', 'custom'):
            if validate.get(vk) is not None:
                formio_validate[vk] = validate[vk]
        if formio_validate:
            field['facets']['formio']['validate'] = formio_validate

        fields.append(field)
