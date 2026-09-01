import json
from datetime import date, datetime

from app import db
from app.models import Contract, ContractStatus
from app.services.module_access_service import ModuleAccessService
from app.utils.timezone import local_today


def _create_contract(org, start_date, end_date, modules=None):
    contract = Contract(
        org_secure_code=org.secure_code,
        contract_number=f'CTR-TZ-{org.secure_code[-8:]}-{start_date:%Y%m%d}',
        name='TZ contract',
        start_date=start_date,
        end_date=end_date,
        status=ContractStatus.ACTIVE,
        modules_config=json.dumps(modules or ['open_defense']),
        is_deleted=False,
    )
    db.session.add(contract)
    db.session.commit()
    db.session.refresh(contract)
    return contract


def test_local_today_uses_target_timezone_and_fallback():
    ref = datetime(2026, 9, 1, 19, 30)

    assert local_today('Asia/Taipei', ref=ref) == date(2026, 9, 2)
    assert local_today('UTC', ref=ref) == date(2026, 9, 1)
    assert local_today('Not/AZone', ref=ref) == date(2026, 9, 2)


def test_contract_status_uses_organization_timezone(test_org):
    test_org.set_setting('timezone', 'Pacific/Kiritimati')
    db.session.commit()
    kiritimati_today = test_org.local_today()

    contract = _create_contract(
        test_org,
        start_date=kiritimati_today,
        end_date=kiritimati_today,
    )

    assert contract.is_active is True
    assert contract.is_not_started is False

    test_org.set_setting('timezone', 'Pacific/Pago_Pago')
    db.session.commit()
    db.session.refresh(test_org)
    pago_pago_today = test_org.local_today()

    assert pago_pago_today != kiritimati_today
    assert contract.is_active is False
    assert contract.is_not_started is (pago_pago_today < kiritimati_today)


def test_module_access_contract_check_uses_user_organization_timezone(
    test_org,
    test_user,
):
    test_org.set_setting('timezone', 'Asia/Taipei')
    db.session.commit()
    org_today = test_org.local_today()
    _create_contract(
        test_org,
        start_date=org_today,
        end_date=org_today,
        modules=['open_defense'],
    )
    db.session.refresh(test_user)

    assert ModuleAccessService.check_module_contract(
        test_user,
        'open_defense',
    ) is True
