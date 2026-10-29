"""用戶編號永不回收：編輯頁換的新號碼要登記，已刪除帳號的號碼不可再發。"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db
from app.models import User, UserType
from app.models.user_numbering_rule import UsedUserNumber
from app.web.users import _check_employee_id_unique


PREFIX = '/beakplatform'


def _employee(org, secure_code, username, *, employee_id=None, deleted=False):
    user = User(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        username=username,
        email=f'{username}@{org.domain_name}',
        display_name=username,
        native_name=username,
        english_name=username,
        password_hash='test-password-hash',
        user_type=UserType.EMPLOYEE,
        is_active=not deleted,
        is_deleted=deleted,
        employee_id=employee_id,
    )
    db.session.add(user)
    db.session.flush()
    return user


def test_edit_page_records_new_employee_id(admin_client, test_org):
    target = _employee(test_org, 'empid_edit_target', 'empid-edit')
    db.session.commit()
    assert not UsedUserNumber.is_number_used(test_org.secure_code, 'EDIT-0001')

    response = admin_client.post(
        f'{PREFIX}/users/{target.secure_code}/edit',
        data={'native_name': '編號測試', 'english_name': 'Empid Edit', 'employee_id': 'EDIT-0001',
              'role': 'user', 'is_active': 'true'},
    )
    db.session.expire_all()

    assert response.status_code == 302
    assert User.query.filter_by(secure_code=target.secure_code).one().employee_id == 'EDIT-0001'
    used = UsedUserNumber.query.filter_by(org_secure_code=test_org.secure_code, number='EDIT-0001').one()
    assert used.user_secure_code == target.secure_code


def test_number_held_only_by_deleted_account_is_not_reissued(test_org):
    # 模擬修正前留下的資料：已刪除帳號身上有編號，但 used_user_numbers 沒登記
    _employee(test_org, 'empid_deleted_holder', 'empid-gone', employee_id='GONE-0001', deleted=True)
    db.session.commit()
    assert not UsedUserNumber.is_number_used(test_org.secure_code, 'GONE-0001')

    assert _check_employee_id_unique(test_org.secure_code, 'GONE-0001') is False
    assert _check_employee_id_unique(test_org.secure_code, 'FREE-0001') is True
