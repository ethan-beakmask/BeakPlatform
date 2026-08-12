#!/usr/bin/env python3
"""
建置兩個 OpenDefense 資安事件處置流程變體（SOC 團隊版 / 小企業單人版）。

用途
    現行只有一個「資安事件處置流程」，其人力假設是「有人會在 15 分鐘內看到案件」。
    本腳本另外建置兩個流程，讓不同編制的組織都能直接用：

      A. SOC 團隊版   3~8 人、有輪班的監控中心
      B. 小企業單人版 一位資安人員、每天上班 8 小時、16 小時無人看管

    兩個流程各自綁一張新的表單模板（schema 完全複製自現行的資安事件處置表單），
    因為 intake 選流程的規則是「依 form_template 取最新 Published 快照」
    （modules/open_defense/services/intake_service.py:314-319），
    同一張表單同時只有一個生效流程。各配一張表單，三個流程才能並存，
    再由 od_form_template_mappings 的 match_rules 決定哪些案件走哪一個。

會做的事（全部冪等，重跑不會產生重複資料）
    1. 建立「資安主管」角色 SOC_SUPERVISOR（命名沿用 docs/guides/SOC_ROLE_DESIGN_GUIDE.md）
    2. 把該角色加進資安案件處置中心與儀表板的選單角色需求（雙鑰匙 Key2）
    3. 指派一位既有資安人員兼任該角色（可用 --supervisor 指定）
    4. 複製表單模板 -> SEC_IR_SOC_TEAM / SEC_IR_SOLO
    5. 建立兩個流程模板並寫入 graph
    6. 建立表單流程配對並發行

不會做的事
    - 不動現有的 SEC_INCIDENT_RESPONSE / SEC_INCIDENT_FLOW
    - 不建立 od_form_template_mappings 路由規則（要讓哪些案件走哪個流程是政策決定，
      請在「事件路由設定」頁自行設定，或用 --with-routing 建立停用狀態的範例規則）

用法
    cd /opt/BeakPlatform-dev
    set -a && source .env && set +a
    venv/bin/python scripts/examples/provision_od_workflow_variants.py --apply

參數
    --apply              實際寫入資料庫。不給這個參數時只做檢查並印出將要做的事
    --org <secure_code>  指定企業。省略時自動選用「有 SECURITY_STAFF 角色」的企業，
                         找到多個會要求明確指定
    --supervisor <email> 指定要兼任資安主管的帳號。省略時自動挑一位非 ORG_ADMIN 的
                         現有資安人員
    --with-routing       一併建立兩條停用狀態的 od 路由規則範例，方便之後啟用
    --force              流程／表單已存在時，覆寫其內容並重新發行
"""
import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'backend'))
# modules/ 在 repo 根，平常是 create_app() 載入模組時才進 sys.path，
# 這裡要在 app context 之外先 import model，所以自己補上。
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, _HERE)

from od_workflow_graphs import (  # noqa: E402
    build_soc_team_graph, build_solo_graph, validate_graph,
    SOLO_DAYTIME_GRACE_MINUTES, SOC_SLA_WARN_MINUTES, OFFICE_HOURS_NOTE,
)

SOURCE_FORM_CODE = 'SEC_INCIDENT_RESPONSE'
STAFF_ROLE_CODE = 'SECURITY_STAFF'
SUPERVISOR_ROLE_CODE = 'SOC_SUPERVISOR'
SUPERVISOR_ROLE_NAME = '資安主管'
SUPERVISOR_ROLE_DESC = '高嚴重度資安案件的第二級處置與封鎖決策覆核'

# 要把資安主管角色加進哪些選單的角色需求（雙鑰匙 Key2）。
# 少了這步，持有資安主管但沒有資安人員角色的帳號會看不到處置中心，
# 二線簽核任務就變成「清單上看得到、點不進去」。
SUPERVISOR_MENU_CODES = ['open_defense.security_cases', 'open_defense.dashboard']

VARIANTS = [
    {
        'key': 'soc_team',
        'form_code': 'SEC_IR_SOC_TEAM',
        'form_name': '資安事件處置（SOC 團隊版）',
        'form_desc': '供 3~8 人輪班監控中心使用，欄位與 SEC_INCIDENT_RESPONSE 相同',
        'workflow_code': 'SEC_IR_FLOW_SOC_TEAM',
        'workflow_name': '資安事件處置流程（SOC 團隊版）',
        'workflow_desc': (
            f'適用 3~8 人、有輪班的監控中心。高危案件開「簽核 + SLA 計時」雙軌，'
            f'{SOC_SLA_WARN_MINUTES} 分鐘未簽核發催辦廣播，再 {SOC_SLA_WARN_MINUTES} '
            f'分鐘仍未簽核升級通報資安主管。計時分支只催辦，不代替人做處置。'
        ),
    },
    {
        'key': 'solo',
        'form_code': 'SEC_IR_SOLO',
        'form_name': '資安事件處置（小企業單人版）',
        'form_desc': '供單一資安人員的小型組織使用，欄位與 SEC_INCIDENT_RESPONSE 相同',
        'workflow_code': 'SEC_IR_FLOW_SOLO',
        'workflow_name': '資安事件處置流程（小企業單人版）',
        'workflow_desc': (
            f'適用一位資安人員、每天上班 8 小時的組織。高危且有來源 IP 的案件：'
            f'非上班時段立即自動封鎖（TTL 24 小時）並留待複核；上班時段交人工處理，'
            f'但 {SOLO_DAYTIME_GRACE_MINUTES} 分鐘未處理仍會自動封鎖。'
            f'{OFFICE_HOURS_NOTE}。'
        ),
    },
]

# --with-routing 用的範例規則（一律建成停用，要用再去「事件路由設定」啟用）
SAMPLE_ROUTING = {
    'soc_team': {
        'name': '【範例｜停用中】高嚴重度走 SOC 團隊版',
        'priority': 200,
        'match_rules': [{'field': 'severity_id', 'op': 'gte', 'value': 5}],
    },
    'solo': {
        'name': '【範例｜停用中】Suricata 來源走小企業單人版',
        'priority': 210,
        'match_rules': [{'field': 'source_system', 'op': 'eq', 'value': 'suricata'}],
    },
}


def log(msg):
    print(msg, flush=True)


def resolve_org(db, models, org_arg):
    """決定要建置在哪個企業。"""
    Role = models['Role']
    query = Role.query.filter_by(code=STAFF_ROLE_CODE, is_deleted=False)
    if org_arg:
        role = query.filter_by(org_secure_code=org_arg).first()
        if not role:
            raise SystemExit(f'企業 {org_arg} 沒有 {STAFF_ROLE_CODE} 角色，'
                             f'請先確認該企業已採購開放防禦模組')
        return org_arg, role.secure_code

    roles = query.all()
    if not roles:
        raise SystemExit(f'找不到任何有 {STAFF_ROLE_CODE} 角色的企業。'
                         f'請先讓企業採購開放防禦模組，或用 --org 指定')
    orgs = {r.org_secure_code for r in roles}
    if len(orgs) > 1:
        raise SystemExit('有多個企業具備資安人員角色，請用 --org 指定其中一個：\n  '
                         + '\n  '.join(sorted(orgs)))
    return roles[0].org_secure_code, roles[0].secure_code


def ensure_supervisor_role(db, models, org_sc, apply):
    """建立資安主管角色（冪等）。回傳 secure_code。"""
    Role = models['Role']
    from app.utils.security import generate_secure_code

    role = Role.query.filter_by(
        org_secure_code=org_sc, code=SUPERVISOR_ROLE_CODE, is_deleted=False).first()
    if role:
        log(f'  角色 {SUPERVISOR_ROLE_CODE} 已存在：{role.secure_code}')
        return role.secure_code

    if not apply:
        log(f'  [預演] 會建立角色 {SUPERVISOR_ROLE_CODE}（{SUPERVISOR_ROLE_NAME}）')
        return None

    role = Role(
        secure_code=generate_secure_code(),
        org_secure_code=org_sc,
        code=SUPERVISOR_ROLE_CODE,
        name=SUPERVISOR_ROLE_NAME,
        description=SUPERVISOR_ROLE_DESC,
        role_type='ROLE',
        scope_type='GLOBAL',
        role_level='MODULE',
        level=1,
        sort_order=0,
        is_manager=True,
        is_system_role=False,
        is_active=True,
        full_path=f'/{SUPERVISOR_ROLE_NAME}',
    )
    db.session.add(role)
    db.session.flush()
    log(f'  已建立角色 {SUPERVISOR_ROLE_CODE}：{role.secure_code}')
    return role.secure_code


def ensure_menu_requirements(db, models, org_sc, role_sc, apply):
    """把資安主管角色加進處置中心與儀表板的選單角色需求。"""
    MenuItem = models['MenuItem']
    MenuRoleRequirement = models['MenuRoleRequirement']
    from app.utils.security import generate_secure_code

    if not role_sc:
        log('  [預演] 角色尚未建立，略過選單角色需求')
        return

    for menu_code in SUPERVISOR_MENU_CODES:
        menu = MenuItem.query.filter_by(code=menu_code, is_deleted=False).first()
        if not menu:
            log(f'  選單 {menu_code} 不存在，略過')
            continue

        exists = MenuRoleRequirement.query.filter_by(
            menu_secure_code=menu.secure_code,
            role_secure_code=role_sc,
            org_secure_code=org_sc,
            is_deleted=False,
        ).first()
        if exists:
            log(f'  選單 {menu_code} 已含 {SUPERVISOR_ROLE_CODE}')
            continue

        if not apply:
            log(f'  [預演] 會把 {SUPERVISOR_ROLE_CODE} 加進選單 {menu_code}')
            continue

        db.session.add(MenuRoleRequirement(
            secure_code=generate_secure_code(),
            menu_secure_code=menu.secure_code,
            role_secure_code=role_sc,
            org_secure_code=org_sc,
        ))
        log(f'  已把 {SUPERVISOR_ROLE_CODE} 加進選單 {menu_code}')


def ensure_supervisor_assignment(db, models, org_sc, role_sc, staff_role_sc,
                                 supervisor_email, apply):
    """指派一位資安人員兼任資安主管。"""
    User = models['User']
    UserRoleAssignment = models['UserRoleAssignment']
    from app.utils.security import generate_secure_code

    if not role_sc:
        log('  [預演] 角色尚未建立，略過人員指派')
        return

    if supervisor_email:
        user = User.query.filter_by(
            email=supervisor_email, org_secure_code=org_sc,
            is_deleted=False, is_active=True).first()
        if not user:
            raise SystemExit(f'找不到可用帳號 {supervisor_email}')
    else:
        # 指南寫明：角色指派給 ORG_ADMIN 無效果（管理員本來就 bypass 角色檢查），
        # 所以自動挑選時排除管理員帳號。
        candidates = (
            User.query
            .join(UserRoleAssignment,
                  UserRoleAssignment.user_secure_code == User.secure_code)
            .filter(UserRoleAssignment.role_secure_code == staff_role_sc,
                    UserRoleAssignment.is_deleted.is_(False),
                    User.org_secure_code == org_sc,
                    User.is_deleted.is_(False),
                    User.is_active.is_(True),
                    User.user_type != 'ORG_ADMIN')
            .order_by(User.id.desc())
            .all()
        )
        if not candidates:
            log('  找不到可兼任資安主管的非管理員帳號，略過指派'
                '（可稍後在「帳號角色」頁自行指派）')
            return
        user = candidates[0]

    exists = UserRoleAssignment.query.filter_by(
        user_secure_code=user.secure_code,
        role_secure_code=role_sc,
        is_deleted=False,
    ).first()
    if exists:
        log(f'  {user.email} 已具備 {SUPERVISOR_ROLE_CODE}')
        return

    if not apply:
        log(f'  [預演] 會把 {SUPERVISOR_ROLE_CODE} 指派給 {user.email}')
        return

    db.session.add(UserRoleAssignment(
        secure_code=generate_secure_code(),
        org_secure_code=org_sc,
        user_secure_code=user.secure_code,
        role_secure_code=role_sc,
    ))
    log(f'  已把 {SUPERVISOR_ROLE_CODE} 指派給 {user.email}（{user.display_name}）')


def ensure_form_template(db, models, org_sc, source_form, spec, apply, force):
    """複製表單模板。schema 必須與來源一致，intake 才寫得進去。"""
    FwFormTemplate = models['FwFormTemplate']
    from app.utils.security import generate_secure_code

    tpl = FwFormTemplate.query.filter_by(
        org_secure_code=org_sc, code=spec['form_code'], is_deleted=False).first()

    if tpl and not force:
        log(f"  表單 {spec['form_code']} 已存在：{tpl.secure_code}")
        return tpl

    if not apply:
        action = '覆寫' if tpl else '建立'
        log(f"  [預演] 會{action}表單 {spec['form_code']}（複製 {SOURCE_FORM_CODE} 的 schema）")
        return None

    if tpl:
        tpl.schema = source_form.schema
        tpl.builder_config = source_form.builder_config
        tpl.name = spec['form_name']
        tpl.description = spec['form_desc']
        tpl.revision = (tpl.revision or 0) + 1
        log(f"  已覆寫表單 {spec['form_code']}：{tpl.secure_code}（revision -> {tpl.revision}）")
        return tpl

    tpl = FwFormTemplate(
        secure_code=generate_secure_code(),
        org_secure_code=org_sc,
        code=spec['form_code'],
        name=spec['form_name'],
        description=spec['form_desc'],
        # category_secure_code 必須沿用資安分類：資安案件處置中心是靠
        # security_center.py 的 CAT_SECURITY_ 前綴認出資安案件的，
        # 換了分類這些案件就不會出現在處置中心。
        category=source_form.category,
        category_secure_code=source_form.category_secure_code,
        schema=source_form.schema,
        builder_config=source_form.builder_config,
        version='AA',
        revision=1,
        is_published=False,
        is_active=True,
        is_protected=False,
        permission_type='org',
    )
    db.session.add(tpl)
    db.session.flush()
    log(f"  已建立表單 {spec['form_code']}：{tpl.secure_code}")
    return tpl


def ensure_workflow_template(db, models, org_sc, source_form, spec, graph, apply, force):
    """建立或更新流程模板。"""
    FwWorkflowTemplate = models['FwWorkflowTemplate']
    from app.utils.security import generate_secure_code

    tpl = FwWorkflowTemplate.query.filter_by(
        org_secure_code=org_sc, code=spec['workflow_code'], is_deleted=False).first()

    if tpl and not force:
        log(f"  流程 {spec['workflow_code']} 已存在：{tpl.secure_code}")
        return tpl

    if not apply:
        action = '覆寫' if tpl else '建立'
        log(f"  [預演] 會{action}流程 {spec['workflow_code']}"
            f"（{len(graph['nodes'])} 節點 / {len(graph['edges'])} 連線）")
        return None

    if tpl:
        tpl.graph = graph
        tpl.name = spec['workflow_name']
        tpl.description = spec['workflow_desc']
        # 直接改 graph 不會自動 bump revision，而發行是以 version+revision 判斷
        # 有無變更的，不加這一行會發行成「版本未變更」並沿用舊快照。
        tpl.revision = (tpl.revision or 0) + 1
        log(f"  已覆寫流程 {spec['workflow_code']}：{tpl.secure_code}"
            f"（revision -> {tpl.revision}）")
        return tpl

    tpl = FwWorkflowTemplate(
        secure_code=generate_secure_code(),
        org_secure_code=org_sc,
        code=spec['workflow_code'],
        name=spec['workflow_name'],
        description=spec['workflow_desc'],
        category=source_form.category,
        category_secure_code=source_form.category_secure_code,
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
    log(f"  已建立流程 {spec['workflow_code']}：{tpl.secure_code}")
    return tpl


def ensure_mapping_and_publish(db, models, org_sc, form_tpl, wf_tpl, publisher, apply):
    """建立表單流程配對並發行。"""
    FwFormWorkflowMapping = models['FwFormWorkflowMapping']
    FwPublishedFormWorkflow = models['FwPublishedFormWorkflow']
    from app.utils.security import generate_secure_code

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

    # 發行：沿用 API 的邏輯（api/mappings.py::publish_mapping），
    # 版本相同就不重複建，不同則停用舊版再建新版。
    existing = FwPublishedFormWorkflow.query.filter_by(
        source_mapping_secure_code=mapping.secure_code, status='Published').first()
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


def ensure_sample_routing(db, models, org_sc, variant_key, form_tpl, apply):
    """建立停用狀態的路由規則範例。"""
    OdFormTemplateMapping = models['OdFormTemplateMapping']
    from app.utils.security import generate_secure_code

    if not apply or not form_tpl:
        log('  [預演] 會建立停用狀態的路由規則範例')
        return

    spec = SAMPLE_ROUTING[variant_key]
    exists = OdFormTemplateMapping.query.filter_by(
        org_secure_code=org_sc, name=spec['name'], is_deleted=False).first()
    if exists:
        log(f"  路由規則「{spec['name']}」已存在：{exists.secure_code}")
        return

    rule = OdFormTemplateMapping(
        secure_code=generate_secure_code(),
        org_secure_code=org_sc,
        name=spec['name'],
        form_template_secure_code=form_tpl.secure_code,
        priority=spec['priority'],
        match_rules=spec['match_rules'],
        is_active=False,
        note='由 provision_od_workflow_variants.py 建立，預設停用；'
             '確認條件符合貴組織的政策後再啟用',
    )
    db.session.add(rule)
    db.session.flush()
    log(f"  已建立停用的路由規則「{spec['name']}」：{rule.secure_code}")


def main():
    parser = argparse.ArgumentParser(
        description='建置 OpenDefense 的 SOC 團隊版與小企業單人版資安事件處置流程',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('--apply', action='store_true',
                        help='實際寫入資料庫；省略時只做檢查與預演')
    parser.add_argument('--org', default=None,
                        help='企業 secure_code；省略時自動偵測')
    parser.add_argument('--supervisor', default=None,
                        help='要兼任資安主管的帳號 e-mail；省略時自動挑選')
    parser.add_argument('--with-routing', action='store_true',
                        help='一併建立停用狀態的 od 路由規則範例')
    parser.add_argument('--force', action='store_true',
                        help='表單／流程已存在時覆寫內容並重新發行')
    args = parser.parse_args()

    # graph 的結構檢查先做，錯的東西不要進資料庫
    log('檢查 graph 結構…')
    dummy = 'X' * 22
    for name, graph in (('SOC 團隊版', build_soc_team_graph(dummy, dummy)),
                        ('小企業單人版', build_solo_graph(dummy))):
        problems = validate_graph(graph)
        if problems:
            log(f'  {name} 有 {len(problems)} 個結構問題：')
            for p in problems:
                log(f'    - {p}')
            raise SystemExit('graph 結構檢查未通過，中止')
        log(f"  {name}：{len(graph['nodes'])} 節點 / {len(graph['edges'])} 連線，通過")

    from app import create_app, db
    from app.models import (
        Role, User, UserRoleAssignment, MenuItem, MenuRoleRequirement,
    )
    from modules.form_workflow.models import (
        FwFormTemplate, FwWorkflowTemplate, FwFormWorkflowMapping,
        FwPublishedFormWorkflow,
    )
    from modules.open_defense.models import OdFormTemplateMapping

    models = {
        'Role': Role, 'User': User, 'UserRoleAssignment': UserRoleAssignment,
        'MenuItem': MenuItem, 'MenuRoleRequirement': MenuRoleRequirement,
        'FwFormTemplate': FwFormTemplate, 'FwWorkflowTemplate': FwWorkflowTemplate,
        'FwFormWorkflowMapping': FwFormWorkflowMapping,
        'FwPublishedFormWorkflow': FwPublishedFormWorkflow,
        'OdFormTemplateMapping': OdFormTemplateMapping,
    }

    app = create_app('development')
    with app.app_context():
        org_sc, staff_role_sc = resolve_org(db, models, args.org)
        log(f'\n企業：{org_sc}')
        log(f'資安人員角色：{staff_role_sc}')

        source_form = FwFormTemplate.query.filter_by(
            org_secure_code=org_sc, code=SOURCE_FORM_CODE, is_deleted=False).first()
        if not source_form:
            raise SystemExit(f'找不到來源表單 {SOURCE_FORM_CODE}，無法複製 schema')
        field_count = len((source_form.schema or {}).get('components', []))
        log(f'來源表單：{source_form.secure_code}（{field_count} 個頂層元件）')

        publisher = User.query.filter_by(
            org_secure_code=org_sc, user_type='ORG_ADMIN',
            is_deleted=False, is_active=True).first()

        log('\n[1/5] 資安主管角色')
        supervisor_role_sc = ensure_supervisor_role(db, models, org_sc, args.apply)

        log('\n[2/5] 選單角色需求（雙鑰匙 Key2）')
        ensure_menu_requirements(db, models, org_sc, supervisor_role_sc, args.apply)

        log('\n[3/5] 人員指派')
        ensure_supervisor_assignment(db, models, org_sc, supervisor_role_sc,
                                     staff_role_sc, args.supervisor, args.apply)

        results = []
        for idx, spec in enumerate(VARIANTS, start=1):
            log(f"\n[4/5] 建置 {spec['workflow_name']}")
            if spec['key'] == 'soc_team':
                graph = build_soc_team_graph(
                    staff_role_sc, supervisor_role_sc or staff_role_sc)
                if not supervisor_role_sc and args.apply:
                    log('  警告：資安主管角色不存在，二線節點暫時指向資安人員')
            else:
                graph = build_solo_graph(staff_role_sc)

            form_tpl = ensure_form_template(
                db, models, org_sc, source_form, spec, args.apply, args.force)
            wf_tpl = ensure_workflow_template(
                db, models, org_sc, source_form, spec, graph, args.apply, args.force)
            mapping, published = ensure_mapping_and_publish(
                db, models, org_sc, form_tpl, wf_tpl, publisher, args.apply)

            if args.with_routing:
                ensure_sample_routing(db, models, org_sc, spec['key'], form_tpl, args.apply)

            results.append((spec, form_tpl, wf_tpl, mapping, published))

        log('\n[5/5] 收尾')
        if args.apply:
            db.session.commit()
            log('  已 commit')
        else:
            db.session.rollback()
            log('  預演模式，未寫入任何資料。加上 --apply 才會實際建置')
            return

        log('\n' + '=' * 72)
        log('建置完成，識別碼如下（下次要改流程時用得到）')
        log('=' * 72)
        if supervisor_role_sc:
            log(f'資安主管角色 {SUPERVISOR_ROLE_CODE}：{supervisor_role_sc}')
        for spec, form_tpl, wf_tpl, mapping, published in results:
            log(f"\n{spec['workflow_name']}")
            log(f"  表單模板 {spec['form_code']}：{form_tpl.secure_code}")
            log(f"  流程模板 {spec['workflow_code']}：{wf_tpl.secure_code}")
            log(f'  表單流程配對：{mapping.secure_code}')
            log(f'  發行版本：{published.secure_code}（v{published.publish_version}）')
            log(f'  流程設計器：/forms/workflows/{wf_tpl.secure_code}')
        log('\n路由設定頁：/open-defense/event-routing/')
        log('資安案件處置中心：/open-defense/security-cases/')


if __name__ == '__main__':
    main()
