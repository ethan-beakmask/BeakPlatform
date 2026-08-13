"""
EGRESS-01 form_node 語境接入 (規格: dev-notes/EGRESS_POLICY_SPEC.md)

約定：
- resource_code: fw_form:<form_template_secure_code>（每個表單模板一個資源代碼）
- node_key:      workflow graph 節點 id（FwNodeExecutionQueue.node_id）
- record_sc:     fw_form_instances.secure_code

過濾做兩層：
1. form_data 值：egress_service.apply()（masked 換哨兵、hidden 剔除）
2. Form.io schema components：hidden 從 schema 遞迴剔除；
   masked 保留 component 但設 disabled（值已是哨兵，前端顯示遮罩）
"""
import copy
import logging

logger = logging.getLogger(__name__)

RESOURCE_PREFIX = 'fw_form:'

# apply() 需要 record_sc 欄位產生哨兵；form_data 本身沒有，暫時注入此鍵
_RECORD_SC_KEY = '__egress_record_sc'


def form_resource_code(form_template_secure_code: str) -> str:
    """表單模板的 egress 資源代碼。"""
    return RESOURCE_PREFIX + (form_template_secure_code or '')


def register(egress_service) -> None:
    """模組載入時註冊揭示取值通道（prefix 比對，涵蓋所有表單模板）。"""
    egress_service.register_accessor_prefix(RESOURCE_PREFIX, _reveal_accessor)


def _reveal_accessor(resource_code: str, record_sc: str, field_name: str):
    """
    揭示通道：從表單實例的 form_data 取單一欄位真值。

    租戶隔離：以當前用戶的 org_secure_code 過濾；
    並驗證實例確實屬於 resource_code 所指的表單模板。
    """
    from flask_login import current_user
    from ..models import FwFormInstance

    org_sc = getattr(current_user, 'org_secure_code', None)
    if not org_sc:
        raise KeyError(field_name)

    instance = FwFormInstance.query.filter_by(
        secure_code=record_sc,
        org_secure_code=org_sc,
        is_deleted=False,
    ).first()
    if not instance:
        raise KeyError(field_name)
    if form_resource_code(instance.form_template_secure_code) != resource_code:
        raise KeyError(field_name)

    return (instance.form_data or {}).get(field_name)


def apply_form_egress(form_instance, schema, node_key):
    """
    對 FormAdapter 節點要下發的 (schema, form_data) 套用 form_node 出口政策。

    未設政策時 no-op（schema 原樣、form_data 為淺複本）。

    Returns: (filtered_schema, filtered_form_data)
    """
    from app.services import egress_service

    resource = form_resource_code(form_instance.form_template_secure_code)

    data = dict(form_instance.form_data or {})
    data[_RECORD_SC_KEY] = form_instance.secure_code
    data = egress_service.apply(
        resource, 'form_node', [data],
        record_sc_key=_RECORD_SC_KEY, node_key=node_key,
    )[0]
    data.pop(_RECORD_SC_KEY, None)

    vis_map = egress_service.visibility_map(
        resource, 'form_node', node_key=node_key)
    if vis_map and schema:
        schema = _filter_schema(schema, vis_map)

    return schema, data


def _filter_schema(schema, vis_map):
    """
    依能見度過濾 Form.io schema：
    - hidden: 遞迴剔除該 key 的 component（前端不知欄位存在）
    - masked: 保留 component 但強制 disabled（值為哨兵，不可編輯）

    巢狀容器（components / columns）遞迴處理；
    field_name 對應 component 的 key（datagrid/container 內層欄位
    以其自身 key 比對，同 key 一律套用）。
    """
    schema = copy.deepcopy(schema)

    def process(components):
        result = []
        for comp in components:
            comp = dict(comp)

            key = comp.get('key')
            if key and vis_map.get(key) == 'hidden':
                continue

            if 'components' in comp:
                comp['components'] = process(comp['components'])
            if 'columns' in comp:
                comp['columns'] = [dict(col) for col in comp.get('columns', [])]
                for col in comp['columns']:
                    if 'components' in col:
                        col['components'] = process(col['components'])

            if key and vis_map.get(key) == 'masked':
                comp['disabled'] = True

            result.append(comp)
        return result

    if schema.get('components'):
        schema['components'] = process(schema['components'])
    return schema
