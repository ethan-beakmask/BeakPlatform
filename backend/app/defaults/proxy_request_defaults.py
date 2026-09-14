"""
Proxy request form/workflow defaults.

出廠表單流程資料值會寫入 DB，不包 gettext。
"""
import logging
from datetime import datetime

from app import db
from app.utils.security import generate_secure_code

logger = logging.getLogger(__name__)


FORM_CODE = 'PROXY_REQUEST'
WORKFLOW_CODE = 'PROXY_REQUEST_FLOW'
FORM_NAME = '代理指定申請單'
WORKFLOW_NAME = '代理指定同意流程'
CATEGORY_NAME = '其他'
CATEGORY_SECURE_CODE = 'SYS_CAT_OTHER'
ICON_BASE = '/static/modules/form_workflow/icons/workflow'
EDGE_STYLE = {
    'width': 1,
    'line-color': 'rgb(149,165,166)',
    'line-style': 'solid',
    'arrow-scale': 1,
    'curve-style': 'straight',
    'target-arrow-color': 'rgb(149,165,166)',
    'target-arrow-shape': 'triangle',
}

_DATE_WIDGET = {
    'type': 'calendar',
    'format': 'yyyy-MM-dd',
    'enableTime': False,
    'displayInTimezone': 'viewer',
    'locale': 'zh-tw',
    'useLocaleSettings': False,
    'allowInput': True,
    'mode': 'single',
    'hourIncrement': 1,
    'minuteIncrement': 1,
    'time_24hr': True,
    'saveAs': 'text',
}

FORM_SCHEMA = {
    'display': 'form',
    'components': [
        {
            'key': 'formTitle',
            'tag': 'h3',
            'type': 'htmlelement',
            'input': False,
            'label': 'HTML',
            'content': '代理指定申請單',
            'tableView': False,
            'attrs': [{'attr': 'style', 'value': 'text-align:center; margin:0 0 0.5rem 0;'}],
        },
        {
            'key': 'delegate',
            'type': 'userPicker',
            'input': True,
            'label': '代理人',
            'description': '請選擇要代你處理的同事。送出後由對方確認是否接受。',
            'defaultToCurrentUser': False,
            'tableView': True,
            'validate': {'required': True},
            'validateWhenHidden': False,
        },
        {
            'key': 'proxy_roles',
            'type': 'myRolePicker',
            'input': True,
            'label': '要委任的角色',
            'description': '只列出你目前正式持有的角色。代理人在效期內視同持有這些角色。',
            'tableView': True,
            'validate': {'required': True},
            'validateWhenHidden': False,
        },
        {
            'key': 'effective_from',
            'type': 'datetime',
            'input': True,
            'label': '生效開始',
            'tableView': False,
            'enableTime': False,
            'format': 'yyyy-MM-dd',
            'datePicker': {'disableWeekends': False, 'disableWeekdays': False},
            'widget': dict(_DATE_WIDGET),
            'validate': {'required': True},
            'validateWhenHidden': False,
        },
        {
            'key': 'effective_until',
            'type': 'datetime',
            'input': True,
            'label': '生效結束',
            'tableView': False,
            'enableTime': False,
            'format': 'yyyy-MM-dd',
            'datePicker': {'disableWeekends': False, 'disableWeekdays': False},
            'widget': dict(_DATE_WIDGET),
            'validate': {'required': True},
            'validateWhenHidden': False,
        },
        {
            'key': 'authorized_forms',
            'type': 'formPicker',
            'input': True,
            'label': '限定表單',
            'description': '留空表示代理人可以簽你這些角色的所有單。選了就只限這幾張表單。',
            'beneficiaryKey': '',
            'tableView': True,
            'validateWhenHidden': False,
        },
        {
            'key': 'reason',
            'type': 'textarea',
            'input': True,
            'label': '事由',
            'rows': 3,
            'tableView': True,
            'autoExpand': False,
            'applyMaskOn': 'change',
            'validate': {'required': True, 'minLength': 5},
            'validateWhenHidden': False,
        },
        {
            'key': 'grant_result',
            'type': 'textarea',
            'input': True,
            'label': '處理結果',
            'description': '由流程自動填寫，申請人不需輸入。',
            'disabled': True,
            'rows': 2,
            'tableView': False,
            'autoExpand': False,
            'validateWhenHidden': False,
        },
    ],
}

FORM_BUILDER_CONFIG = {
    'formTheme': 'parallel-label',
    'formWidth': 900,
    'background': None,
    'fileUploadEnabled': False,
    'placeholderToLabel': True,
}

MAPPING_PERMISSION_SPECS = [
    ('role', 'EMPLOYEE', '企業成員', False),
    ('role', 'ORG_ADMIN', '企業管理員', False),
]


def _node(node_id, node_type, label, config=None, x=0, y=0, description=''):
    return {
        'id': node_id,
        'type': node_type,
        'label': label,
        'icon': f'{ICON_BASE}/{node_type.lower()}.svg',
        'config': config or {},
        'position': {'x': x, 'y': y},
        'description': description,
    }


def _edge(edge_id, source, target, label=''):
    return {
        'id': edge_id,
        'label': label,
        'style': dict(EDGE_STYLE),
        'source': source,
        'target': target,
        'hasRelays': False,
    }


def get_op_proxy_grant_icon():
    from app import db

    try:
        from modules.form_workflow.models import WorkflowNodeDefinition
        definition = WorkflowNodeDefinition.query.filter_by(
            node_type='OpProxyGrant', is_deleted=False).first()
        if definition and definition.icon:
            return definition.icon
    except Exception:
        row = db.session.execute(
            db.text('SELECT icon FROM workflow_node_definitions WHERE node_type=:t'),
            {'t': 'OpProxyGrant'},
        ).first()
        if row and row[0]:
            return row[0]
    return f'{ICON_BASE}/opproxygrant.svg'


def build_graph(op_proxy_grant_icon):
    graph = {
        'nodes': [
            _node('node-Start', 'Start', 'Start', {}, -560, 0),
            _node('node-FieldRead-delegate', 'OpFieldRead', '讀取代理人', {
                'fields': ['delegate'],
            }, -300, 0),
            _node('node-FormAdapter-consent', 'FormAdapter', '代理人確認', {
                'assignee_type': 'DYNAMIC',
                # OpFieldRead 會把每個欄位寫成兩個流程變數：
                # f'{form_code}_{field}' 與 f'{field}'。而它的 form_code 取的是
                # form_instance.form_template_secure_code（fieldread_handler.py:38），
                # 不是表單模板的 code，所以帶前綴的那個名字是 '<模板 sc>_delegate'、
                # 每個企業都不一樣，出廠 graph 寫不出來。這裡只能用不帶前綴的簡單名。
                # 流程變數的作用域是單一流程實例，本流程只有這張表單的欄位，不會撞名。
                'assignee_value': 'delegate',
                'assignee_label': '指定的代理人',
                'assignee_list': [],
                'selection_mode': 'single',
                'output_variable': 'consent',
                'allow_comment': True,
                'require_comment': False,
                'use_custom_decisions': True,
                'input_variables': [],
                'decision_options': [
                    {'id': 'opt-approve', 'label': '同意代理', 'value': 'approved',
                     'style': 'primary', 'target_edges': ['edge-approve']},
                    {'id': 'opt-reject', 'label': '拒絕', 'value': 'rejected',
                     'style': 'danger', 'target_edges': ['edge-reject']},
                ],
            }, -40, 0, '簽核者是申請單上指定的代理人本人；同意後系統才會建立代理指派。'),
            _node('node-OpProxyGrant', 'OpProxyGrant', '建立代理指派', {}, 220, -80,
                  '依申請單內容建立 proxy 角色指派；config 留空即採用預設欄位名。'),
            _node('node-FieldWrite-granted', 'OpFieldWrite', '寫回授出結果', {
                'target_field': 'grant_result',
                'content_type': 'text',
                'content': ('${v.proxy_delegate_name} 已同意代理，共建立 ${v.proxy_count} 筆代理指派：'
                            '${v.proxy_roles}，效期 ${v.proxy_from} 至 ${v.proxy_until}。'),
            }, 480, -80),
            _node('node-FieldWrite-rejected', 'OpFieldWrite', '寫回拒絕結果', {
                'target_field': 'grant_result',
                'content_type': 'text',
                'content': '代理人未同意這次委任，沒有建立任何代理指派。',
            }, 220, 100),
            _node('node-End', 'End', 'End', {'finish_mode': 'detach', 'wait_seconds': 3}, 740, 0),
        ],
        'edges': [
            _edge('edge-start', 'node-Start', 'node-FieldRead-delegate'),
            _edge('edge-read-consent', 'node-FieldRead-delegate', 'node-FormAdapter-consent'),
            _edge('edge-approve', 'node-FormAdapter-consent', 'node-OpProxyGrant', label='同意代理'),
            _edge('edge-granted', 'node-OpProxyGrant', 'node-FieldWrite-granted'),
            _edge('edge-granted-end', 'node-FieldWrite-granted', 'node-End'),
            _edge('edge-reject', 'node-FormAdapter-consent', 'node-FieldWrite-rejected', label='拒絕'),
            _edge('edge-rejected-end', 'node-FieldWrite-rejected', 'node-End'),
        ],
    }
    for node in graph['nodes']:
        if node['type'] == 'OpProxyGrant':
            node['icon'] = op_proxy_grant_icon
    return graph


def validate_graph(graph):
    problems = []
    nodes = graph.get('nodes') or []
    edges = graph.get('edges') or []
    node_ids = [node.get('id') for node in nodes]
    edge_ids = [edge.get('id') for edge in edges]
    node_id_set = set(node_ids)
    edge_id_set = set(edge_ids)

    if len(node_ids) != len(node_id_set):
        problems.append('節點 id 不唯一')
    if len(edge_ids) != len(edge_id_set):
        problems.append('邊 id 不唯一')

    for edge in edges:
        if edge.get('source') not in node_id_set:
            problems.append(f"邊 {edge.get('id')} 的 source 不存在：{edge.get('source')}")
        if edge.get('target') not in node_id_set:
            problems.append(f"邊 {edge.get('id')} 的 target 不存在：{edge.get('target')}")

    for node in nodes:
        if node.get('type') == 'FormAdapter':
            for option in (node.get('config') or {}).get('decision_options') or []:
                for edge_id in option.get('target_edges') or []:
                    if edge_id not in edge_id_set:
                        problems.append(
                            f"FormAdapter {node.get('id')} decision option {option.get('id')} "
                            f"指向不存在的邊：{edge_id}"
                        )

    outgoing = {}
    for edge in edges:
        outgoing.setdefault(edge.get('source'), 0)
        outgoing[edge.get('source')] += 1
    for node in nodes:
        if node.get('type') != 'End' and outgoing.get(node.get('id'), 0) < 1:
            problems.append(f"節點 {node.get('id')} 沒有出邊")

    start_count = sum(1 for node in nodes if node.get('type') == 'Start')
    end_count = sum(1 for node in nodes if node.get('type') == 'End')
    if start_count != 1:
        problems.append(f'Start 節點數量必須剛好為 1，目前為 {start_count}')
    if end_count < 1:
        problems.append('流程必須至少有一個 End 節點')

    for node in nodes:
        if node.get('type') != 'FormAdapter':
            continue
        for option in (node.get('config') or {}).get('decision_options') or []:
            if not (option.get('target_edges') or []):
                problems.append(
                    f"FormAdapter {node.get('id')} 的決策選項 "
                    f"{option.get('label') or option.get('id')} 沒有配對任何出線"
                )
    return problems


def _get_publisher(User, org_sc):
    return User.query.filter_by(
        org_secure_code=org_sc, user_type='ORG_ADMIN',
        is_deleted=False, is_active=True).first()


def _describe_empty(org_secure_code):
    return {
        'org_secure_code': org_secure_code,
        'form': {'exists': False, 'secure_code': None, 'version': None, 'revision': None},
        'workflow': {
            'exists': False, 'secure_code': None, 'version': None, 'revision': None,
            'has_graph': False, 'has_cytoscape': False,
        },
        'mapping': {'exists': False, 'secure_code': None},
        'published': {'exists': False, 'secure_code': None, 'publish_version': None},
        'permissions': [],
        'complete': False,
    }


def describe_org_state(org_secure_code) -> dict:
    """回報該企業目前的建置狀態，供預演與驗收使用。不寫入任何資料。"""
    state = _describe_empty(org_secure_code)
    if not org_secure_code:
        return state

    try:
        from modules.form_workflow.models import (
            FwFormTemplate, FwWorkflowTemplate, FwFormWorkflowMapping,
            FwPublishedFormWorkflow, FwMappingPermission,
        )
    except ImportError:
        logger.warning('Proxy request defaults unavailable; skip describe')
        state['skipped'] = True
        state['reason'] = 'module_unavailable'
        return state

    form_tpl = FwFormTemplate.query.filter_by(
        org_secure_code=org_secure_code, code=FORM_CODE, is_deleted=False).first()
    if form_tpl:
        state['form'] = {
            'exists': True,
            'secure_code': form_tpl.secure_code,
            'version': form_tpl.version,
            'revision': form_tpl.revision,
        }

    wf_tpl = FwWorkflowTemplate.query.filter_by(
        org_secure_code=org_secure_code, code=WORKFLOW_CODE, is_deleted=False).first()
    if wf_tpl:
        state['workflow'] = {
            'exists': True,
            'secure_code': wf_tpl.secure_code,
            'version': wf_tpl.version,
            'revision': wf_tpl.revision,
            'has_graph': bool(wf_tpl.graph),
            'has_cytoscape': bool(wf_tpl.cytoscape_config),
        }

    mapping = None
    if form_tpl:
        mapping = FwFormWorkflowMapping.query.filter_by(
            org_secure_code=org_secure_code,
            form_template_secure_code=form_tpl.secure_code,
            is_deleted=False,
        ).first()
    if mapping:
        state['mapping'] = {'exists': True, 'secure_code': mapping.secure_code}
        published = FwPublishedFormWorkflow.query.filter_by(
            org_secure_code=org_secure_code,
            source_mapping_secure_code=mapping.secure_code,
            status='Published',
            is_deleted=False,
        ).order_by(FwPublishedFormWorkflow.publish_version.desc()).first()
        if published:
            state['published'] = {
                'exists': True,
                'secure_code': published.secure_code,
                'publish_version': published.publish_version,
            }
        permissions = FwMappingPermission.query.filter_by(
            org_secure_code=org_secure_code,
            mapping_secure_code=mapping.secure_code,
            is_deleted=False,
        ).order_by(FwMappingPermission.id).all()
        state['permissions'] = [
            {
                'grant_type': item.grant_type,
                'grant_target': item.grant_target,
                'grant_target_name': item.grant_target_name,
                'include_children': item.include_children,
            }
            for item in permissions
        ]

    required_permissions = {
        (grant_type, grant_target, grant_target_name, include_children)
        for grant_type, grant_target, grant_target_name, include_children in MAPPING_PERMISSION_SPECS
    }
    actual_permissions = {
        (
            item['grant_type'], item['grant_target'],
            item['grant_target_name'], item['include_children'],
        )
        for item in state['permissions']
    }
    state['complete'] = all([
        state['form']['exists'],
        state['workflow']['exists'],
        state['workflow']['has_graph'],
        state['workflow']['has_cytoscape'],
        state['mapping']['exists'],
        state['published']['exists'],
        required_permissions.issubset(actual_permissions),
    ])
    return state


def seed_org_proxy_request_flow(org_secure_code, *, force=False) -> dict:
    """為單一企業種入代理指定申請鏈路（冪等，不 commit）。呼叫端負責 commit。"""
    if not org_secure_code:
        return {'ok': True, 'skipped': True, 'reason': 'no_org_secure_code'}

    try:
        with db.session.begin_nested():
            try:
                from app.models import User
                from modules.form_workflow.models import (
                    FwFormTemplate, FwWorkflowTemplate, FwFormWorkflowMapping,
                    FwPublishedFormWorkflow, FwMappingPermission,
                )
            except ImportError:
                logger.warning('Proxy request defaults unavailable; skip seed')
                return {'ok': True, 'skipped': True, 'reason': 'module_unavailable'}

            graph = build_graph(get_op_proxy_grant_icon())
            problems = validate_graph(graph)
            if problems:
                logger.error(
                    'Proxy request graph invalid org=%s problems=%s',
                    org_secure_code, problems,
                )
                return {'ok': False, 'reason': 'invalid_graph', 'problems': problems}

            created = {
                'form': False,
                'workflow': False,
                'mapping': False,
                'published': False,
                'permissions': [],
            }

            form_tpl = FwFormTemplate.query.filter_by(
                org_secure_code=org_secure_code, code=FORM_CODE, is_deleted=False).first()
            form_attrs = {
                'name': FORM_NAME,
                'description': '成員送出代理指定申請，由代理人本人同意後，系統自動建立 proxy 角色指派。',
                'category': CATEGORY_NAME,
                'category_secure_code': CATEGORY_SECURE_CODE,
                'schema': FORM_SCHEMA,
                'builder_config': FORM_BUILDER_CONFIG,
                'is_published': False,
                'is_active': True,
                'is_protected': False,
                'permission_type': 'org',
            }
            if form_tpl and force:
                for key, value in form_attrs.items():
                    setattr(form_tpl, key, value)
                form_tpl.revision = (form_tpl.revision or 0) + 1
                logger.info(
                    'Proxy request form overwritten org=%s secure_code=%s revision=%s',
                    org_secure_code, form_tpl.secure_code, form_tpl.revision,
                )
            elif form_tpl:
                logger.info(
                    'Proxy request form exists org=%s secure_code=%s',
                    org_secure_code, form_tpl.secure_code,
                )
            else:
                form_tpl = FwFormTemplate(
                    secure_code=generate_secure_code(),
                    org_secure_code=org_secure_code,
                    code=FORM_CODE,
                    version='AA',
                    revision=1,
                    **form_attrs,
                )
                db.session.add(form_tpl)
                db.session.flush()
                created['form'] = True
                logger.info(
                    'Proxy request form created org=%s secure_code=%s',
                    org_secure_code, form_tpl.secure_code,
                )

            wf_tpl = FwWorkflowTemplate.query.filter_by(
                org_secure_code=org_secure_code, code=WORKFLOW_CODE, is_deleted=False).first()
            workflow_attrs = {
                'name': WORKFLOW_NAME,
                'description': '指定的代理人同意後，由系統以申請人身分授出 proxy 角色指派；拒絕時不建立任何指派。',
                'category': CATEGORY_NAME,
                'category_secure_code': CATEGORY_SECURE_CODE,
                'graph': graph,
                'cytoscape_config': graph,
                'is_published': False,
                'is_active': True,
                'is_protected': False,
                'permission_type': 'org',
                'is_subprocess': False,
            }
            if wf_tpl and force:
                for key, value in workflow_attrs.items():
                    setattr(wf_tpl, key, value)
                wf_tpl.revision = (wf_tpl.revision or 0) + 1
                logger.info(
                    'Proxy request workflow overwritten org=%s secure_code=%s revision=%s',
                    org_secure_code, wf_tpl.secure_code, wf_tpl.revision,
                )
            elif wf_tpl:
                logger.info(
                    'Proxy request workflow exists org=%s secure_code=%s',
                    org_secure_code, wf_tpl.secure_code,
                )
            else:
                wf_tpl = FwWorkflowTemplate(
                    secure_code=generate_secure_code(),
                    org_secure_code=org_secure_code,
                    code=WORKFLOW_CODE,
                    version='AA',
                    revision=1,
                    **workflow_attrs,
                )
                db.session.add(wf_tpl)
                db.session.flush()
                created['workflow'] = True
                logger.info(
                    'Proxy request workflow created org=%s secure_code=%s',
                    org_secure_code, wf_tpl.secure_code,
                )

            mapping = FwFormWorkflowMapping.query.filter_by(
                org_secure_code=org_secure_code,
                form_template_secure_code=form_tpl.secure_code,
                is_deleted=False,
            ).first()
            if mapping:
                mapping.workflow_template_id = wf_tpl.id
                mapping.workflow_template_secure_code = wf_tpl.secure_code
                mapping.workflow_template_code = wf_tpl.code
                mapping.workflow_template_version = wf_tpl.version
                mapping.is_active = True
                logger.info(
                    'Proxy request mapping exists org=%s secure_code=%s',
                    org_secure_code, mapping.secure_code,
                )
            else:
                mapping = FwFormWorkflowMapping(
                    secure_code=generate_secure_code(),
                    org_secure_code=org_secure_code,
                    form_template_id=form_tpl.id,
                    form_template_secure_code=form_tpl.secure_code,
                    form_template_code=form_tpl.code,
                    form_template_version=form_tpl.version,
                    workflow_template_id=wf_tpl.id,
                    workflow_template_secure_code=wf_tpl.secure_code,
                    workflow_template_code=wf_tpl.code,
                    workflow_template_version=wf_tpl.version,
                    is_active=True,
                    is_published=False,
                    priority=0,
                    description=f'{form_tpl.name} + {wf_tpl.name}',
                )
                db.session.add(mapping)
                db.session.flush()
                created['mapping'] = True
                logger.info(
                    'Proxy request mapping created org=%s secure_code=%s',
                    org_secure_code, mapping.secure_code,
                )

            publisher = _get_publisher(User, org_secure_code)
            existing = FwPublishedFormWorkflow.query.filter_by(
                org_secure_code=org_secure_code,
                source_mapping_secure_code=mapping.secure_code,
                status='Published',
                is_deleted=False,
            ).first()
            if existing:
                same = (existing.source_form_version == form_tpl.version
                        and existing.source_form_revision == form_tpl.revision
                        and existing.source_workflow_version == wf_tpl.version
                        and existing.source_workflow_revision == wf_tpl.revision)
                if same:
                    published = existing
                    logger.info(
                        'Proxy request published version exists org=%s secure_code=%s version=%s',
                        org_secure_code, published.secure_code, published.publish_version,
                    )
                else:
                    if existing.status == 'Archived':
                        raise ValueError('已封存的版本無法停用')
                    existing.status = 'Suspended'
                    existing.suspended_at = datetime.utcnow()
                    existing.suspended_by = publisher.secure_code if publisher else None
                    published = FwPublishedFormWorkflow.create_from_mapping(
                        mapping=mapping,
                        form_template=form_tpl,
                        workflow_template=wf_tpl,
                        published_by=publisher.secure_code if publisher else None,
                        published_by_name=(publisher.display_name or publisher.username) if publisher else None,
                    )
                    mapping.is_published = True
                    mapping.form_template_version = form_tpl.version
                    mapping.workflow_template_version = wf_tpl.version
                    db.session.add(published)
                    db.session.flush()
                    created['published'] = True
                    logger.info(
                        'Proxy request published new version org=%s secure_code=%s version=%s',
                        org_secure_code, published.secure_code, published.publish_version,
                    )
            else:
                published = FwPublishedFormWorkflow.create_from_mapping(
                    mapping=mapping,
                    form_template=form_tpl,
                    workflow_template=wf_tpl,
                    published_by=publisher.secure_code if publisher else None,
                    published_by_name=(publisher.display_name or publisher.username) if publisher else None,
                )
                mapping.is_published = True
                mapping.form_template_version = form_tpl.version
                mapping.workflow_template_version = wf_tpl.version
                db.session.add(published)
                db.session.flush()
                created['published'] = True
                logger.info(
                    'Proxy request published org=%s secure_code=%s version=%s',
                    org_secure_code, published.secure_code, published.publish_version,
                )

            for grant_type, grant_target, grant_target_name, include_children in MAPPING_PERMISSION_SPECS:
                exists = FwMappingPermission.query.filter_by(
                    org_secure_code=org_secure_code,
                    mapping_secure_code=mapping.secure_code,
                    grant_type=grant_type,
                    grant_target=grant_target,
                    is_deleted=False,
                ).first()
                if exists:
                    if (exists.grant_target_name != grant_target_name
                            or exists.include_children != include_children):
                        exists.grant_target_name = grant_target_name
                        exists.include_children = include_children
                        logger.info(
                            'Proxy request permission updated org=%s permission=%s:%s',
                            org_secure_code, grant_type, grant_target,
                        )
                    else:
                        logger.info(
                            'Proxy request permission exists org=%s permission=%s:%s',
                            org_secure_code, grant_type, grant_target,
                        )
                    continue

                db.session.add(FwMappingPermission(
                    secure_code=generate_secure_code(),
                    org_secure_code=org_secure_code,
                    mapping_secure_code=mapping.secure_code,
                    grant_type=grant_type,
                    grant_target=grant_target,
                    grant_target_name=grant_target_name,
                    include_children=include_children,
                ))
                created['permissions'].append(f'{grant_type}:{grant_target}')
                logger.info(
                    'Proxy request permission created org=%s permission=%s:%s',
                    org_secure_code, grant_type, grant_target,
                )

            db.session.flush()
            return {
                'ok': True,
                'skipped': False,
                'form_secure_code': form_tpl.secure_code,
                'workflow_secure_code': wf_tpl.secure_code,
                'mapping_secure_code': mapping.secure_code,
                'published_secure_code': published.secure_code,
                'publish_version': published.publish_version,
                'created': created,
            }
    except Exception as exc:
        logger.exception(
            'Proxy request defaults failed org=%s error=%s',
            org_secure_code, exc,
        )
        return {'ok': False, 'reason': 'error', 'error': str(exc)}
