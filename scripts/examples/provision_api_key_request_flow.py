#!/usr/bin/env python3
"""
建置 API Key 申請單與核發流程。

用途
    在指定企業內建立「API Key 申請單」的完整鏈路：

      1. 表單模板 API_KEY_REQUEST
      2. 流程模板 API_KEY_REQUEST_FLOW
      3. 表單流程配對並發行
      4. 三筆配對填寫權限，讓企業成員、企業管理員、有群組的外部廠商可申請

    腳本冪等，重跑不會新增重複資料；只做建置，不做任何刪除。

用法
    cd /opt/BeakPlatform-dev
    set -a && source .env && set +a
    venv/bin/python scripts/examples/provision_api_key_request_flow.py --org beluga.com --apply

參數
    --apply      實際寫入資料庫；省略時只做檢查與預演
    --org <值>   企業 secure_code 或 domain_name；實際建置時必填
    --force      表單／流程已存在時覆寫內容、bump revision 並重新發行
"""
import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'backend'))
sys.path.insert(0, _REPO_ROOT)

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


def log(msg):
    print(msg, flush=True)


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


def get_api_key_issue_icon(db):
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
                    # （Ethan 2026-08-27 定調），那是「進行中／異常中斷／長時間
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


def resolve_org(Organization, org_arg):
    org = Organization.query.filter_by(
        secure_code=org_arg, is_deleted=False).first()
    if not org:
        org = Organization.query.filter_by(
            domain_name=org_arg, is_deleted=False).first()
    if org:
        return org

    log(f'找不到企業：{org_arg}')
    log('可用企業：')
    for item in Organization.query.filter_by(is_deleted=False).order_by(Organization.id).all():
        log(f'  {item.secure_code} | {item.domain_name or ""} | {item.name}')
    raise SystemExit('請用 --org 指定上列企業的 secure_code 或 domain_name')


def list_available_orgs(Organization):
    log('可用企業：')
    for item in Organization.query.filter_by(is_deleted=False).order_by(Organization.id).all():
        log(f'  {item.secure_code} | {item.domain_name or ""} | {item.name}')


def get_org_admin_role(Role, org_sc):
    role = Role.query.filter_by(
        org_secure_code=org_sc, code='ORG_ADMIN', is_deleted=False).first()
    if not role:
        raise SystemExit('該企業缺少 ORG_ADMIN 角色，無法指定核准人')
    return role


def warn_if_no_org_admin_users(User, UserRoleAssignment, org_sc, role_sc):
    count = (
        User.query
        .join(UserRoleAssignment,
              UserRoleAssignment.user_secure_code == User.secure_code)
        .filter(UserRoleAssignment.org_secure_code == org_sc,
                UserRoleAssignment.role_secure_code == role_sc,
                UserRoleAssignment.is_deleted.is_(False),
                User.org_secure_code == org_sc,
                User.is_deleted.is_(False),
                User.is_active.is_(True))
        .count()
    )
    if count == 0:
        log('  警告：ORG_ADMIN 角色底下沒有有效帳號，核准關卡會解析出空的簽核人清單，單子會卡住。')


def get_publisher(User, org_sc):
    return User.query.filter_by(
        org_secure_code=org_sc, user_type='ORG_ADMIN',
        is_deleted=False, is_active=True).first()


def ensure_form_template(FwFormTemplate, org_sc, apply, force):
    from app.utils.security import generate_secure_code

    tpl = FwFormTemplate.query.filter_by(
        org_secure_code=org_sc, code=FORM_CODE, is_deleted=False).first()
    if tpl and not force:
        log(f'  表單 {FORM_CODE} 已存在：{tpl.secure_code}')
        return tpl

    if not apply:
        action = '覆寫' if tpl else '建立'
        log(f'  [預演] 會{action}表單 {FORM_CODE}')
        return None

    attrs = {
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
    if tpl:
        for key, value in attrs.items():
            setattr(tpl, key, value)
        tpl.revision = (tpl.revision or 0) + 1
        log(f'  已覆寫表單 {FORM_CODE}：{tpl.secure_code}（revision -> {tpl.revision}）')
        return tpl

    tpl = FwFormTemplate(
        secure_code=generate_secure_code(),
        org_secure_code=org_sc,
        code=FORM_CODE,
        version='AA',
        revision=1,
        **attrs,
    )
    from app import db
    db.session.add(tpl)
    db.session.flush()
    log(f'  已建立表單 {FORM_CODE}：{tpl.secure_code}')
    return tpl


def ensure_workflow_template(FwWorkflowTemplate, org_sc, graph, apply, force):
    from app.utils.security import generate_secure_code

    tpl = FwWorkflowTemplate.query.filter_by(
        org_secure_code=org_sc, code=WORKFLOW_CODE, is_deleted=False).first()
    if tpl and not force:
        log(f'  流程 {WORKFLOW_CODE} 已存在：{tpl.secure_code}')
        return tpl

    if not apply:
        action = '覆寫' if tpl else '建立'
        log(f"  [預演] 會{action}流程 {WORKFLOW_CODE}"
            f"（{len(graph['nodes'])} 節點 / {len(graph['edges'])} 連線）")
        return None

    attrs = {
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
    if tpl:
        for key, value in attrs.items():
            setattr(tpl, key, value)
        tpl.revision = (tpl.revision or 0) + 1
        log(f'  已覆寫流程 {WORKFLOW_CODE}：{tpl.secure_code}（revision -> {tpl.revision}）')
        return tpl

    tpl = FwWorkflowTemplate(
        secure_code=generate_secure_code(),
        org_secure_code=org_sc,
        code=WORKFLOW_CODE,
        version='AA',
        revision=1,
        **attrs,
    )
    from app import db
    db.session.add(tpl)
    db.session.flush()
    log(f'  已建立流程 {WORKFLOW_CODE}：{tpl.secure_code}')
    return tpl


def ensure_mapping_and_publish(FwFormWorkflowMapping, FwPublishedFormWorkflow,
                               org_sc, form_tpl, wf_tpl, publisher, apply):
    from app.utils.security import generate_secure_code
    from app import db

    if not apply or not form_tpl or not wf_tpl:
        log('  [預演] 會建立表單流程配對並發行')
        return None, None

    mapping = FwFormWorkflowMapping.query.filter_by(
        org_secure_code=org_sc,
        form_template_secure_code=form_tpl.secure_code,
        is_deleted=False,
    ).first()

    if mapping:
        mapping.workflow_template_id = wf_tpl.id
        mapping.workflow_template_secure_code = wf_tpl.secure_code
        mapping.workflow_template_code = wf_tpl.code
        mapping.workflow_template_version = wf_tpl.version
        mapping.is_active = True
        log(f'  配對已存在，更新為指向 {wf_tpl.code}：{mapping.secure_code}')
    else:
        mapping = FwFormWorkflowMapping(
            secure_code=generate_secure_code(),
            org_secure_code=org_sc,
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
        log(f'  已建立配對：{mapping.secure_code}')

    existing = FwPublishedFormWorkflow.query.filter_by(
        org_secure_code=org_sc,
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
            log(f'  發行版本未變更，沿用 v{existing.publish_version}：{existing.secure_code}')
            return mapping, existing
        existing.suspend(suspended_by=publisher.secure_code if publisher else None)
        log(f'  已停用舊發行版本 v{existing.publish_version}')

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
    log(f'  已發行 v{published.publish_version}：{published.secure_code}')
    return mapping, published


def ensure_mapping_permissions(FwMappingPermission, org_sc, mapping, apply):
    from app.utils.security import generate_secure_code
    from app import db

    specs = [
        ('role', 'EMPLOYEE', '企業成員', False),
        ('role', 'ORG_ADMIN', '企業管理員', False),
        ('group', '__ORG_ROOT__', '全企業群組（含子群組）', True),
    ]
    if not apply or not mapping:
        for grant_type, grant_target, grant_target_name, include_children in specs:
            log(f'  [預演] 會確保填寫權限 {grant_type}:{grant_target}（{grant_target_name}）')
        return

    for grant_type, grant_target, grant_target_name, include_children in specs:
        exists = FwMappingPermission.query.filter_by(
            org_secure_code=org_sc,
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
                log(f'  已更新填寫權限 {grant_type}:{grant_target}')
            else:
                log(f'  填寫權限已存在 {grant_type}:{grant_target}')
            continue

        db.session.add(FwMappingPermission(
            secure_code=generate_secure_code(),
            org_secure_code=org_sc,
            mapping_secure_code=mapping.secure_code,
            grant_type=grant_type,
            grant_target=grant_target,
            grant_target_name=grant_target_name,
            include_children=include_children,
        ))
        log(f'  已建立填寫權限 {grant_type}:{grant_target}')


def main():
    parser = argparse.ArgumentParser(
        description='建置 API Key 申請單與核發流程',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('--apply', action='store_true',
                        help='實際寫入資料庫；省略時只做檢查與預演')
    parser.add_argument('--org', default=None,
                        help='企業 secure_code 或 domain_name；實際建置時必填')
    parser.add_argument('--force', action='store_true',
                        help='表單／流程已存在時覆寫內容、bump revision 並重新發行')
    args = parser.parse_args()

    from app import create_app, db
    from app.models import Organization, Role, User, UserRoleAssignment
    from modules.form_workflow.models import (
        FwFormTemplate, FwWorkflowTemplate, FwFormWorkflowMapping,
        FwPublishedFormWorkflow, FwMappingPermission,
    )

    app = create_app('development')
    with app.app_context():
        if not args.org:
            if args.apply:
                raise SystemExit('實際寫入資料庫時必須指定 --org')
            log('未指定 --org，預演模式只列出可用企業，不寫入資料庫。')
            list_available_orgs(Organization)
            db.session.rollback()
            return

        org = resolve_org(Organization, args.org)
        org_sc = org.secure_code
        log(f'企業：{org.secure_code} | {org.domain_name or ""} | {org.name}')

        org_admin_role = get_org_admin_role(Role, org_sc)
        log(f'企業管理員角色：{org_admin_role.secure_code}')
        warn_if_no_org_admin_users(User, UserRoleAssignment, org_sc, org_admin_role.secure_code)

        publisher = get_publisher(User, org_sc)
        if publisher:
            log(f'發行者：{publisher.secure_code}（{publisher.display_name or publisher.username}）')
        else:
            log('  警告：找不到有效的 ORG_ADMIN 帳號，發行紀錄將不帶發行者。')

        graph = build_graph(org_admin_role.secure_code, get_api_key_issue_icon(db))
        problems = validate_graph(graph)
        if problems:
            log('graph 結構檢查未通過：')
            for problem in problems:
                log(f'  - {problem}')
            raise SystemExit('graph 結構檢查未通過，中止')
        log(f"graph 結構檢查通過：{len(graph['nodes'])} 節點 / {len(graph['edges'])} 連線")

        log('\n[1/4] 表單模板')
        form_tpl = ensure_form_template(FwFormTemplate, org_sc, args.apply, args.force)

        log('\n[2/4] 流程模板')
        wf_tpl = ensure_workflow_template(FwWorkflowTemplate, org_sc, graph, args.apply, args.force)

        log('\n[3/4] 配對與發行')
        mapping, published = ensure_mapping_and_publish(
            FwFormWorkflowMapping, FwPublishedFormWorkflow,
            org_sc, form_tpl, wf_tpl, publisher, args.apply)

        log('\n[4/4] 填寫權限')
        ensure_mapping_permissions(FwMappingPermission, org_sc, mapping, args.apply)

        if args.apply:
            db.session.commit()
            log('\n已 commit')
        else:
            db.session.rollback()
            log('\n預演模式，未寫入任何資料。加上 --apply 才會實際建置')
            log('提醒：外部廠商必須至少屬於一個群組才吃得到這條規則；沒有群組成員身分的外部帳號仍然看不到這張表單。')
            return

        log('\n' + '=' * 72)
        log('建置完成，識別碼如下')
        log('=' * 72)
        log(f'表單模板 secure_code / code：{form_tpl.secure_code} / {form_tpl.code}')
        log(f'流程模板 secure_code / code：{wf_tpl.secure_code} / {wf_tpl.code}')
        log(f'配對 secure_code：{mapping.secure_code}')
        log(f'發行版本 secure_code / publish_version：{published.secure_code} / {published.publish_version}')
        log('以下網址都要加 nginx 前綴 /beakplatform：')
        log(f'  表單設計器：/forms/templates/{form_tpl.secure_code}')
        log(f'  流程設計器：/forms/workflows/{wf_tpl.secure_code}')
        log('  表單中心：/forms/center')
        log('提醒：外部廠商必須至少屬於一個群組才吃得到這條規則；沒有群組成員身分的外部帳號仍然看不到這張表單。')


if __name__ == '__main__':
    main()
