# -*- coding: utf-8 -*-
"""
OpHrLookup 人事資料取值節點測試
"""
import json
import os
import secrets
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db  # noqa: E402
from app.models import (  # noqa: E402
    ApprovalCategory,
    JobFamily,
    JobLevel,
    JobLevelApprovalLimit,
    JobTitle,
    Organization,
    OrganizationalUnit,
    EmployeePosition,
    PositionType,
    Role,
    RoleType,
    UnitType,
    User,
    UserRoleAssignment,
    UserUnitMembership,
    MembershipType,
)
from app.models.contract import Contract, ContractStatus  # noqa: E402
from app.services.unit_resolver import iter_manager_chain, resolve_role_holders  # noqa: E402
from modules.form_workflow.services.node_handlers.hr_lookup_handler import HrLookupHandler  # noqa: E402


ORG2 = 'hr_org_other_0000000000001'


@pytest.fixture(autouse=True)
def reset_module_loader_for_function_scoped_app():
    from app.module_loader import module_loader

    previous_skip = os.environ.get('SKIP_MODULE_SYNC')
    os.environ['SKIP_MODULE_SYNC'] = '1'
    module_loader._loaded = False
    yield
    module_loader._loaded = False
    if previous_skip is None:
        os.environ.pop('SKIP_MODULE_SYNC', None)
    else:
        os.environ['SKIP_MODULE_SYNC'] = previous_skip


@pytest.fixture
def hr_env(app, test_org):
    test_org.set_setting('timezone', 'Asia/Taipei')
    org2 = Organization(
        secure_code=ORG2,
        code='HR_ORG2',
        name='HR Other Org',
        domain_name='hr-other.local',
        settings=json.dumps({'timezone': 'Asia/Taipei'}),
        is_active=True,
        is_deleted=False,
    )
    db.session.add(org2)
    db.session.flush()

    today = test_org.local_today()
    yesterday = today - timedelta(days=1)
    older = today - timedelta(days=30)
    newer = today - timedelta(days=10)

    db.session.add(Contract(
        org_secure_code=test_org.secure_code,
        contract_number='CTR-HR-LOOKUP',
        name='HR lookup test contract',
        start_date=today - timedelta(days=1),
        end_date=today + timedelta(days=30),
        status=ContractStatus.ACTIVE,
        modules_config=json.dumps(['form_workflow']),
    ))

    levels = {
        'L100': JobLevel(org_secure_code=test_org.secure_code, code='L100', name='助理級', level_order=100, is_manager_level=False),
        'L300': JobLevel(org_secure_code=test_org.secure_code, code='L300', name='主管級', level_order=300, is_manager_level=True),
        'L500': JobLevel(org_secure_code=test_org.secure_code, code='L500', name='經理級', level_order=500, is_manager_level=True),
    }
    for level in levels.values():
        db.session.add(level)
    db.session.flush()

    family_root = JobFamily(
        org_secure_code=test_org.secure_code,
        code='PROF',
        name='專業職',
        family_type='PROFESSIONAL',
        is_active=True,
    )
    db.session.add(family_root)
    db.session.flush()
    family_child = JobFamily(
        org_secure_code=test_org.secure_code,
        code='TECH',
        name='工程技術職',
        family_type='PROFESSIONAL',
        parent_secure_code=family_root.secure_code,
        is_active=True,
    )
    family_mgr = JobFamily(
        org_secure_code=test_org.secure_code,
        code='MGR',
        name='管理職',
        family_type='MANAGER',
        is_active=True,
    )
    db.session.add_all([family_child, family_mgr])
    db.session.flush()

    titles = {
        'ENG': JobTitle(
            org_secure_code=test_org.secure_code,
            code='ENG',
            name='工程師',
            short_name='工程',
            job_level_secure_code=levels['L100'].secure_code,
            job_family_secure_code=family_child.secure_code,
            is_supervisor=False,
        ),
        'LEAD': JobTitle(
            org_secure_code=test_org.secure_code,
            code='LEAD',
            name='主任',
            short_name='主任',
            job_level_secure_code=levels['L300'].secure_code,
            job_family_secure_code=family_mgr.secure_code,
            is_supervisor=True,
        ),
        'MGR': JobTitle(
            org_secure_code=test_org.secure_code,
            code='MGR',
            name='經理',
            short_name='經理',
            job_level_secure_code=levels['L500'].secure_code,
            job_family_secure_code=family_mgr.secure_code,
            is_supervisor=True,
        ),
    }
    for title in titles.values():
        db.session.add(title)
    db.session.flush()

    hq = OrganizationalUnit(
        org_secure_code=test_org.secure_code,
        code='HQ',
        name='公司',
        unit_type=UnitType.DEPARTMENT,
        full_path='/公司',
        level=1,
        is_active=True,
    )
    db.session.add(hq)
    db.session.flush()
    rd = OrganizationalUnit(
        org_secure_code=test_org.secure_code,
        code='RD',
        name='研發部',
        unit_type=UnitType.DEPARTMENT,
        parent_secure_code=hq.secure_code,
        full_path='/公司/研發部',
        level=2,
        is_active=True,
    )
    db.session.add(rd)
    db.session.flush()

    roles = {
        'manager': Role(
            org_secure_code=test_org.secure_code,
            code='DEPT_MANAGER',
            name='部門主管',
            role_type=RoleType.POSITION,
            scope_type='DEPARTMENT',
            is_active=True,
            is_deleted=False,
        ),
        'member': Role(
            org_secure_code=test_org.secure_code,
            code='DEPT_MEMBER',
            name='部門成員',
            role_type=RoleType.ROLE,
            scope_type='DEPARTMENT',
            is_active=True,
            is_deleted=False,
        ),
        'deputy': Role(
            org_secure_code=test_org.secure_code,
            code='DEPT_DEPUTY',
            name='副主管',
            role_type=RoleType.POSITION,
            scope_type='DEPARTMENT',
            is_active=True,
            is_deleted=False,
        ),
    }
    for role in roles.values():
        db.session.add(role)
    db.session.flush()

    users = {}
    for code, name, org_code in [
        ('hr_user_a_000000000000000001', '申請人 A', test_org.secure_code),
        ('hr_user_b_000000000000000001', '主管 B', test_org.secure_code),
        ('hr_user_c_000000000000000001', '主管 C', test_org.secure_code),
        ('hr_user_x_000000000000000001', '外部 X', ORG2),
    ]:
        user = User(
            secure_code=code,
            org_secure_code=org_code,
            username=code,
            email=f'{code}@example.test',
            display_name=name,
            is_active=True,
            is_deleted=False,
        )
        user.set_password(secrets.token_urlsafe(16))
        db.session.add(user)
        users[code[-25:26] if False else code] = user
    db.session.flush()

    category = ApprovalCategory(
        org_secure_code=test_org.secure_code,
        code='TRAVEL',
        name='差旅費',
        currency='TWD',
        sort_order=10,
        is_active=True,
    )
    no_limit_category = ApprovalCategory(
        org_secure_code=test_org.secure_code,
        code='MEAL',
        name='餐費',
        currency='TWD',
        sort_order=20,
        is_active=True,
    )
    inactive_category = ApprovalCategory(
        org_secure_code=test_org.secure_code,
        code='OLD',
        name='舊類別',
        currency='TWD',
        sort_order=30,
        is_active=False,
    )
    other_category = ApprovalCategory(
        org_secure_code=ORG2,
        code='OTHER',
        name='跨企業類別',
        currency='TWD',
        sort_order=5,
        is_active=True,
    )
    db.session.add_all([category, no_limit_category, inactive_category, other_category])
    db.session.flush()

    for level_code, amount in [('L100', 10000), ('L300', 100000), ('L500', 1000000)]:
        db.session.add(JobLevelApprovalLimit(
            org_secure_code=test_org.secure_code,
            job_level_secure_code=levels[level_code].secure_code,
            category_secure_code=category.secure_code,
            approval_limit=amount,
        ))

    def assign(user, role, unit=None, valid_until=None):
        row = UserRoleAssignment(
            org_secure_code=user.org_secure_code,
            user_secure_code=user.secure_code,
            role_secure_code=role.secure_code,
            unit_secure_code=unit.secure_code if unit else None,
            valid_until=valid_until,
            is_deleted=False,
        )
        db.session.add(row)
        db.session.flush()
        return row

    def add_position(user, title, ptype=PositionType.PRIMARY, unit=None, start=None, until=None, head=False):
        pos = EmployeePosition(
            org_secure_code=test_org.secure_code,
            user_secure_code=user.secure_code,
            job_title_secure_code=title.secure_code,
            unit_secure_code=(unit or rd).secure_code,
            position_type=ptype,
            is_unit_head=head,
            effective_from=start or older,
            effective_until=until,
            is_active=True,
            is_deleted=False,
        )
        db.session.add(pos)
        db.session.flush()
        return pos

    user_a = users['hr_user_a_000000000000000001']
    user_b = users['hr_user_b_000000000000000001']
    user_c = users['hr_user_c_000000000000000001']
    pos_a = add_position(user_a, titles['ENG'])
    pos_b = add_position(user_b, titles['LEAD'], head=True)
    pos_c = add_position(user_c, titles['MGR'], unit=hq, head=True)
    user_a.primary_unit_secure_code = rd.secure_code
    user_b.primary_unit_secure_code = rd.secure_code
    user_c.primary_unit_secure_code = hq.secure_code
    db.session.add(UserUnitMembership(
        org_secure_code=test_org.secure_code,
        user_secure_code=user_a.secure_code,
        unit_secure_code=rd.secure_code,
        membership_type=MembershipType.SOLID,
        is_deleted=False,
    ))
    assign(user_a, roles['member'], rd)
    assign(user_b, roles['manager'], rd)
    assign(user_c, roles['manager'], hq)
    db.session.commit()

    return SimpleNamespace(
        org=test_org,
        org2=org2,
        today=today,
        yesterday=yesterday,
        older=older,
        newer=newer,
        levels=levels,
        families={'root': family_root, 'child': family_child, 'manager': family_mgr},
        titles=titles,
        unit=rd,
        units={'hq': hq, 'rd': rd},
        roles=roles,
        users=users,
        category=category,
        no_limit_category=no_limit_category,
        inactive_category=inactive_category,
        positions={'a': pos_a, 'b': pos_b, 'c': pos_c},
        add_position=add_position,
        assign=assign,
    )


def make_handler(config, hr_env, applicant=None, replacements=None):
    queue_item = SimpleNamespace(
        org_secure_code=hr_env.org.secure_code,
        node_id='n_hr_1',
        node_type='OpHrLookup',
        node_config=config,
        secure_code='QUEUE_HR_TEST',
        status='PENDING',
        id=1,
        retry_count=0,
        started_at=None,
        process_id=None,
        workflow_instance_secure_code=None,
    )
    handler = HrLookupHandler(queue_item)
    flow_vars = {}
    warnings = []
    handler.report_running = lambda: None
    handler.log_info = lambda msg, details=None: None
    handler.log_error = lambda msg, details=None: None
    handler.log_warning = lambda msg, details=None: warnings.append((msg, details))
    handler.set_flow_var = lambda name, value: flow_vars.__setitem__(name, value)
    handler._form_instance = SimpleNamespace(
        applicant_secure_code=applicant or hr_env.users['hr_user_a_000000000000000001'].secure_code
    )
    handler.replace_variables = lambda text, **kw: replacements.get(text, text) if replacements else text
    return handler, flow_vars, warnings


def run_lookup(config, hr_env, applicant=None, replacements=None):
    handler, flow_vars, warnings = make_handler(config, hr_env, applicant, replacements)
    return handler.handle(), flow_vars, warnings


def test_applicant_primary_position_outputs_all_core_variables(hr_env):
    resp, vars_, _ = run_lookup({'var_prefix': 'hr'}, hr_env)

    assert resp['status'] == 'success'
    assert vars_['hr_found'] == 'true'
    assert vars_['hr_user_code'] == hr_env.users['hr_user_a_000000000000000001'].secure_code
    assert vars_['hr_user_name'] == '申請人 A'
    assert vars_['hr_position_type'] == 'PRIMARY'
    assert vars_['hr_job_title'] == '工程師'
    assert vars_['hr_job_title_code'] == 'ENG'
    assert vars_['hr_job_title_short'] == '工程'
    assert vars_['hr_is_supervisor'] == 'false'
    assert vars_['hr_job_level_code'] == 'L100'
    assert vars_['hr_job_level_name'] == '助理級'
    assert vars_['hr_job_level_order'] == 100
    assert vars_['hr_job_level_is_manager'] == 'false'
    assert vars_['hr_job_family_code'] == 'TECH'
    assert vars_['hr_job_family_name'] == '工程技術職'
    assert vars_['hr_job_family_type'] == 'PROFESSIONAL'
    assert vars_['hr_job_family_root_code'] == 'PROF'
    assert vars_['hr_unit_code'] == 'RD'
    assert vars_['hr_unit_name'] == '研發部'
    assert vars_['hr_is_unit_head'] == 'false'
    assert vars_['hr_direct_manager'] == hr_env.users['hr_user_b_000000000000000001'].secure_code
    assert vars_['hr_direct_manager_name'] == '主管 B'
    assert vars_['hr_direct_manager_unit'] == 'RD'
    assert vars_['hr_direct_manager_unit_name'] == '研發部'


def test_concurrent_and_acting_choose_earliest_effective_from(hr_env):
    hr_env.positions['a'].is_active = False
    early = hr_env.add_position(
        hr_env.users['hr_user_a_000000000000000001'],
        hr_env.titles['LEAD'],
        ptype=PositionType.ACTING,
        start=hr_env.older,
    )
    hr_env.add_position(
        hr_env.users['hr_user_a_000000000000000001'],
        hr_env.titles['MGR'],
        ptype=PositionType.CONCURRENT,
        start=hr_env.newer,
    )
    db.session.commit()

    _, vars_, _ = run_lookup({'var_prefix': 'hr'}, hr_env)

    assert vars_['hr_position_type'] == early.position_type
    assert vars_['hr_job_title_code'] == 'LEAD'
    assert vars_['hr_job_level_order'] == 300


def test_expired_primary_falls_back_to_active_concurrent(hr_env):
    hr_env.positions['a'].effective_until = hr_env.yesterday
    hr_env.add_position(
        hr_env.users['hr_user_a_000000000000000001'],
        hr_env.titles['LEAD'],
        ptype=PositionType.CONCURRENT,
        start=hr_env.newer,
    )
    db.session.commit()

    _, vars_, _ = run_lookup({'var_prefix': 'hr'}, hr_env)

    assert vars_['hr_position_type'] == 'CONCURRENT'
    assert vars_['hr_job_title_code'] == 'LEAD'
    assert vars_['hr_job_level_is_manager'] == 'true'


def test_no_effective_position_writes_found_false_and_empty_values(hr_env):
    hr_env.positions['a'].effective_until = hr_env.yesterday
    db.session.commit()

    resp, vars_, warnings = run_lookup({'var_prefix': 'hr', 'approval_category_code': 'TRAVEL', 'approver_mode': True}, hr_env)

    assert resp['status'] == 'success'
    assert vars_['hr_found'] == 'false'
    for key, value in vars_.items():
        if key not in ('hr_found', 'hr_approver_found'):
            assert value == ''
    assert vars_['hr_approver_found'] == 'false'
    assert warnings


def test_variable_target_points_to_manager_b(hr_env):
    resp, vars_, _ = run_lookup(
        {'target_source': 'variable', 'target_expr': '${v.target_user}', 'var_prefix': 'mgr'},
        hr_env,
        replacements={'${v.target_user}': hr_env.users['hr_user_b_000000000000000001'].secure_code},
    )

    assert resp['status'] == 'success'
    assert vars_['mgr_user_name'] == '主管 B'
    assert vars_['mgr_job_title_code'] == 'LEAD'
    assert vars_['mgr_direct_manager'] == hr_env.users['hr_user_c_000000000000000001'].secure_code
    assert vars_['mgr_direct_manager_unit'] == 'HQ'


def test_variable_target_from_other_org_is_not_found(hr_env):
    _, vars_, warnings = run_lookup(
        {'target_source': 'variable', 'target_expr': '${v.target_user}', 'var_prefix': 'hr'},
        hr_env,
        replacements={'${v.target_user}': hr_env.users['hr_user_x_000000000000000001'].secure_code},
    )

    assert vars_['hr_found'] == 'false'
    assert vars_['hr_user_code'] == ''
    assert warnings[0][1]['has_user'] is False


def test_approval_category_limit_zero_and_missing_category(hr_env):
    _, travel_vars, _ = run_lookup({'approval_category_code': 'TRAVEL'}, hr_env)
    _, meal_vars, _ = run_lookup({'approval_category_code': 'MEAL'}, hr_env)
    _, missing_vars, missing_warnings = run_lookup({'approval_category_code': 'NOPE'}, hr_env)

    assert travel_vars['hr_approval_limit'] == 10000
    assert meal_vars['hr_approval_limit'] == 0
    assert missing_vars['hr_approval_limit'] == ''
    assert any('核決類別' in msg for msg, _ in missing_warnings)


@pytest.mark.parametrize('amount,expected_code,expected_found', [
    ('50000', 'hr_user_b_000000000000000001', 'true'),
    ('500000', 'hr_user_c_000000000000000001', 'true'),
    ('5000000', '', 'false'),
])
def test_approver_mode_walks_manager_chain_by_amount(hr_env, amount, expected_code, expected_found):
    _, vars_, _ = run_lookup(
        {'approval_category_code': 'TRAVEL', 'approver_mode': True, 'amount_expr': '${f.amount}'},
        hr_env,
        replacements={'${f.amount}': amount},
    )

    assert vars_['hr_approver_found'] == expected_found
    assert vars_['hr_approver'] == expected_code
    if expected_code:
        assert vars_['hr_approver_level_code'] in ('L300', 'L500')
        assert vars_['hr_approver_unit'] in ('RD', 'HQ')


def test_approver_walks_up_when_manager_has_no_effective_position(hr_env):
    hr_env.positions['b'].effective_until = hr_env.yesterday
    db.session.commit()

    _, vars_, _ = run_lookup(
        {'approval_category_code': 'TRAVEL', 'approver_mode': True, 'amount_expr': '${f.amount}'},
        hr_env,
        replacements={'${f.amount}': '300000'},
    )

    assert vars_['hr_approver_found'] == 'true'
    assert vars_['hr_approver'] == hr_env.users['hr_user_c_000000000000000001'].secure_code
    assert vars_['hr_approver_unit'] == 'HQ'
    assert vars_['hr_approver_unit_name'] == '公司'


def test_approver_mode_bad_amount_returns_success_and_not_found(hr_env):
    resp, vars_, warnings = run_lookup(
        {'approval_category_code': 'TRAVEL', 'approver_mode': True, 'amount_expr': '${f.amount}'},
        hr_env,
        replacements={'${f.amount}': 'not-number'},
    )

    assert resp['status'] == 'success'
    assert vars_['hr_approver_found'] == 'false'
    assert vars_['hr_approver_name'] == ''
    assert any('金額解析失敗' in msg for msg, _ in warnings)


def test_invalid_var_prefix_falls_back_to_hr(hr_env):
    _, vars_, warnings = run_lookup({'var_prefix': '9x-'}, hr_env)

    assert 'hr_found' in vars_
    assert '9x-_found' not in vars_
    assert vars_['hr_user_name'] == '申請人 A'
    assert any('前綴不合法' in msg for msg, _ in warnings)


def test_direct_manager_skips_self_when_applicant_heads_own_unit(hr_env):
    _, b_vars, _ = run_lookup(
        {'target_source': 'variable', 'target_expr': '${v.target_user}', 'var_prefix': 'mgr'},
        hr_env,
        replacements={'${v.target_user}': hr_env.users['hr_user_b_000000000000000001'].secure_code},
    )
    _, c_vars, _ = run_lookup(
        {'target_source': 'variable', 'target_expr': '${v.target_user}', 'var_prefix': 'mgr'},
        hr_env,
        replacements={'${v.target_user}': hr_env.users['hr_user_c_000000000000000001'].secure_code},
    )

    assert b_vars['mgr_direct_manager'] == hr_env.users['hr_user_c_000000000000000001'].secure_code
    assert b_vars['mgr_direct_manager_unit'] == 'HQ'
    assert c_vars['mgr_direct_manager'] == ''
    assert c_vars['mgr_direct_manager_name'] == ''
    assert c_vars['mgr_direct_manager_unit'] == ''


def test_direct_manager_walks_up_on_vacancy(hr_env):
    UserRoleAssignment.query.filter_by(
        user_secure_code=hr_env.users['hr_user_b_000000000000000001'].secure_code,
        role_secure_code=hr_env.roles['manager'].secure_code,
        unit_secure_code=hr_env.units['rd'].secure_code,
    ).first().is_deleted = True
    db.session.commit()

    _, vars_with_parent, _ = run_lookup({'var_prefix': 'hr'}, hr_env)
    assert vars_with_parent['hr_direct_manager'] == hr_env.users['hr_user_c_000000000000000001'].secure_code
    assert vars_with_parent['hr_direct_manager_unit_name'] == '公司'

    UserRoleAssignment.query.filter_by(
        user_secure_code=hr_env.users['hr_user_c_000000000000000001'].secure_code,
        role_secure_code=hr_env.roles['manager'].secure_code,
        unit_secure_code=hr_env.units['hq'].secure_code,
    ).first().is_deleted = True
    db.session.commit()
    _, vars_without_manager, _ = run_lookup({'var_prefix': 'hr'}, hr_env)
    assert vars_without_manager['hr_found'] == 'true'
    assert vars_without_manager['hr_direct_manager'] == ''
    assert vars_without_manager['hr_direct_manager_unit_name'] == ''


def test_direct_manager_ignores_deputy_and_expired_assignment(hr_env):
    UserRoleAssignment.query.filter_by(
        user_secure_code=hr_env.users['hr_user_b_000000000000000001'].secure_code,
        role_secure_code=hr_env.roles['manager'].secure_code,
        unit_secure_code=hr_env.units['rd'].secure_code,
    ).first().is_deleted = True
    deputy = User(
        secure_code='hr_user_d_000000000000000001',
        org_secure_code=hr_env.org.secure_code,
        username='hr_user_d',
        email='hr_user_d@example.test',
        display_name='副主管 D',
        is_active=True,
        is_deleted=False,
    )
    deputy.set_password(secrets.token_urlsafe(16))
    expired = User(
        secure_code='hr_user_e_000000000000000001',
        org_secure_code=hr_env.org.secure_code,
        username='hr_user_e',
        email='hr_user_e@example.test',
        display_name='過期主管 E',
        is_active=True,
        is_deleted=False,
    )
    expired.set_password(secrets.token_urlsafe(16))
    db.session.add_all([deputy, expired])
    db.session.flush()
    hr_env.assign(deputy, hr_env.roles['deputy'], hr_env.units['rd'])
    hr_env.assign(expired, hr_env.roles['manager'], hr_env.units['rd'], valid_until=hr_env.yesterday)
    db.session.commit()

    _, vars_, _ = run_lookup({'var_prefix': 'hr'}, hr_env)

    assert vars_['hr_direct_manager'] == hr_env.users['hr_user_c_000000000000000001'].secure_code
    assert vars_['hr_direct_manager_name'] == '主管 C'


def test_direct_manager_prefers_unit_assignment_over_global(hr_env):
    global_manager = User(
        secure_code='hr_user_g_000000000000000001',
        org_secure_code=hr_env.org.secure_code,
        username='hr_user_g',
        email='hr_user_g@example.test',
        display_name='全企業主管 G',
        is_active=True,
        is_deleted=False,
    )
    global_manager.set_password(secrets.token_urlsafe(16))
    db.session.add(global_manager)
    db.session.flush()
    assignment = hr_env.assign(global_manager, hr_env.roles['manager'], None)
    assignment.assigned_at = datetime.combine(hr_env.today - timedelta(days=20), datetime.min.time())
    db.session.commit()

    _, vars_, _ = run_lookup({'var_prefix': 'hr'}, hr_env)

    assert vars_['hr_direct_manager'] == hr_env.users['hr_user_b_000000000000000001'].secure_code
    assert vars_['hr_direct_manager_unit'] == 'RD'

    UserRoleAssignment.query.filter_by(
        user_secure_code=hr_env.users['hr_user_b_000000000000000001'].secure_code,
        role_secure_code=hr_env.roles['manager'].secure_code,
        unit_secure_code=hr_env.units['rd'].secure_code,
    ).first().is_deleted = True
    db.session.commit()

    _, fallback_vars, _ = run_lookup({'var_prefix': 'hr'}, hr_env)

    assert fallback_vars['hr_direct_manager'] == global_manager.secure_code
    assert fallback_vars['hr_direct_manager_name'] == global_manager.display_name
    assert fallback_vars['hr_direct_manager_unit'] == 'RD'


def test_direct_manager_global_fallback_when_applicant_heads_own_unit(hr_env):
    global_manager = User(
        secure_code='hr_user_g_self_000000000000001',
        org_secure_code=hr_env.org.secure_code,
        username='hr_user_g_self',
        email='hr_user_g_self@example.test',
        display_name='全企業主管 G',
        is_active=True,
        is_deleted=False,
    )
    global_manager.set_password(secrets.token_urlsafe(16))
    db.session.add(global_manager)
    db.session.flush()
    assignment = hr_env.assign(global_manager, hr_env.roles['manager'], None)
    db.session.commit()

    _, vars_, _ = run_lookup(
        {'target_source': 'variable', 'target_expr': '${v.target_user}', 'var_prefix': 'mgr'},
        hr_env,
        replacements={'${v.target_user}': hr_env.users['hr_user_b_000000000000000001'].secure_code},
    )

    assert vars_['mgr_direct_manager'] == global_manager.secure_code
    assert vars_['mgr_direct_manager_unit'] == 'RD'

    assignment.is_deleted = True
    db.session.commit()
    _, parent_vars, _ = run_lookup(
        {'target_source': 'variable', 'target_expr': '${v.target_user}', 'var_prefix': 'mgr'},
        hr_env,
        replacements={'${v.target_user}': hr_env.users['hr_user_b_000000000000000001'].secure_code},
    )

    assert parent_vars['mgr_direct_manager'] == hr_env.users['hr_user_c_000000000000000001'].secure_code
    assert parent_vars['mgr_direct_manager_unit'] == 'HQ'


def test_resolve_role_holders_unit_only_excludes_global(hr_env):
    global_manager = User(
        secure_code='hr_user_g_unitonly_000000000001',
        org_secure_code=hr_env.org.secure_code,
        username='hr_user_g_unitonly',
        email='hr_user_g_unitonly@example.test',
        display_name='全企業主管 G',
        is_active=True,
        is_deleted=False,
    )
    global_manager.set_password(secrets.token_urlsafe(16))
    db.session.add(global_manager)
    db.session.flush()
    assignment = hr_env.assign(global_manager, hr_env.roles['manager'], None)
    assignment.assigned_at = datetime.combine(hr_env.today - timedelta(days=20), datetime.min.time())
    db.session.commit()

    default_holders = resolve_role_holders(
        hr_env.roles['manager'].secure_code,
        hr_env.org.secure_code,
        hr_env.units['rd'].secure_code,
        today=hr_env.today,
    )
    unit_holders = resolve_role_holders(
        hr_env.roles['manager'].secure_code,
        hr_env.org.secure_code,
        hr_env.units['rd'].secure_code,
        today=hr_env.today,
        unit_only=True,
    )
    all_holders = resolve_role_holders(
        hr_env.roles['manager'].secure_code,
        hr_env.org.secure_code,
        today=hr_env.today,
    )
    all_holders_unit_only = resolve_role_holders(
        hr_env.roles['manager'].secure_code,
        hr_env.org.secure_code,
        today=hr_env.today,
        unit_only=True,
    )

    assert global_manager.secure_code in default_holders
    assert hr_env.users['hr_user_b_000000000000000001'].secure_code in default_holders
    assert unit_holders == [hr_env.users['hr_user_b_000000000000000001'].secure_code]
    assert all_holders_unit_only == all_holders


def test_unit_resolved_from_primary_position_when_no_membership(hr_env):
    UserUnitMembership.query.filter_by(
        user_secure_code=hr_env.users['hr_user_a_000000000000000001'].secure_code,
        unit_secure_code=hr_env.units['rd'].secure_code,
    ).first().is_deleted = True
    db.session.commit()

    _, vars_, _ = run_lookup({'var_prefix': 'hr'}, hr_env)

    assert vars_['hr_unit_code'] == 'RD'
    assert vars_['hr_direct_manager'] == hr_env.users['hr_user_b_000000000000000001'].secure_code


def test_direct_manager_stays_within_org(hr_env):
    other_unit = OrganizationalUnit(
        org_secure_code=ORG2,
        code='RD2',
        name='其他研發部',
        unit_type=UnitType.DEPARTMENT,
        full_path='/其他研發部',
        level=1,
        is_active=True,
    )
    other_role = Role(
        org_secure_code=ORG2,
        code='DEPT_MANAGER',
        name='其他部門主管',
        role_type=RoleType.POSITION,
        scope_type='DEPARTMENT',
        is_active=True,
        is_deleted=False,
    )
    db.session.add_all([other_unit, other_role])
    db.session.flush()
    hr_env.assign(hr_env.users['hr_user_x_000000000000000001'], other_role, other_unit)
    db.session.commit()

    _, vars_, _ = run_lookup({'var_prefix': 'hr'}, hr_env)

    assert vars_['hr_direct_manager'] == hr_env.users['hr_user_b_000000000000000001'].secure_code
    assert list(iter_manager_chain(
        hr_env.users['hr_user_a_000000000000000001'].secure_code,
        ORG2,
        hr_env.today,
    )) == []


def test_approval_categories_endpoint_filters_current_org_and_active(admin_client, hr_env):
    response = admin_client.get('/beakplatform/api/workflows/data/approval-categories')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    codes = [item['code'] for item in payload['data']]
    assert codes == ['TRAVEL', 'MEAL']
    assert 'OLD' not in codes
    assert 'OTHER' not in codes
