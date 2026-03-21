"""
Multifaceted FormIO Generator - 多面向規格轉 FormIO Schema

將 multifaceted spec fields (core + facets.formio) 轉換為 FormIO schema，
用於建立 FwFormTemplate。
"""
import logging

logger = logging.getLogger(__name__)


def multifaceted_field_to_formio_component(field):
    """
    單一 multifaceted 欄位 -> FormIO component

    優先使用 facets.formio 的設定，若無則根據 data_class 推導。

    Args:
        field: multifaceted 欄位 dict (含 core + facets)

    Returns:
        dict: FormIO component，若不支援 formio 則回傳 None
    """
    core = field.get('core', {})
    formio_facet = field.get('facets', {}).get('formio', {})
    key = field.get('field_key', '')
    label = field.get('label', '') or key

    if not key:
        return None

    # 決定 component_type
    component_type = formio_facet.get('component_type')
    if not component_type:
        # 從 data_class 推導 fallback
        component_type = _data_class_to_component_type(
            core.get('data_class', 'text')
        )
    if not component_type:
        return None

    comp = {
        'type': component_type,
        'key': key,
        'label': label,
        'input': True,
        'tableView': True,
    }

    # PII 標記
    if core.get('is_pii'):
        comp['properties'] = {'pii': 'true'}

    # 描述
    desc = field.get('description', '')
    if desc:
        comp['description'] = desc

    # 預設值
    default_val = core.get('default_value')
    if default_val is not None:
        comp['defaultValue'] = default_val

    # 驗證 -- 合併 core.required + facets.formio.validate
    validate = {}
    if core.get('required'):
        validate['required'] = True

    facet_validate = formio_facet.get('validate') or {}
    for vk in ('maxLength', 'minLength', 'min', 'max', 'pattern', 'custom'):
        if facet_validate.get(vk) is not None:
            validate[vk] = facet_validate[vk]

    if validate:
        comp['validate'] = validate

    return comp


# data_class -> formio component_type fallback 映射
_DC_TO_FORMIO = {
    'text': 'textfield',
    'text_long': 'textarea',
    'integer': 'number',
    'decimal': 'number',
    'currency': 'currency',
    'boolean': 'checkbox',
    'date': 'day',
    'datetime': 'datetime',
    'email': 'email',
    'phone': 'phoneNumber',
    'url': 'url',
    'enum_single': 'select',
    'enum_multi': 'selectboxes',
    'json': 'textarea',
    'tags': 'tags',
    'signature': 'signature',
}


def _data_class_to_component_type(data_class):
    """data_class -> formio component_type fallback"""
    return _DC_TO_FORMIO.get(data_class, 'textfield')


def _make_form_title_component(title):
    """建立 formTitle 表單名稱元件"""
    return {
        'type': 'formTitle',
        'tag': 'h3',
        'attrs': [
            {'attr': 'style', 'value': 'text-align:center; margin:0 0 0.5rem 0;'},
        ],
        'content': title or '請設定表單名稱',
        'key': 'formTitle',
        'input': False,
        'tableView': False,
    }


def multifaceted_to_formio_schema(fields, form_title=None):
    """
    整個 multifaceted spec fields -> FormIO schema

    Args:
        fields: multifaceted spec fields list
        form_title: 表單標題，加在最前面

    Returns:
        dict: FormIO schema (含 components)
    """
    components = []

    if form_title:
        components.append(_make_form_title_component(form_title))

    for f in (fields or []):
        comp = multifaceted_field_to_formio_component(f)
        if comp:
            components.append(comp)
        else:
            fk = f.get('field_key', '?')
            dc = f.get('core', {}).get('data_class', '?')
            logger.warning(
                'multifaceted field %s (data_class=%s) 無法轉為 FormIO component，已跳過',
                fk, dc,
            )

    return {'components': components}
