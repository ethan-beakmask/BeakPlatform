#!/usr/bin/env python3
"""
從零建置單一企業的 Open Defense 事件受理鏈路。

用途
    讓「尚未有任何資安受理設定」的企業一次具備可收案的最小鏈路：

      資安分類（secure_code 以 CAT_SECURITY_ 開頭）
        -> 資安事件處置表單模板
        -> 最小人工簽核流程模板
        -> 表單流程配對 + Published 快照
        -> 啟用中的 catch-all 事件路由規則
        -> od_intake API Key

    建完後即可用 scripts/examples/od_intake_send_event.py 送事件，案件會出現在
    「開放防禦 / 資安案件處置中心」。

重要提醒
    本腳本建立的 od_form_template_mappings 是啟用中的 catch-all 規則：
    event_class=NULL 且 match_rules=[]，任何 event_class 都會收進同一張表單。
    這是為了讓空白企業能立即驗證收案；正式環境請依組織政策改成分流規則。

用法
    cd <BeakPlatform 專案目錄>
    set -a && source .env && set +a
    venv/bin/python scripts/examples/provision_od_intake_for_org.py --org lion.com --apply

參數
    --org <值>            必填。可填企業 secure_code 或 domain_name（例 lion.com）
    --apply               實際寫入資料庫；省略時只做檢查並印出將要做的事
    --force               表單／流程已存在時覆寫內容並重新發行
    --source-system <值>  可重複指定，寫進 API Key 白名單；預設 elk
    --skip-api-key        不建立 API Key
    --assignee-role <值>  簽核角色 code；預設 SECURITY_STAFF
"""
import argparse
import copy
import os
import secrets
import sys
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'backend'))
sys.path.insert(0, _REPO_ROOT)

SECURITY_CATEGORY_PREFIX = 'CAT_SECURITY_'
FORM_CODE = 'SEC_INCIDENT_RESPONSE'
FORM_NAME = '資安事件處置'
FORM_DESCRIPTION = 'Open Defense 事件受理後建立的資安案件處置表單'
WORKFLOW_CODE = 'SEC_INCIDENT_FLOW'
WORKFLOW_NAME = '資安事件處置流程'
WORKFLOW_DESCRIPTION = 'Open Defense 最小可用人工簽核流程：Start -> 資安人員簽核 -> End'
DEFAULT_ASSIGNEE_ROLE = 'SECURITY_STAFF'
API_KEY_NAME = 'Open Defense intake (provisioned)'

SECURITY_FORM_SCHEMA = {
    "display": "form",
    "components": [
        {
            "key": "p_event",
            "type": "panel",
            "input": False,
            "label": "事件資訊",
            "title": "事件資訊",
            "tableView": False,
            "components": [
                {"key": "finding_title", "type": "textfield", "input": True, "label": "事件標題", "tableView": True},
                {"key": "finding_summary", "type": "textarea", "input": True, "label": "事件摘要", "tableView": True},
                {"key": "event_class", "type": "textfield", "input": True, "label": "事件類別", "tableView": True},
                {"key": "source_system", "type": "textfield", "input": True, "label": "偵測來源", "tableView": True},
                {"key": "severity_id", "type": "number", "input": True, "label": "嚴重度 (OCSF 1-5)", "delimiter": False, "tableView": True},
                {"key": "confidence", "type": "number", "input": True, "label": "信心度", "delimiter": False, "tableView": True},
                {"key": "occurred_at", "type": "textfield", "input": True, "label": "發生時間", "tableView": True},
                {"key": "correlation_id", "type": "textfield", "input": True, "label": "事件關聯 ID", "tableView": True},
            ],
        },
        {
            "key": "p_actor",
            "type": "panel",
            "input": False,
            "label": "攻擊者",
            "title": "攻擊者",
            "tableView": False,
            "components": [
                {"key": "actor_ip", "type": "textfield", "input": True, "label": "攻擊者 IP", "tableView": True},
                {"key": "actor_asn", "type": "textfield", "input": True, "label": "ASN", "tableView": True},
                {"key": "actor_country", "type": "textfield", "input": True, "label": "國別", "tableView": True},
                {"key": "actor_user_agent", "type": "textfield", "input": True, "label": "User-Agent", "tableView": True},
                {"key": "actor_xff", "type": "textfield", "input": True, "label": "X-Forwarded-For 原文", "tableView": True},
            ],
        },
        {
            "key": "p_target",
            "type": "panel",
            "input": False,
            "label": "受攻擊目標",
            "title": "受攻擊目標",
            "tableView": False,
            "components": [
                {"key": "target_host", "type": "textfield", "input": True, "label": "目標主機", "tableView": True},
                {"key": "target_url", "type": "textfield", "input": True, "label": "目標 URL", "tableView": True},
                {"key": "target_service", "type": "textfield", "input": True, "label": "目標服務", "tableView": True},
            ],
        },
        {
            "key": "p_detect",
            "type": "panel",
            "input": False,
            "label": "偵測規則",
            "title": "偵測規則",
            "tableView": False,
            "components": [
                {"key": "finding_rule_id", "type": "textfield", "input": True, "label": "規則 ID", "tableView": True},
                {"key": "finding_rule_set", "type": "textfield", "input": True, "label": "規則集", "tableView": True},
                {"key": "detector_hint_action", "type": "textfield", "input": True, "label": "偵測端建議動作", "tableView": True},
                {"key": "detector_hint_ttl_sec", "type": "number", "input": True, "label": "建議 TTL (秒)", "delimiter": False, "tableView": True},
            ],
        },
        {
            "key": "p_intel",
            "type": "panel",
            "input": False,
            "label": "情報彙整（系統自動填寫）",
            "title": "情報彙整（系統自動填寫）",
            "tableView": False,
            "components": [
                {"key": "risk_score", "type": "number", "input": True, "label": "風險分數 (0-100)", "delimiter": False, "tableView": True},
                {"key": "recommended_action", "type": "textfield", "input": True, "label": "建議處置", "tableView": True},
                {"key": "od_event_count", "type": "number", "input": True, "label": "本案件聚合事件數", "delimiter": False, "tableView": True},
                {"key": "od_repeat_count", "type": "number", "input": True, "label": "24 小時內同源事件數", "delimiter": False, "tableView": True},
                {"key": "od_history_block_count", "type": "number", "input": True, "label": "該 IP 歷史封鎖次數", "delimiter": False, "tableView": True},
                {"key": "intel_summary", "type": "textarea", "input": True, "label": "情報摘要", "tableView": True},
                {"key": "od_first_seen", "type": "textfield", "input": True, "label": "首次出現", "tableView": True},
                {"key": "od_last_seen", "type": "textfield", "input": True, "label": "最近出現", "tableView": True},
            ],
        },
    ],
}


def log(msg):
    print(msg, flush=True)


def build_workflow_graph(assignee_role_sc):
    icon_base = '/static/modules/form_workflow/icons/workflow'
    edge_style = {
        "width": 1,
        "line-color": "rgb(149,165,166)",
        "line-style": "solid",
        "arrow-scale": 1,
        "curve-style": "straight",
        "target-arrow-color": "rgb(149,165,166)",
        "target-arrow-shape": "triangle",
    }
    return {
        "nodes": [
            {
                "id": "node-Start",
                "icon": f"{icon_base}/start.svg",
                "type": "Start",
                "label": "Start",
                "config": {},
                "position": {"x": -400, "y": 0},
                "description": "",
            },
            {
                "id": "node-Review",
                "icon": f"{icon_base}/formadapter.svg",
                "type": "FormAdapter",
                "label": "資安人員簽核",
                "config": {
                    "allow_comment": True,
                    "assignee_list": [],
                    "assignee_type": "ROLE",
                    "assignee_label": "資安人員",
                    "assignee_value": assignee_role_sc,
                    "selection_mode": "single",
                    "input_variables": [],
                    "output_variable": "soc_decision",
                    "require_comment": True,
                    "decision_options": [
                        {
                            "id": "opt-block",
                            "label": "封鎖攻擊來源",
                            "style": "danger",
                            "value": "block",
                            "target_edges": ["edge-done"],
                        },
                        {
                            "id": "opt-allow",
                            "label": "放行（可接受風險）",
                            "style": "default",
                            "value": "allow",
                            "target_edges": ["edge-done"],
                        },
                        {
                            "id": "opt-fp",
                            "label": "誤判結案",
                            "style": "danger",
                            "value": "false_positive",
                            "target_edges": ["edge-done"],
                        },
                    ],
                    "min_comment_length": 2,
                    "use_custom_decisions": True,
                },
                "position": {"x": 0, "y": 0},
                "description": "",
            },
            {
                "id": "node-End",
                "icon": f"{icon_base}/end.svg",
                "type": "End",
                "label": "End",
                "config": {},
                "position": {"x": 400, "y": 0},
                "description": "",
            },
        ],
        "edges": [
            {
                "id": "edge-1",
                "label": "",
                "source": "node-Start",
                "target": "node-Review",
                "hasRelays": False,
                "style": dict(edge_style),
            },
            {
                "id": "edge-done",
                "label": "",
                "source": "node-Review",
                "target": "node-End",
                "hasRelays": False,
                "style": dict(edge_style),
            },
        ],
    }


def resolve_org(Organization, org_arg):
    org = Organization.query.filter(
        Organization.is_deleted.is_(False),
        ((Organization.secure_code == org_arg) | (Organization.domain_name == org_arg)),
    ).first()
    if org:
        return org

    available = Organization.query.filter_by(is_deleted=False).order_by(Organization.domain_name.asc()).all()
    lines = ['找不到企業：' + org_arg, '可用企業：']
    for item in available:
        lines.append(f'  - {item.domain_name} / {item.secure_code} / {item.name}')
    raise SystemExit('\n'.join(lines))


def ensure_assignee_role(Role, org_sc, role_code):
    role = Role.query.filter_by(
        org_secure_code=org_sc,
        code=role_code,
        is_deleted=False,
        is_active=True,
    ).first()
    if not role:
        raise SystemExit(
            f'企業 {org_sc} 找不到啟用中的簽核角色 {role_code}。'
            '該企業可能尚未採購開放防禦模組，請先確認模組合約與預設角色種子資料。'
        )
    return role


def get_publisher(User, org_sc):
    publisher = User.query.filter_by(
        org_secure_code=org_sc,
        user_type='ORG_ADMIN',
        is_deleted=False,
        is_active=True,
    ).order_by(User.id.asc()).first()
    if not publisher:
        raise SystemExit(f'企業 {org_sc} 找不到啟用中的 ORG_ADMIN，無法發行流程')
    return publisher


def ensure_security_category(db, FwCategory, org_sc, apply):
    category = FwCategory.query.filter(
        FwCategory.org_secure_code == org_sc,
        FwCategory.secure_code.like(f'{SECURITY_CATEGORY_PREFIX}%'),
        FwCategory.is_deleted.is_(False),
    ).order_by(FwCategory.id.asc()).first()
    if category:
        log(f'  資安分類已存在：{category.secure_code}（{category.name}）')
        return category

    if not apply:
        log(f'  [預演] 會建立資安分類 secure_code={SECURITY_CATEGORY_PREFIX}<8 hex>')
        return None

    category = FwCategory(
        secure_code=SECURITY_CATEGORY_PREFIX + secrets.token_hex(4),
        org_secure_code=org_sc,
        name='資安案件',
        description='Open Defense 資安案件分類',
        display_order=0,
        is_system=False,
        show_in_form_design=True,
        show_in_workflow_design=True,
        show_in_form_center=False,
        parent_secure_code=None,
    )
    db.session.add(category)
    db.session.flush()
    log(f'  已建立資安分類：{category.secure_code}')
    return category


def ensure_form_template(db, FwFormTemplate, org_sc, category, apply, force):
    from app.utils.security import generate_secure_code

    tpl = FwFormTemplate.query.filter_by(
        org_secure_code=org_sc,
        code=FORM_CODE,
        is_deleted=False,
    ).first()
    if tpl and not force:
        log(f'  表單模板已存在：{tpl.secure_code}（revision {tpl.revision}）')
        return tpl

    if not apply:
        action = '覆寫' if tpl else '建立'
        log(f'  [預演] 會{action}表單模板 {FORM_CODE}（內嵌資安事件 schema）')
        return None

    if tpl:
        tpl.name = FORM_NAME
        tpl.description = FORM_DESCRIPTION
        tpl.category = category.name
        tpl.category_secure_code = category.secure_code
        tpl.schema = copy.deepcopy(SECURITY_FORM_SCHEMA)
        tpl.builder_config = {}
        tpl.version = tpl.version or 'AA'
        tpl.revision = (tpl.revision or 0) + 1
        tpl.is_active = True
        tpl.is_protected = False
        tpl.permission_type = 'org'
        log(f'  已覆寫表單模板：{tpl.secure_code}（revision -> {tpl.revision}）')
        return tpl

    tpl = FwFormTemplate(
        secure_code=generate_secure_code(),
        org_secure_code=org_sc,
        code=FORM_CODE,
        name=FORM_NAME,
        description=FORM_DESCRIPTION,
        category=category.name,
        category_secure_code=category.secure_code,
        schema=copy.deepcopy(SECURITY_FORM_SCHEMA),
        builder_config={},
        version='AA',
        revision=1,
        is_published=False,
        is_active=True,
        is_protected=False,
        permission_type='org',
    )
    db.session.add(tpl)
    db.session.flush()
    log(f'  已建立表單模板：{tpl.secure_code}')
    return tpl


def ensure_workflow_template(db, FwWorkflowTemplate, org_sc, category, assignee_role_sc, apply, force):
    from app.utils.security import generate_secure_code

    graph = build_workflow_graph(assignee_role_sc)
    tpl = FwWorkflowTemplate.query.filter_by(
        org_secure_code=org_sc,
        code=WORKFLOW_CODE,
        is_deleted=False,
    ).first()
    if tpl and not force:
        log(f'  流程模板已存在：{tpl.secure_code}（revision {tpl.revision}）')
        return tpl

    if not apply:
        action = '覆寫' if tpl else '建立'
        log(f"  [預演] 會{action}流程模板 {WORKFLOW_CODE}（{len(graph['nodes'])} 節點 / {len(graph['edges'])} 連線）")
        return None

    if tpl:
        tpl.name = WORKFLOW_NAME
        tpl.description = WORKFLOW_DESCRIPTION
        tpl.category = category.name
        tpl.category_secure_code = category.secure_code
        tpl.graph = graph
        tpl.version = tpl.version or 'AA'
        tpl.revision = (tpl.revision or 0) + 1
        tpl.is_active = True
        tpl.is_protected = False
        tpl.permission_type = 'org'
        tpl.is_subprocess = False
        log(f'  已覆寫流程模板：{tpl.secure_code}（revision -> {tpl.revision}）')
        return tpl

    tpl = FwWorkflowTemplate(
        secure_code=generate_secure_code(),
        org_secure_code=org_sc,
        code=WORKFLOW_CODE,
        name=WORKFLOW_NAME,
        description=WORKFLOW_DESCRIPTION,
        category=category.name,
        category_secure_code=category.secure_code,
        graph=graph,
        version='AA',
        revision=1,
        is_published=False,
        is_active=True,
        is_protected=False,
        permission_type='org',
        is_subprocess=False,
    )
    db.session.add(tpl)
    db.session.flush()
    log(f'  已建立流程模板：{tpl.secure_code}')
    return tpl


def ensure_mapping_and_publish(db, models, org_sc, form_tpl, workflow_tpl, publisher, apply):
    FwFormWorkflowMapping = models['FwFormWorkflowMapping']
    FwPublishedFormWorkflow = models['FwPublishedFormWorkflow']
    from app.utils.security import generate_secure_code

    if not apply or not form_tpl or not workflow_tpl:
        log('  [預演] 會建立表單流程配對並發行最新 Published 快照')
        return None, None

    mapping = FwFormWorkflowMapping.query.filter_by(
        org_secure_code=org_sc,
        form_template_secure_code=form_tpl.secure_code,
        is_deleted=False,
    ).first()
    if mapping:
        mapping.workflow_template_id = workflow_tpl.id
        mapping.workflow_template_secure_code = workflow_tpl.secure_code
        mapping.workflow_template_code = workflow_tpl.code
        mapping.workflow_template_version = workflow_tpl.version
        mapping.is_active = True
        mapping.is_archived = False
        log(f'  配對已存在：{mapping.secure_code}')
    else:
        mapping = FwFormWorkflowMapping(
            secure_code=generate_secure_code(),
            org_secure_code=org_sc,
            form_template_id=form_tpl.id,
            form_template_secure_code=form_tpl.secure_code,
            form_template_code=form_tpl.code,
            form_template_version=form_tpl.version,
            workflow_template_id=workflow_tpl.id,
            workflow_template_secure_code=workflow_tpl.secure_code,
            workflow_template_code=workflow_tpl.code,
            workflow_template_version=workflow_tpl.version,
            is_active=True,
            is_published=False,
            priority=0,
            description=f'{form_tpl.name} + {workflow_tpl.name}',
        )
        db.session.add(mapping)
        db.session.flush()
        log(f'  已建立配對：{mapping.secure_code}')

    existing = FwPublishedFormWorkflow.query.filter_by(
        source_mapping_secure_code=mapping.secure_code,
        org_secure_code=org_sc,
        status='Published',
        is_deleted=False,
    ).order_by(FwPublishedFormWorkflow.publish_version.desc()).first()
    if existing:
        same = (
            existing.source_form_version == form_tpl.version
            and existing.source_form_revision == form_tpl.revision
            and existing.source_workflow_version == workflow_tpl.version
            and existing.source_workflow_revision == workflow_tpl.revision
        )
        if same:
            mapping.is_published = True
            log(f'  發行版本未變更，沿用 v{existing.publish_version}：{existing.secure_code}')
            return mapping, existing
        existing.status = 'Suspended'
        existing.suspended_at = datetime.utcnow()
        existing.suspended_by = publisher.secure_code
        log(f'  已停用舊發行版本 v{existing.publish_version}')

    published = FwPublishedFormWorkflow.create_from_mapping(
        mapping=mapping,
        form_template=form_tpl,
        workflow_template=workflow_tpl,
        published_by=publisher.secure_code,
        published_by_name=publisher.display_name or publisher.username,
    )
    mapping.is_published = True
    mapping.form_template_version = form_tpl.version
    mapping.workflow_template_version = workflow_tpl.version
    db.session.add(published)
    db.session.flush()
    log(f'  已發行 v{published.publish_version}：{published.secure_code}')
    return mapping, published


def ensure_routing_rule(db, OdFormTemplateMapping, org_sc, form_tpl, apply):
    from app.utils.security import generate_secure_code

    if not apply or not form_tpl:
        log('  [預演] 會建立啟用中的 catch-all 路由規則（正式環境請依政策改成分流規則）')
        return None

    rule = OdFormTemplateMapping.query.filter_by(
        org_secure_code=org_sc,
        event_class=None,
        form_template_secure_code=form_tpl.secure_code,
        payload_kind=None,
        is_deleted=False,
    ).first()
    if rule:
        rule.name = '全部事件（catch-all）'
        rule.priority = 0
        rule.match_rules = []
        rule.is_active = True
        rule.note = '由 provision_od_intake_for_org.py 建立；正式環境請依政策改成分流規則'
        log(f'  catch-all 路由規則已存在並確認啟用：{rule.secure_code}')
        return rule

    rule = OdFormTemplateMapping(
        secure_code=generate_secure_code(),
        org_secure_code=org_sc,
        event_class=None,
        form_template_secure_code=form_tpl.secure_code,
        name='全部事件（catch-all）',
        priority=0,
        match_rules=[],
        is_active=True,
        payload_kind=None,
        note='由 provision_od_intake_for_org.py 建立；正式環境請依政策改成分流規則',
    )
    db.session.add(rule)
    db.session.flush()
    log(f'  已建立啟用中的 catch-all 路由規則：{rule.secure_code}')
    return rule


def ensure_api_key(db, ApiKey, org_sc, admin, source_systems, apply):
    if not apply:
        log(f"  [預演] 會建立 API Key，scopes.od_intake.source_systems={source_systems}")
        return None, None, False

    existing = ApiKey.query.filter_by(
        org_secure_code=org_sc,
        name=API_KEY_NAME,
        is_deleted=False,
    ).first()
    if existing:
        scopes = existing.scopes or {}
        wanted = {'od_intake': {'source_systems': source_systems}}
        if scopes != wanted:
            existing.scopes = wanted
            log(f'  已更新既有 API Key 白名單：{existing.key_id}')
        else:
            log(f'  API Key 已存在：{existing.key_id}')
        return existing, None, False

    from app.services import api_key_service

    record, plaintext_secret_b64 = api_key_service.create_api_key(
        org_secure_code=org_sc,
        name=API_KEY_NAME,
        consumer_label='Open Defense intake',
        description='由 provision_od_intake_for_org.py 建立，用於 Open Defense 事件受理',
        scopes={'od_intake': {'source_systems': source_systems}},
        created_by_secure_code=admin.secure_code,
    )
    log(f'  已建立 API Key：{record.key_id}')
    return record, plaintext_secret_b64, True


def print_next_steps(key_record, secret, source_system):
    log('\n下一步')
    log('請設定環境變數後送一筆測試事件：')
    log('export BP_BASE_URL=<自己填平台網址，含 /beakplatform 前綴>')
    if key_record:
        log(f'export BP_API_KEY_ID={key_record.key_id}')
    else:
        log('export BP_API_KEY_ID=<既有 API Key ID>')
    if secret:
        log(f"export BP_API_KEY_SECRET='{secret}'  # 只顯示這一次，請立刻保存")
    else:
        log("export BP_API_KEY_SECRET='<既有金鑰密鑰無法再次顯示，請使用先前保存的 secret>'")
    log('')
    log('python3 scripts/examples/od_intake_send_event.py \\')
    log(f'  --source-system {source_system} --event-class web_activity --severity 4 \\')
    log('  --title "測試事件" --actor-ip 203.0.113.42 --target-host test.example.com')
    log('')
    log('案件會出現在「開放防禦 ／ 資安案件處置中心」，簽核任務會出現在「表單流程 ／ 待處理」。')


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description='從零建置單一企業的 Open Defense 事件受理鏈路',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('--org', default=None,
                        help='必填。企業 secure_code 或 domain_name，例如 lion.com')
    parser.add_argument('--apply', action='store_true',
                        help='實際寫入資料庫；省略時只做檢查與預演')
    parser.add_argument('--force', action='store_true',
                        help='表單／流程已存在時覆寫內容並重新發行')
    parser.add_argument('--source-system', action='append', default=None,
                        help='可重複指定，寫進 API Key 的 source_systems 白名單；預設 elk')
    parser.add_argument('--skip-api-key', action='store_true',
                        help='不建立 API Key（企業已經有 key 時用）')
    parser.add_argument('--assignee-role', default=DEFAULT_ASSIGNEE_ROLE,
                        help='簽核角色 code；預設 SECURITY_STAFF')
    return parser.parse_args(argv)


def provision(org_sc, apply, force=False, source_systems=None, skip_api_key=False,
              assignee_role=DEFAULT_ASSIGNEE_ROLE):
    source_systems = source_systems or ['elk']

    from app import db
    from app.models import Organization, Role, User
    from app.models.api_key import ApiKey
    from modules.form_workflow.models import (
        FwCategory, FwFormTemplate, FwWorkflowTemplate, FwFormWorkflowMapping,
        FwPublishedFormWorkflow,
    )
    from modules.open_defense.models import OdFormTemplateMapping

    models = {
        'FwFormWorkflowMapping': FwFormWorkflowMapping,
        'FwPublishedFormWorkflow': FwPublishedFormWorkflow,
    }

    org = resolve_org(Organization, org_sc)
    role = ensure_assignee_role(Role, org.secure_code, assignee_role)
    publisher = get_publisher(User, org.secure_code)

    log(f'\n企業：{org.name} / {org.domain_name} / {org.secure_code}')
    log(f'簽核角色：{role.code} / {role.secure_code}')
    log(f'發行人：{publisher.email}')
    if not apply:
        log('\n預演模式：不會寫入任何資料。加上 --apply 才會實際建置。')

    log('\n[1/6] 資安分類')
    category = ensure_security_category(db, FwCategory, org.secure_code, apply)

    log('\n[2/6] 表單模板')
    form_tpl = ensure_form_template(
        db, FwFormTemplate, org.secure_code, category, apply, force)

    log('\n[3/6] 流程模板')
    workflow_tpl = ensure_workflow_template(
        db, FwWorkflowTemplate, org.secure_code, category,
        role.secure_code, apply, force)

    log('\n[4/6] 表單流程配對與發行')
    mapping, published = ensure_mapping_and_publish(
        db, models, org.secure_code, form_tpl, workflow_tpl, publisher, apply)

    log('\n[5/6] 事件路由規則')
    routing_rule = ensure_routing_rule(
        db, OdFormTemplateMapping, org.secure_code, form_tpl, apply)
    log('  提醒：catch-all 規則會讓任何 event_class 都收案；正式環境請依政策改成分流規則。')

    key_record = None
    key_secret = None
    log('\n[6/6] API Key')
    if skip_api_key:
        log('  已依 --skip-api-key 略過')
    else:
        key_record, key_secret, _ = ensure_api_key(
            db, ApiKey, org.secure_code, publisher, source_systems, apply)

    return {
        'org': org,
        'category': category,
        'form': form_tpl,
        'workflow': workflow_tpl,
        'mapping': mapping,
        'published': published,
        'routing_rule': routing_rule,
        'api_key': key_record,
        'api_key_secret': key_secret,
        'source_systems': source_systems,
    }


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        log(__doc__)
        return 0

    args = parse_args(argv)
    if not args.org:
        raise SystemExit('缺少 --org。請指定企業 secure_code 或 domain_name，例如 --org lion.com')

    from app import create_app, db

    app = create_app('development')
    with app.app_context():
        try:
            result = provision(
                args.org,
                args.apply,
                force=args.force,
                source_systems=args.source_system or ['elk'],
                skip_api_key=args.skip_api_key,
                assignee_role=args.assignee_role,
            )
            if args.apply:
                db.session.commit()
                log('\n  已 commit 表單、流程、發行、路由與 API Key 設定')
            else:
                db.session.rollback()

            if not args.apply:
                log('\n預演完成，未寫入任何資料。')
                print_next_steps(None, None, result['source_systems'][0])
                return 0

            org = result['org']
            category = result['category']
            form_tpl = result['form']
            workflow_tpl = result['workflow']
            mapping = result['mapping']
            published = result['published']
            routing_rule = result['routing_rule']
            key_record = result['api_key']
            key_secret = result['api_key_secret']

            log('\n' + '=' * 72)
            log('建置完成')
            log('=' * 72)
            log(f'企業：{org.secure_code}')
            log(f'資安分類：{category.secure_code}')
            log(f'表單模板 {FORM_CODE}：{form_tpl.secure_code}')
            log(f'流程模板 {WORKFLOW_CODE}：{workflow_tpl.secure_code}')
            log(f'表單流程配對：{mapping.secure_code}')
            log(f'發行版本：{published.secure_code}（v{published.publish_version}）')
            log(f'路由規則：{routing_rule.secure_code}')
            if key_record:
                log(f'API Key：{key_record.key_id}')
                if not key_secret:
                    log('API Key secret：既有金鑰不會再次顯示，請使用先前保存的 secret')

            print_next_steps(key_record, key_secret, result['source_systems'][0])
            return 0
        except SystemExit:
            if args.apply:
                db.session.rollback()
            raise
        except Exception:
            if args.apply:
                db.session.rollback()
            raise


if __name__ == '__main__':
    raise SystemExit(main())
