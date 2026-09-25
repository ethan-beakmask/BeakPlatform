"""
PF-160 授權表單清單：list_fillable_published_templates()

這支是「你能手動填的表單，才能申請 key 去自動填」的唯一判定，
API Key 申請單的選項來源與 ApiKeyIssue 核發前的重驗都走它，
判定放寬等於讓申請人取得填不到的表單的自動化能力。
"""
import os
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("SYSTEM_ORG_CODE", "system.local")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db  # noqa: E402
from app.models import Role, User, UserRoleAssignment  # noqa: E402
from app.models.contract import Contract, ContractStatus  # noqa: E402
from app.models.user import UserType  # noqa: E402
from flask import session  # noqa: E402
from flask_login import login_user  # noqa: E402
from modules.form_workflow.api.fc_available import (  # noqa: E402
    list_published_form_templates,
)


def _login_in_request(user, org):
    login_user(user)
    session['org_secure_code'] = org.secure_code
    session['org_domain'] = org.domain_name


def _json_from_response(result):
    response = result[0] if isinstance(result, tuple) else result
    status = result[1] if isinstance(result, tuple) else response.status_code
    return status, response.get_json()


def _grant_form_workflow_contract(org):
    today = org.local_today()
    contract = Contract(
        secure_code=f'contract_fw_{org.secure_code[-8:]}',
        org_secure_code=org.secure_code,
        contract_number=f'CTR-FW-{org.secure_code[-8:]}',
        name='Form Workflow Test Contract',
        start_date=today - timedelta(days=1),
        end_date=today + timedelta(days=30),
        status=ContractStatus.ACTIVE,
        modules_config=json.dumps(['form_workflow']),
        is_deleted=False,
    )
    db.session.add(contract)
    db.session.commit()
    return contract


def _publish(org_sc, template_sc, mapping_sc, name, *, status='Published',
             category_sc=None, created_at=None, secure_code=None):
    from modules.form_workflow.models import FwPublishedFormWorkflow

    record = FwPublishedFormWorkflow(
        secure_code=secure_code or f'pub_{mapping_sc}',
        org_secure_code=org_sc,
        source_mapping_id=abs(hash(mapping_sc)) % 100000,
        source_mapping_secure_code=mapping_sc,
        source_form_template_id=abs(hash(template_sc)) % 100000,
        source_form_template_secure_code=template_sc,
        source_workflow_template_id=1,
        source_workflow_template_secure_code=f'wf_{mapping_sc}',
        publish_version=1,
        name=name,
        form_snapshot={'name': name, 'code': f'CODE_{template_sc}',
                       'category_secure_code': category_sc},
        workflow_snapshot={'name': f'WF {name}'},
        status=status,
        is_deleted=False,
    )
    if created_at:
        record.created_at = created_at
    db.session.add(record)
    db.session.commit()
    return record


def _grant_user(org_sc, mapping_sc, user_sc, secure_code):
    from modules.form_workflow.models import FwMappingPermission

    perm = FwMappingPermission(
        secure_code=secure_code,
        org_secure_code=org_sc,
        mapping_secure_code=mapping_sc,
        grant_type='user',
        grant_target=user_sc,
        include_children=False,
        is_deleted=False,
    )
    db.session.add(perm)
    db.session.commit()
    return perm


def _grant_role(org_sc, mapping_sc, role_code, secure_code, name=None):
    from modules.form_workflow.models import FwMappingPermission

    perm = FwMappingPermission(
        secure_code=secure_code,
        org_secure_code=org_sc,
        mapping_secure_code=mapping_sc,
        grant_type='role',
        grant_target=role_code,
        grant_target_name=name or role_code,
        include_children=False,
        is_deleted=False,
    )
    db.session.add(perm)
    db.session.commit()
    return perm


def _role(org, code, name=None):
    role = Role(
        org_secure_code=org.secure_code,
        code=code,
        name=name or code,
        role_type='ROLE',
        scope_type='GLOBAL',
        is_active=True,
        is_deleted=False,
    )
    db.session.add(role)
    db.session.commit()
    return role


def _assign(user, role):
    row = UserRoleAssignment(
        org_secure_code=user.org_secure_code,
        user_secure_code=user.secure_code,
        role_secure_code=role.secure_code,
        unit_secure_code=None,
        is_deleted=False,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _user(org, sc, username):
    user = User(
        secure_code=sc,
        org_secure_code=org.secure_code,
        username=username,
        email=f'{username}@example.com',
        display_name=username,
        user_type=UserType.EMPLOYEE,
        is_active=True,
        is_deleted=False,
    )
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()
    return user


def _mapping(org_sc, template_sc, mapping_sc, *, category_sc=None):
    from modules.form_workflow.models import (
        FwFormTemplate, FwFormWorkflowMapping, FwWorkflowTemplate,
    )

    suffix = mapping_sc[-12:]
    form = FwFormTemplate(
        secure_code=template_sc,
        org_secure_code=org_sc,
        code=f'FORM_{suffix}',
        name=f'Form {suffix}',
        category_secure_code=category_sc,
        schema={'display': 'form', 'components': [{'key': 'a', 'type': 'textfield'}]},
        version='AA',
        revision=1,
        is_active=True,
        is_deleted=False,
    )
    workflow = FwWorkflowTemplate(
        secure_code=f'wf_{suffix}',
        org_secure_code=org_sc,
        form_template_secure_code=template_sc,
        code=f'WF_{suffix}',
        name=f'Workflow {suffix}',
        graph={'nodes': [{'id': 'start', 'type': 'Start'}], 'edges': []},
        version='AA',
        revision=1,
        is_active=True,
        is_deleted=False,
    )
    db.session.add_all([form, workflow])
    db.session.flush()
    mapping = FwFormWorkflowMapping(
        secure_code=mapping_sc,
        org_secure_code=org_sc,
        form_template_id=form.id,
        form_template_secure_code=form.secure_code,
        form_template_code=form.code,
        form_template_version=form.version,
        workflow_template_id=workflow.id,
        workflow_template_secure_code=workflow.secure_code,
        workflow_template_code=workflow.code,
        workflow_template_version=workflow.version,
        is_active=True,
        is_deleted=False,
    )
    db.session.add(mapping)
    db.session.commit()
    return mapping


def _codes(user, org_sc):
    from modules.form_workflow.services.fill_permission_service import (
        list_fillable_published_templates,
    )
    return [i['secure_code'] for i in list_fillable_published_templates(user, org_sc)]


def test_only_templates_granted_to_the_user_are_listed(app, test_org, test_user):
    org_sc = test_org.secure_code
    _publish(org_sc, 'tpl_granted', 'map_granted', '有授權的表單')
    _publish(org_sc, 'tpl_other', 'map_other', '沒授權的表單')
    _grant_user(org_sc, 'map_granted', test_user.secure_code, 'perm_granted')

    codes = _codes(test_user, org_sc)

    # 未設任何規則的 map_other 走預設（企業成員角色），測試庫無角色 seed -> 不放行
    assert codes == ['tpl_granted']


def test_security_category_template_requires_explicit_permission(
        app, test_org, test_user):
    org_sc = test_org.secure_code
    _publish(org_sc, 'tpl_sec', 'map_sec', '資安案件表單',
             category_sc='CAT_SECURITY_f5bc0629')

    # 資安表單納入 API Key 申請判定，但沒有任何 mapping permission 時 fail-closed。
    assert _codes(test_user, org_sc) == []

    security_role = _role(test_org, 'SECURITY_STAFF', '資安人員')
    _grant_role(org_sc, 'map_sec', 'SECURITY_STAFF', 'perm_sec_role', '資安人員')
    assert _codes(test_user, org_sc) == []

    _assign(test_user, security_role)
    assert _codes(test_user, org_sc) == ['tpl_sec']


def test_regular_template_without_permissions_still_defaults_to_employee(
        app, test_org, test_user):
    org_sc = test_org.secure_code
    employee = _role(test_org, 'EMPLOYEE', '企業成員')
    _assign(test_user, employee)
    _publish(org_sc, 'tpl_employee_default', 'map_employee_default', '一般表單')

    assert _codes(test_user, org_sc) == ['tpl_employee_default']


def test_user_can_fill_mapping_security_fail_closed_and_role_allowed(
        app, test_org, test_user):
    from modules.form_workflow.services.fill_permission_service import (
        user_can_fill_mapping,
    )

    org_sc = test_org.secure_code
    employee = _role(test_org, 'EMPLOYEE', '企業成員')
    security_role = _role(test_org, 'SECURITY_STAFF', '資安人員')
    _assign(test_user, employee)

    _mapping(
        org_sc, 'tpl_ucfm_sec', 'map_ucfm_sec',
        category_sc='CAT_SECURITY_f5bc0629',
    )
    _mapping(org_sc, 'tpl_ucfm_regular', 'map_ucfm_regular')

    assert user_can_fill_mapping(test_user, org_sc, 'map_ucfm_sec') is False
    assert user_can_fill_mapping(test_user, org_sc, 'map_ucfm_regular') is True

    _grant_role(org_sc, 'map_ucfm_sec', 'SECURITY_STAFF', 'perm_ucfm_sec')
    assert user_can_fill_mapping(test_user, org_sc, 'map_ucfm_sec') is False

    _assign(test_user, security_role)
    assert user_can_fill_mapping(test_user, org_sc, 'map_ucfm_sec') is True


def test_list_published_templates_still_excludes_security(app, test_org):
    from modules.form_workflow.services.fill_permission_service import (
        list_published_templates,
    )

    org_sc = test_org.secure_code
    _publish(org_sc, 'tpl_pub_regular_direct', 'map_pub_regular_direct', '一般表單')
    _publish(org_sc, 'tpl_pub_sec_direct', 'map_pub_sec_direct', '資安表單',
             category_sc='CAT_SECURITY_f5bc0629')

    assert [
        item['secure_code'] for item in list_published_templates(org_sc)
    ] == ['tpl_pub_regular_direct']


def test_ensure_role_fill_permissions_idempotent_and_missing_roles(
        app, test_org):
    from modules.form_workflow.models import FwMappingPermission
    from modules.form_workflow.services.fill_permission_service import (
        ensure_role_fill_permissions,
    )

    org_sc = test_org.secure_code
    _mapping(org_sc, 'tpl_helper_roles', 'map_helper_roles')
    _role(test_org, 'SECURITY_STAFF', '資安人員')
    _role(test_org, 'SOC_SUPERVISOR', '資安主管')

    first = ensure_role_fill_permissions(
        org_sc, 'map_helper_roles', ['SECURITY_STAFF', 'SOC_SUPERVISOR', 'NO_SUCH_ROLE'])
    db.session.commit()
    second = ensure_role_fill_permissions(
        org_sc, 'map_helper_roles', ['SECURITY_STAFF', 'SOC_SUPERVISOR', 'NO_SUCH_ROLE'])

    assert first == {
        'created': ['SECURITY_STAFF', 'SOC_SUPERVISOR'],
        'existing': [],
        'missing_roles': ['NO_SUCH_ROLE'],
    }
    assert second == {
        'created': [],
        'existing': ['SECURITY_STAFF', 'SOC_SUPERVISOR'],
        'missing_roles': ['NO_SUCH_ROLE'],
    }
    assert FwMappingPermission.query.filter_by(
        org_secure_code=org_sc,
        mapping_secure_code='map_helper_roles',
        grant_type='role',
        is_deleted=False,
    ).count() == 2


def test_api_key_issue_recheck_marks_security_form_out_of_scope(
        app, test_org, test_user, monkeypatch):
    from modules.form_workflow.services import fill_permission_service
    from modules.form_workflow.services.node_handlers.api_key_issue_handler import (
        ApiKeyIssueHandler,
    )

    def fake_fillable(user, org_sc):
        assert user.secure_code == test_user.secure_code
        assert org_sc == test_org.secure_code
        return [{'secure_code': 'tpl_regular'}]

    monkeypatch.setattr(
        fill_permission_service, 'list_fillable_published_templates', fake_fillable)

    handler = ApiKeyIssueHandler.__new__(ApiKeyIssueHandler)
    assert handler._forms_out_of_scope(
        ['tpl_regular', 'tpl_security'], test_user, test_org.secure_code
    ) == ['tpl_security']


def test_latest_publish_decides_permission(app, test_org, test_user):
    """同一張表單有多個發行版本時，判定對象是最新的那一筆。

    external_trigger 解析 form_code 時取的就是最新 Published，
    若這裡拿舊版本判定，會出現「申請得到卻發不動」或反過來的授權落差。
    """
    org_sc = test_org.secure_code
    old = datetime.utcnow() - timedelta(days=2)
    _publish(org_sc, 'tpl_multi', 'map_old', '舊版配對',
             created_at=old, secure_code='pub_multi_old')
    _publish(org_sc, 'tpl_multi', 'map_new', '新版配對',
             created_at=datetime.utcnow(), secure_code='pub_multi_new')
    # 只授權舊版配對
    _grant_user(org_sc, 'map_old', test_user.secure_code, 'perm_multi_old')

    assert _codes(test_user, org_sc) == []

    _grant_user(org_sc, 'map_new', test_user.secure_code, 'perm_multi_new')
    assert _codes(test_user, org_sc) == ['tpl_multi']


def test_non_published_status_is_ignored(app, test_org, test_user):
    """只有 Published 能被外部觸發，Suspended/Archived 不得出現在申請選項。"""
    org_sc = test_org.secure_code
    _publish(org_sc, 'tpl_suspended', 'map_suspended', '已停用版本',
             status='Suspended')
    _grant_user(org_sc, 'map_suspended', test_user.secure_code, 'perm_suspended')

    assert _codes(test_user, org_sc) == []


def test_other_org_publish_is_not_visible(app, test_org, test_user):
    """TENANT-01：別家企業的發行不得出現。

    授權記錄刻意在「本企業」也放一筆同 mapping 的 grant --
    否則他企業的表單會因為查不到 perms 而落到預設規則被擋，
    測試就變成恆真：把 published 查詢的 org 過濾拿掉也照樣綠。
    """
    org_sc = test_org.secure_code
    _publish('other_org_00000000001', 'tpl_foreign', 'map_foreign', '他企業表單')
    _grant_user('other_org_00000000001', 'map_foreign',
                test_user.secure_code, 'perm_foreign')
    _grant_user(org_sc, 'map_foreign', test_user.secure_code, 'perm_foreign_local')

    assert _codes(test_user, org_sc) == []


def test_published_form_templates_endpoint_success_and_filters(
        app, test_org, test_admin, rbac_seed):
    org_sc = test_org.secure_code
    _publish(org_sc, 'tpl_pub_ok', 'map_pub_ok', '一般表單')
    _publish(org_sc, 'tpl_pub_sec', 'map_pub_sec', '資安表單',
             category_sc='CAT_SECURITY_f5bc0629')
    _publish('other_org_published01', 'tpl_other_org', 'map_other_org',
             '別企業表單')
    _grant_form_workflow_contract(test_org)

    with app.test_request_context('/api/form-center/published-form-templates'):
        _login_in_request(test_admin, test_org)
        status, data = _json_from_response(list_published_form_templates())

    assert status == 200
    assert data['success'] is True
    assert [item['secure_code'] for item in data['data']] == ['tpl_pub_ok']


def test_published_form_templates_endpoint_rejects_external(app, test_org):
    external = User(
        secure_code='fillable_ext_user001',
        org_secure_code=test_org.secure_code,
        username='fillable_ext',
        email='fillable_ext@example.com',
        display_name='External',
        user_type=UserType.EXTERNAL,
        is_active=True,
        is_deleted=False,
    )
    external.set_password('password123')
    db.session.add(external)
    db.session.commit()
    _grant_form_workflow_contract(test_org)

    with app.test_request_context('/api/form-center/published-form-templates'):
        _login_in_request(external, test_org)
        status, data = _json_from_response(list_published_form_templates())

    assert status == 403
    assert data['success'] is False
