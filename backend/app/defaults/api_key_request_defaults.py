"""
API Key request form/workflow defaults.

出廠表單流程資料值會寫入 DB，不包 gettext。
"""
import logging
from datetime import datetime

from app import db
from app.utils.security import generate_secure_code

logger = logging.getLogger(__name__)


FORM_CODE = 'API_KEY_REQUEST'
WORKFLOW_CODE = 'API_KEY_REQUEST_FLOW'
FORM_NAME = 'API Key 申請單'
WORKFLOW_NAME = 'API Key 申請核發流程'
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

FORM_SCHEMA = {
    'display': 'form',
    'components': [
        {
            'key': 'formTitle',
            'tag': 'h3',
            'type': 'htmlelement',
            'input': False,
            'label': 'HTML',
            'content': 'API Key 申請單',
            'tableView': False,
            'attrs': [{'attr': 'style', 'value': 'text-align:center; margin:0 0 0.5rem 0;'}],
        },
        {
            'key': 'beneficiary',
            'type': 'userPicker',
            'input': True,
            'label': '使用者（Key 歸屬人）',
            'description': '預設為登入者本人。代為申請時改選對象；核發的 Key 歸該對象所有，只有本人領得到金鑰。',
            'tableView': True,
            'validate': {'required': True},
            'validateWhenHidden': False,
        },
        {
            'key': 'authorized_forms',
            'type': 'formPicker',
            'input': True,
            'label': '授權表單',
            'description': '只列出「Key 歸屬人」自己填得到、且已發行的表單。換人時選項會重新計算。',
            'tableView': True,
            'validate': {'required': True},
            'validateWhenHidden': False,
        },
        {
            'key': 'purpose',
            'type': 'textarea',
            'input': True,
            'label': '用途說明',
            'description': '寫明哪一台設備、哪一個系統要使用，以及大約的呼叫頻率。',
            'rows': 3,
            'tableView': True,
            'autoExpand': False,
            'applyMaskOn': 'change',
            'validate': {'required': True, 'minLength': 10},
            'validateWhenHidden': False,
        },
        {
            'key': 'expires_at',
            'type': 'datetime',
            'input': True,
            'label': '有效期限',
            'description': '到期後這把 Key 立即失效，需要重新申請。',
            'tableView': False,
            'enableTime': False,
            'format': 'yyyy-MM-dd',
            'datePicker': {'disableWeekends': False, 'disableWeekdays': False},
            'widget': {
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
            },
            'validate': {'required': True},
            'validateWhenHidden': False,
        },
        {
            'key': 'allowed_ips',
            'type': 'textfield',
            'input': True,
            'label': '來源 IP 限制',
            'description': '選填。可填單一 IP 或 CIDR，多筆以逗號分隔。留空表示不限制來源。',
            'tableView': True,
            'applyMaskOn': 'change',
            'validateWhenHidden': False,
        },
        {
            'key': 'issue_result',
            'type': 'textarea',
            'input': True,
            'label': '核發結果',
            'description': '由流程自動填寫，申請人不需輸入。',
            'rows': 2,
            'disabled': True,
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
    ('group', '__ORG_ROOT__', '全企業群組（含子群組）', True),
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


def get_api_key_issue_icon():
    from app import db

    try:
        from modules.form_workflow.models import WorkflowNodeDefinition
        definition = WorkflowNodeDefinition.query.filter_by(
            node_type='ApiKeyIssue', is_deleted=False).first()
        if definition and definition.icon:
            return definition.icon
    except Exception:
        row = db.session.execute(
            db.text('SELECT icon FROM workflow_node_definitions WHERE node_type=:t'),
            {'t': 'ApiKeyIssue'},
        ).first()
        if row and row[0]:
            return row[0]
    return f'{ICON_BASE}/apikeyissue.svg'


def build_graph(org_admin_role_sc, api_key_issue_icon):
    graph = {
        'nodes': [
            _node('node-Start', 'Start', 'Start', {}, -560, 0),
            _node('node-FormAdapter-approve', 'FormAdapter', '管理員核准', {
                'assignee_type': 'ROLE',
                'assignee_value': org_admin_role_sc,
                'assignee_label': '企業管理員',
                'assignee_list': [],
                'selection_mode': 'single',
                'output_variable': 'approval',
                'allow_comment': True,
                'require_comment': False,
                'use_custom_decisions': True,
                'input_variables': [],
                'decision_options': [
                    {'id': 'opt-approve', 'label': '核准並核發', 'value': 'approved',
                     'style': 'primary', 'target_edges': ['edge-approve']},
                    # 駁回接回同一個 End：本平台的流程一律要走到 End 節點收尾
                    # （2026-08-27 定調），那是「進行中／異常中斷／長時間
                    # 卡住」這類統計的排除條件。設計器面板印的「未配對 =
                    # REJECTED 終態」雖然也是既有機制，但會讓流程不經 End 結束。
                    #
                    # 已知代價：表單中心只在「target_edges 為空且 style=danger」
                    # 時才送 decision='rejected'（fc-approval.js:336-343），所以
                    # 接了邊之後 fw_approval_records.action 會記成 'approved'，
                    # 決策真相只留在流程變數 approval 與簽核意見裡。這是全平台
                    # 通例（OD 的「人工確認」、WF2610385E 的「退回」都一樣），
                    # 不在本流程特案處理。
                    {'id': 'opt-reject', 'label': '駁回', 'value': 'rejected',
                     'style': 'danger', 'target_edges': ['edge-reject']},
                ],
            }, -300, 0, '核發前唯一的把關點：管理員在此看得到 Key 歸屬人與授權表單範圍。'),
            _node('node-ApiKeyIssue', 'ApiKeyIssue', '核發 API Key', {}, -40, -80,
                  '核發前會再驗一次「授權表單 ⊆ 領取人可填範圍」；config 留空即採用預設欄位名。'),
            _node('node-FieldWrite-issued', 'OpFieldWrite', '寫回核發結果', {
                'target_field': 'issue_result',
                'content_type': 'text',
                'content': ('已核發 API Key，識別碼 ${v.apikey_key_id}。'
                            '請 Key 歸屬人本人登入平台，於「個人設定」頁一次性領取金鑰；'
                            '金鑰只顯示一次，逾期未領取需重新申請。'),
            }, 220, -80),
            _node('node-End', 'End', 'End', {'finish_mode': 'detach', 'wait_seconds': 3}, 480, 0),
        ],
        'edges': [
            _edge('edge-start', 'node-Start', 'node-FormAdapter-approve'),
            _edge('edge-approve', 'node-FormAdapter-approve', 'node-ApiKeyIssue', label='核准'),
            _edge('edge-issued', 'node-ApiKeyIssue', 'node-FieldWrite-issued'),
            _edge('edge-issued-end', 'node-FieldWrite-issued', 'node-End'),
            # 駁回不做任何後續動作，只留表單與簽核記錄，直接收到 End
            _edge('edge-reject', 'node-FormAdapter-approve', 'node-End', label='駁回'),
        ],
    }
    for node in graph['nodes']:
        if node['type'] == 'ApiKeyIssue':
            node['icon'] = api_key_issue_icon
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
    # End 只要求至少一個：多個 End 是合法設計（End 是流程級結束，任一到達即結束），
    # 寫死「剛好一個」會擋掉「每條分支各自收尾」這種也合理的畫法。
    if end_count < 1:
        problems.append('流程必須至少有一個 End 節點')

    # 每個決策選項都必須有去向：本平台的流程一律要走到 End 收尾，
    # 未配對的選項在畫布上是懸空的按鈕，看圖的人無從判斷它會怎麼結束。
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
        'org_admin_role_secure_code': None,
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
        from app.models import Role
        from modules.form_workflow.models import (
            FwFormTemplate, FwWorkflowTemplate, FwFormWorkflowMapping,
            FwPublishedFormWorkflow, FwMappingPermission,
        )
    except ImportError:
        logger.warning('API Key request defaults unavailable; skip describe')
        state['skipped'] = True
        state['reason'] = 'module_unavailable'
        return state

    role = Role.query.filter_by(
        org_secure_code=org_secure_code, code='ORG_ADMIN', is_deleted=False).first()
    state['org_admin_role_secure_code'] = role.secure_code if role else None

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
        bool(state['org_admin_role_secure_code']),
        state['form']['exists'],
        state['workflow']['exists'],
        state['workflow']['has_graph'],
        state['workflow']['has_cytoscape'],
        state['mapping']['exists'],
        state['published']['exists'],
        required_permissions.issubset(actual_permissions),
    ])
    return state


def seed_org_api_key_request_flow(org_secure_code, *, force=False) -> dict:
    """為單一企業種入 API Key 申請單鏈路（冪等，不 commit）。呼叫端負責 commit。"""
    if not org_secure_code:
        return {'ok': True, 'skipped': True, 'reason': 'no_org_secure_code'}

    try:
        with db.session.begin_nested():
            try:
                from app.models import Role, User
                from modules.form_workflow.models import (
                    FwFormTemplate, FwWorkflowTemplate, FwFormWorkflowMapping,
                    FwPublishedFormWorkflow, FwMappingPermission,
                )
            except ImportError:
                logger.warning('API Key request defaults unavailable; skip seed')
                return {'ok': True, 'skipped': True, 'reason': 'module_unavailable'}

            db.session.flush()
            org_admin_role = Role.query.filter_by(
                org_secure_code=org_secure_code,
                code='ORG_ADMIN',
                is_deleted=False,
            ).first()
            if not org_admin_role:
                logger.warning(
                    'API Key request defaults skipped org=%s reason=no_org_admin_role',
                    org_secure_code,
                )
                return {'ok': True, 'skipped': True, 'reason': 'no_org_admin_role'}

            graph = build_graph(org_admin_role.secure_code, get_api_key_issue_icon())
            problems = validate_graph(graph)
            if problems:
                logger.error(
                    'API Key request graph invalid org=%s problems=%s',
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
                'description': '申請外部系統對接用的平台 API Key。核准後由系統自動核發，金鑰只有 Key 歸屬人本人能一次性領取。',
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
                    'API Key request form overwritten org=%s secure_code=%s revision=%s',
                    org_secure_code, form_tpl.secure_code, form_tpl.revision,
                )
            elif form_tpl:
                logger.info(
                    'API Key request form exists org=%s secure_code=%s',
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
                    'API Key request form created org=%s secure_code=%s',
                    org_secure_code, form_tpl.secure_code,
                )

            wf_tpl = FwWorkflowTemplate.query.filter_by(
                org_secure_code=org_secure_code, code=WORKFLOW_CODE, is_deleted=False).first()
            workflow_attrs = {
                'name': WORKFLOW_NAME,
                'description': '企業管理員核准後自動核發 API Key 並建立一次性領取憑證，金鑰不經手任何人。',
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
                    'API Key request workflow overwritten org=%s secure_code=%s revision=%s',
                    org_secure_code, wf_tpl.secure_code, wf_tpl.revision,
                )
            elif wf_tpl:
                logger.info(
                    'API Key request workflow exists org=%s secure_code=%s',
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
                    'API Key request workflow created org=%s secure_code=%s',
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
                    'API Key request mapping exists org=%s secure_code=%s',
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
                    'API Key request mapping created org=%s secure_code=%s',
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
                        'API Key request published version exists org=%s secure_code=%s version=%s',
                        org_secure_code, published.secure_code, published.publish_version,
                    )
                else:
                    # 這裡刻意不呼叫 existing.suspend()：那個 model 方法內部有
                    # db.session.commit()，而本函式的契約是「不 commit，由呼叫端
                    # 決定」——建立企業的流程會在中途呼叫它，提早 commit 會把
                    # 尚未完成的企業建立交易切成兩半。以下三行等同 suspend() 的
                    # 內容（含 Archived 檢查），不是重複的死碼。
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
                        'API Key request published new version org=%s secure_code=%s version=%s',
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
                    'API Key request published org=%s secure_code=%s version=%s',
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
                            'API Key request permission updated org=%s permission=%s:%s',
                            org_secure_code, grant_type, grant_target,
                        )
                    else:
                        logger.info(
                            'API Key request permission exists org=%s permission=%s:%s',
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
                    'API Key request permission created org=%s permission=%s:%s',
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
            'API Key request defaults failed org=%s error=%s',
            org_secure_code, exc,
        )
        return {'ok': False, 'reason': 'error', 'error': str(exc)}
