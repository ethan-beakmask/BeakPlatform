"""PF-241：平台權限出廠定義的守恆測試（2026-09-04）。

兩件事：
1. ResourceGateway 註冊（MODEL_RESOURCE_TYPE_MAP）的每一種 resource_type 都必須有
   read / create / update / delete 的出廠定義。缺了的話 PermissionService.check()
   先查定義、查不到就回 False，ORG_ADMIN 的 bypass 輪不到，fresh install 的該資源 API
   對每一種身分都 403（TENANT-02 雷二；BeakPlatform-VM 2026-09-04 實測 work_schedule）。
2. seed_system_permissions(force=False) 必須逐 code 補缺，不能「DB 已有任何系統權限
   就整批跳過」——否則既有環境跑 bootstrap_db.py --update 永遠補不到新增的定義。
"""
from app import db
from app.defaults.permission_defaults import seed_system_permissions
from app.models.permission import DEFAULT_PERMISSIONS, Permission
from app.models.permission_condition import DEFAULT_CONDITIONS, PermissionCondition
from app.security.resource_gateway import MODEL_RESOURCE_TYPE_MAP

CRUD_ACTIONS = ('read', 'create', 'update', 'delete')


def _default_codes():
    return [
        Permission.generate_code(p['resource_type'], p['action'])
        for p in DEFAULT_PERMISSIONS
    ]


def test_default_permission_codes_are_unique():
    codes = _default_codes()
    duplicated = sorted({c for c in codes if codes.count(c) > 1})
    assert not duplicated, f'出廠定義重複的 code：{duplicated}'


def test_every_gateway_resource_type_has_crud_defaults():
    codes = set(_default_codes())
    missing = sorted(
        f'{resource_type}:{action}'
        for resource_type in set(MODEL_RESOURCE_TYPE_MAP.values())
        for action in CRUD_ACTIONS
        if f'{resource_type}:{action}' not in codes
    )
    assert not missing, (
        '以下 ResourceGateway 資源型缺出廠 permission 定義，fresh install 會對所有身分 403：'
        f'{missing}。請補進 app/models/permission.py 的 DEFAULT_PERMISSIONS，'
        '不要改 MODEL_RESOURCE_TYPE_MAP。'
    )


def test_seed_fills_missing_codes_without_force(app):
    first = seed_system_permissions(force=False)
    assert first['permissions_created'] == len(DEFAULT_PERMISSIONS)
    assert first['conditions_created'] == len(DEFAULT_CONDITIONS)
    assert Permission.query.count() == len(DEFAULT_PERMISSIONS)

    # 模擬 2026-09-04 BeakPlatform-VM 實況：DB 已有其他系統權限，但缺 work_schedule:*
    removed = Permission.query.filter(
        Permission.code.like('work_schedule:%')
    ).delete(synchronize_session=False)
    db.session.commit()
    assert removed == 4

    again = seed_system_permissions(force=False)
    assert again['permissions_created'] == 4
    assert again['conditions_created'] == 0
    rebuilt = Permission.query.filter(Permission.code.like('work_schedule:%')).all()
    assert sorted(p.code for p in rebuilt) == [
        'work_schedule:create', 'work_schedule:delete',
        'work_schedule:read', 'work_schedule:update',
    ]
    assert all(p.is_system_permission and p.is_active for p in rebuilt)

    third = seed_system_permissions(force=False)
    assert third['permissions_created'] == 0
    assert third['conditions_created'] == 0
    assert Permission.query.count() == len(DEFAULT_PERMISSIONS)


def test_seed_without_force_does_not_touch_existing_rows(app):
    seed_system_permissions(force=False)
    row = Permission.query.filter_by(code='work_schedule:read').one()
    row.name = '自訂名稱'
    row.is_active = False
    db.session.commit()

    seed_system_permissions(force=False)
    row = Permission.query.filter_by(code='work_schedule:read').one()
    assert row.name == '自訂名稱'
    assert row.is_active is False


def test_seed_with_force_rebuilds_system_rows(app):
    seed_system_permissions(force=False)
    row = Permission.query.filter_by(code='work_schedule:read').one()
    row.name = '自訂名稱'
    db.session.commit()

    result = seed_system_permissions(force=True)
    assert result['permissions_created'] == len(DEFAULT_PERMISSIONS)
    assert Permission.query.filter_by(code='work_schedule:read').one().name == '檢視班表'
    assert PermissionCondition.query.count() == len(DEFAULT_CONDITIONS)
