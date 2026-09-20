"""Workflow node to Form.io field binding checks for publish-time validation."""
from flask_babel import gettext as _

from .node_handlers.api_key_issue_handler import ApiKeyIssueHandler
from .node_handlers.op_proxy_grant_handler import OpProxyGrantHandler


def _field_type_label(field_type):
    if field_type == 'formPicker':
        return _('API表單選擇')
    if field_type == 'proxyFormPicker':
        return _('代理限定表單選擇')
    if field_type == 'myRolePicker':
        return _('可委任角色選擇')
    if field_type == 'userPicker':
        return _('人員選擇')
    return field_type


def _iter_components(components):
    if not isinstance(components, list):
        return
    for comp in components:
        if not isinstance(comp, dict):
            continue
        yield comp
        for child in _iter_component_children(comp):
            yield child


def _iter_component_children(comp):
    for child in _iter_components(comp.get('components')):
        yield child
    for column in comp.get('columns') or []:
        if isinstance(column, dict):
            for child in _iter_components(column.get('components')):
                yield child
    rows = comp.get('rows')
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, list):
                for cell in row:
                    if isinstance(cell, dict):
                        for child in _iter_components(cell.get('components')):
                            yield child


def _component_index(form_schema):
    return {
        comp.get('key'): comp
        for comp in _iter_components((form_schema or {}).get('components') or [])
        if comp.get('key')
    }


def _node_label(node):
    return node.get('label') or node.get('id') or node.get('type') or ''


def _cfg(node, name, defaults):
    config = node.get('config') or {}
    return config.get(name) or defaults[name]


def _field_type_error(node, config_name, field_key, expected_type):
    return _('節點「%(node_label)s」的 %(config_name)s 指向欄位「%(field_key)s」，'
             '必須是「%(expected)s」元件',
             node_label=_node_label(node),
             config_name=config_name,
             field_key=field_key,
             expected=_field_type_label(expected_type))


def _require_type(errors, components, node, config_name, field_key, expected_type):
    comp = components.get(field_key)
    if not comp or comp.get('type') != expected_type:
        errors.append(_field_type_error(node, config_name, field_key, expected_type))
        return None
    return comp


def check_node_field_bindings(form_schema: dict, graph: dict) -> list[str]:
    """Validate node config field keys against the Form.io schema."""
    errors = []
    components = _component_index(form_schema or {})
    nodes = (graph or {}).get('nodes') or []

    for node in nodes:
        node_type = node.get('type')
        if node_type == 'ApiKeyIssue':
            defaults = ApiKeyIssueHandler.FIELD_DEFAULTS
            beneficiary_field = _cfg(node, 'beneficiary_field', defaults)
            forms_field = _cfg(node, 'forms_field', defaults)
            _require_type(
                errors, components, node, 'beneficiary_field',
                beneficiary_field, 'userPicker')
            form_picker = _require_type(
                errors, components, node, 'forms_field',
                forms_field, 'formPicker')
            if form_picker:
                beneficiary_key = form_picker.get('beneficiaryKey')
                if beneficiary_key is None:
                    beneficiary_key = defaults['beneficiary_field']
                if beneficiary_key != beneficiary_field:
                    errors.append(
                        _('節點「%(node_label)s」的 forms_field 指向欄位「%(field_key)s」，'
                          '但該 API表單選擇的 Key 歸屬人欄位是「%(actual)s」，'
                          '必須等於 beneficiary_field「%(expected)s」',
                          node_label=_node_label(node),
                          field_key=forms_field,
                          actual=beneficiary_key,
                          expected=beneficiary_field)
                    )

        elif node_type == 'OpProxyGrant':
            defaults = OpProxyGrantHandler.FIELD_DEFAULTS
            roles_field = _cfg(node, 'roles_field', defaults)
            delegate_field = _cfg(node, 'delegate_field', defaults)
            forms_field = _cfg(node, 'forms_field', defaults)
            _require_type(
                errors, components, node, 'roles_field',
                roles_field, 'myRolePicker')
            _require_type(
                errors, components, node, 'delegate_field',
                delegate_field, 'userPicker')
            if forms_field in components:
                _require_type(
                    errors, components, node, 'forms_field',
                    forms_field, 'proxyFormPicker')

    return errors
