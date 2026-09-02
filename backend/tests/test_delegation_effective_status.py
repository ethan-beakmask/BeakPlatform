"""代理授權效期改為依企業當地日期即時判定（2026-09-02）。

修前 `Delegation.is_active` 要求 `status == ACTIVE`，而 status 只在儲存時計算、
沒有排程更新，提前建立的授權到了開始日永遠不會生效。修後 `is_active` /
`effective_status` 只看日期（撤銷除外），task_authorizer 也跟著吃到。
"""
from datetime import timedelta

from app import db
from app.models.delegation import Delegation, DelegationStatus, DelegationType


def _create_delegation(org, delegator, delegate, start, end,
                       stored_status=DelegationStatus.PENDING,
                       delegation_type=DelegationType.FULL):
    d = Delegation(
        org_secure_code=org.secure_code,
        delegator_secure_code=delegator.secure_code,
        delegate_secure_code=delegate.secure_code,
        delegation_type=delegation_type,
        status=stored_status,
        effective_from=start,
        effective_until=end,
        created_by='test',
    )
    db.session.add(d)
    db.session.commit()
    db.session.refresh(d)
    return d


def test_stored_pending_becomes_active_by_date(test_org, test_user, test_admin):
    today = test_org.local_today()
    d = _create_delegation(test_org, test_admin, test_user, today, today,
                           stored_status=DelegationStatus.PENDING)

    assert d.status == DelegationStatus.PENDING          # 快照沒人更新
    assert d.effective_status == DelegationStatus.ACTIVE  # 畫面與授權看這個
    assert d.is_active is True
    assert d.to_dict()['status'] == DelegationStatus.ACTIVE


def test_future_and_past_ranges(test_org, test_user, test_admin):
    today = test_org.local_today()
    future = _create_delegation(test_org, test_admin, test_user,
                                today + timedelta(days=1), today + timedelta(days=2))
    past = _create_delegation(test_org, test_admin, test_user,
                              today - timedelta(days=2), today - timedelta(days=1),
                              stored_status=DelegationStatus.ACTIVE)

    assert future.effective_status == DelegationStatus.PENDING
    assert future.is_active is False
    assert past.effective_status == DelegationStatus.EXPIRED   # 快照仍是 ACTIVE 也判過期
    assert past.is_active is False
    assert past.days_remaining == 0


def test_revoked_wins_over_dates(test_org, test_user, test_admin):
    today = test_org.local_today()
    d = _create_delegation(test_org, test_admin, test_user, today, today)
    d.revoke('tester', 'done')
    db.session.commit()

    assert d.effective_status == DelegationStatus.REVOKED
    assert d.is_active is False
    d.check_and_update_status()
    assert d.status == DelegationStatus.REVOKED


def test_uses_organization_timezone(test_org, test_user, test_admin):
    test_org.set_setting('timezone', 'Pacific/Kiritimati')
    db.session.commit()
    kiritimati_today = test_org.local_today()
    d = _create_delegation(test_org, test_admin, test_user,
                           kiritimati_today, kiritimati_today)
    assert d.is_active is True

    test_org.set_setting('timezone', 'Pacific/Pago_Pago')
    db.session.commit()
    db.session.refresh(test_org)
    assert test_org.local_today() != kiritimati_today
    assert d.is_active is False


def test_task_authorizer_sees_date_active_delegation(test_org, test_user, test_admin):
    from modules.form_workflow.services.task_authorizer import get_delegated_identities

    today = test_org.local_today()
    _create_delegation(test_org, test_admin, test_user, today, today,
                       stored_status=DelegationStatus.PENDING)
    # 限額代理填了金額：依 PF-71 現況不採計
    _create_delegation(test_org, test_admin, test_user, today, today,
                       delegation_type=DelegationType.APPROVAL)

    identities = get_delegated_identities(test_user.secure_code, test_org.secure_code)
    assert set(identities.keys()) == {test_admin.secure_code}
