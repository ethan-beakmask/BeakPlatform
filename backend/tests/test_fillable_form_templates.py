"""
PF-160 授權表單清單：list_fillable_published_templates()

這支是「你能手動填的表單，才能申請 key 去自動填」的唯一判定，
API Key 申請單的選項來源與 ApiKeyIssue 核發前的重驗都走它，
判定放寬等於讓申請人取得填不到的表單的自動化能力。
"""
import os
from datetime import datetime, timedelta

os.environ.setdefault("SYSTEM_ORG_CODE", "system.local")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app import db  # noqa: E402


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


def test_security_category_template_is_excluded(app, test_org, test_user):
    org_sc = test_org.secure_code
    _publish(org_sc, 'tpl_sec', 'map_sec', '資安案件表單',
             category_sc='CAT_SECURITY_f5bc0629')
    _grant_user(org_sc, 'map_sec', test_user.secure_code, 'perm_sec')

    # 資安表單由 intake/處置中心承接，不是手動填寫的對象；
    # 授權它等於讓外部 key 打進資安案件鏈路
    assert _codes(test_user, org_sc) == []


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
