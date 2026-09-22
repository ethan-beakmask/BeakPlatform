"""緊急廣播：角色型對象比對與訊息內容跳脫。

兩個回歸：
1. `_user_in_target()` 曾讀不存在的 `user.roles`，只指定角色的廣播誰都收不到。
2. 廣播 message 以 innerHTML 渲染，變數替換進來的值必須跳脫，設計者自己寫的標籤保留。
"""
import sys
from pathlib import Path

import pytest

from app import db
from app.models import Role, UserRoleAssignment
from app.models.role import RoleLevel, RoleType, ScopeType
from app.api.broadcasts import _user_in_target

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _make_role(org_sc, code, sc):
    role = Role(
        secure_code=sc,
        org_secure_code=org_sc,
        code=code,
        name=code,
        role_type=RoleType.ROLE,
        scope_type=ScopeType.GLOBAL,
        role_level=RoleLevel.MEMBER,
        is_active=True,
    )
    db.session.add(role)
    db.session.flush()
    return role


def test_role_target_matches_active_assignment(app, test_org, test_user):
    role = _make_role(test_org.secure_code, 'SECURITY_STAFF', 'bcast_role_staff_sc')
    db.session.add(UserRoleAssignment(
        org_secure_code=test_org.secure_code,
        user_secure_code=test_user.secure_code,
        role_secure_code=role.secure_code,
    ))
    db.session.commit()

    target = {'type': 'specific', 'roles': ['SECURITY_STAFF'], 'departments': []}
    assert _user_in_target(test_user, target) is True
    # 角色 secure_code 也可比對
    assert _user_in_target(test_user, {'type': 'specific', 'roles': [role.secure_code]}) is True


def test_role_target_rejects_user_without_role(app, test_org, test_user):
    _make_role(test_org.secure_code, 'SOC_SUPERVISOR', 'bcast_role_sup_sc')
    db.session.commit()
    target = {'type': 'specific', 'roles': ['SOC_SUPERVISOR'], 'departments': []}
    assert _user_in_target(test_user, target) is False


def test_role_target_ignores_deleted_assignment(app, test_org, test_user):
    role = _make_role(test_org.secure_code, 'SECURITY_STAFF', 'bcast_role_staff_del_sc')
    db.session.add(UserRoleAssignment(
        org_secure_code=test_org.secure_code,
        user_secure_code=test_user.secure_code,
        role_secure_code=role.secure_code,
        is_deleted=True,
    ))
    db.session.commit()
    assert _user_in_target(test_user, {'type': 'specific', 'roles': ['SECURITY_STAFF']}) is False


@pytest.fixture
def handler_stub(app):
    from modules.form_workflow.services.node_handlers.alert_broadcast_handler import (
        AlertBroadcastHandler,
    )

    h = AlertBroadcastHandler.__new__(AlertBroadcastHandler)
    h.get_all_vars = lambda: {'note': '<i>斜體</i>'}
    h.get_form_field = lambda name: {'finding_title': '<img src=x onerror=alert(1)>'}.get(name)
    return h


def test_replace_variables_escapes_only_substituted_values(handler_stub):
    text = '案件 <b>${f.finding_title}</b>／${v.note}'
    out = handler_stub.replace_variables(text, escape_html=True)
    assert out == '案件 <b>&lt;img src=x onerror=alert(1)&gt;</b>／&lt;i&gt;斜體&lt;/i&gt;'


def test_replace_variables_default_keeps_raw(handler_stub):
    out = handler_stub.replace_variables('${v.note}')
    assert out == '<i>斜體</i>'
