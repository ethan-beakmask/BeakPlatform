"""
Level 1 冒煙測試 - API GET 路由 500 偵測

目的：以三種身份 (SYSTEM_ADMIN, ORG_ADMIN, EMPLOYEE) 對所有 API GET 路由
     發送請求，確認不會回傳 500 Internal Server Error。

設計原則：
- 機械式執行，不依賴 AI 判斷
- 200/302/401/403/404 都算 PASS（預期行為）
- 500 是 FAIL（程式錯誤）
- 自動從 Flask url_map 發現路由
- 參數化路由用測試資料填充
- 每次請求後 rollback，防止 DB transaction 污染

手動執行：
    cd /opt/BeakPlatform && source venv/bin/activate && set -a && source .env && set +a
    cd backend && DATABASE_URL="postgresql://beakplatform:postgres123@localhost:5432/beakplatform_test" \\
        python -m pytest tests/test_smoke.py -v --tb=short

CI 執行：
    由 .forgejo/workflows/security-check.yml 的 test job 自動涵蓋
"""
import re
import pytest
from app import create_app, db
from app.models.user import User, UserType
from app.models.organization import Organization
from app.models.menu_item import MenuItem
from app.models.role import Role
from app.models.organizational_unit import OrganizationalUnit, UnitType


# ============================================================================
# 路由過濾
# ============================================================================

# 只測 API 路由（Web 路由的 template 渲染需要更完整的 fixture，留給 L2）
API_PREFIX = '/api/'

# 跳過的路由前綴
SKIP_PREFIXES = (
    '/api/form-',        # 模組路由，需要模組合約等前置條件
    '/api/spec-',        # 模組路由
    '/api/nocode-',      # 模組路由
)

# 已知問題路由（已記錄待修，排除以免遮蔽新迴歸）
# 修復後從此清單移除
KNOWN_ISSUES = {
    '/api/lookup/categories/<secure_code>',  # 需要 LookupCategory fixture
    '/api/lookup/categories/<secure_code>/items',  # 同上
}


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope='module')
def smoke_app():
    """Module-scoped app，冒煙測試共用一個 app 實例。"""
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture(scope='module')
def smoke_data(smoke_app):
    """建立冒煙測試所需的全部測試資料。"""
    with smoke_app.app_context():
        # --- 系統企業 (system.local) ---
        system_org = Organization(
            secure_code='smoke_system_local__',
            code='SYSTEM_LOCAL',
            name='System Local',
            domain_name='system.local',
            is_active=True,
            is_deleted=False,
        )
        db.session.add(system_org)

        # --- 測試企業 ---
        test_org = Organization(
            secure_code='smoke_test_org______',
            code='SMOKE_ORG',
            name='Smoke Test Org',
            domain_name='smoke.local',
            is_active=True,
            is_deleted=False,
        )
        db.session.add(test_org)
        db.session.flush()

        # --- 三種身份的用戶 ---
        system_admin = User(
            secure_code='smoke_sysadmin_____',
            org_secure_code=system_org.secure_code,
            username='smoke_sysadmin',
            email='sysadmin@smoke.example.com.zz',
            display_name='Smoke SysAdmin',
            user_type=UserType.SYSTEM_ADMIN,
            is_active=True,
            is_deleted=False,
        )
        system_admin.set_password('Test1234')

        org_admin = User(
            secure_code='smoke_orgadmin_____',
            org_secure_code=test_org.secure_code,
            username='smoke_orgadmin',
            email='orgadmin@smoke.example.com.zz',
            display_name='Smoke OrgAdmin',
            user_type=UserType.ORG_ADMIN,
            is_active=True,
            is_deleted=False,
        )
        org_admin.set_password('Test1234')

        employee = User(
            secure_code='smoke_employee_____',
            org_secure_code=test_org.secure_code,
            username='smoke_employee',
            email='employee@smoke.example.com.zz',
            display_name='Smoke Employee',
            user_type=UserType.EMPLOYEE,
            is_active=True,
            is_deleted=False,
        )
        employee.set_password('Test1234')

        db.session.add_all([system_admin, org_admin, employee])
        db.session.flush()

        # --- 選單項目 (屬於 system.local) ---
        menu_item = MenuItem(
            secure_code='smoke_menu_________',
            org_secure_code=system_org.secure_code,
            code='SMOKE_MENU',
            title='Smoke Menu',
            link_type='route',
            link_target='/smoke-test',
            display_order=0,
            depth=0,
            is_active=True,
            is_deleted=False,
        )
        db.session.add(menu_item)

        # --- 角色 ---
        role = Role(
            secure_code='smoke_role_________',
            org_secure_code=test_org.secure_code,
            code='SMOKE_ROLE',
            name='Smoke Role',
            role_type='ROLE',
            scope_type='GLOBAL',
            role_level='MEMBER',
            is_system_role=False,
            is_active=True,
            is_deleted=False,
        )
        db.session.add(role)

        # --- 部門 ---
        department = OrganizationalUnit(
            secure_code='smoke_dept_________',
            org_secure_code=test_org.secure_code,
            code='SMOKE_DEPT',
            name='Smoke Department',
            unit_type=UnitType.DEPARTMENT,
            is_active=True,
            is_deleted=False,
        )
        db.session.add(department)

        db.session.commit()

        data = {
            'system_org': system_org,
            'test_org': test_org,
            'system_admin': system_admin,
            'org_admin': org_admin,
            'employee': employee,
            # secure_code 快取（供路由參數替換）
            'secure_codes': {
                'user': employee.secure_code,
                'organization': test_org.secure_code,
                'menu': menu_item.secure_code,
                'role': role.secure_code,
                'unit': department.secure_code,
            },
        }
        yield data


def _login(client, user, org):
    """模擬登入。"""
    with client.session_transaction() as sess:
        sess['_user_id'] = user.get_id()
        sess['_fresh'] = True
        sess['org_secure_code'] = org.secure_code
        sess['org_domain'] = org.domain_name


# ============================================================================
# 路由發現與參數填充
# ============================================================================

def _discover_api_get_routes(app):
    """從 Flask url_map 中提取所有 API GET 路由。"""
    routes = []
    for rule in app.url_map.iter_rules():
        if 'GET' not in rule.methods:
            continue
        if not rule.rule.startswith(API_PREFIX):
            continue
        if rule.rule.startswith(SKIP_PREFIXES):
            continue
        if rule.rule in KNOWN_ISSUES:
            continue
        routes.append((rule.rule, rule.endpoint))
    return sorted(routes)


# 路由前綴 → 該前綴下 <secure_code> 對應的資源類型
_PREFIX_TO_RESOURCE = {
    '/api/users': 'user',
    '/api/menu': 'menu',
    '/api/roles': 'role',
    '/api/units': 'unit',
    '/api/organizations': 'organization',
    '/api/modules': 'organization',
    '/api/admin/work-schedules': 'organization',
    '/api/permissions': 'role',
    '/api/contracts': 'organization',
    '/api/duties': 'organization',
    '/api/admin/settings': 'organization',
    '/api/system-settings': 'organization',
    '/api/conglomerates': 'organization',
    '/api/module-access': 'organization',
    '/api/lookup': 'organization',
    '/api/pages': 'organization',
    '/api/enterprise-data': 'organization',
}


def _fill_params(rule_str, secure_codes):
    """
    將路由字串中的 <param> 替換為測試資料。
    無法填充的參數用固定假值替代（會得到 404，不會 500）。
    """
    resource_type = None
    best_len = 0
    for prefix, rtype in _PREFIX_TO_RESOURCE.items():
        if rule_str.startswith(prefix) and len(prefix) > best_len:
            resource_type = rtype
            best_len = len(prefix)

    sc = secure_codes.get(resource_type, 'smoke_fallback________')

    param_map = {
        'secure_code': sc,
        'user_secure_code': secure_codes.get('user', 'smoke_fallback________'),
        'role_secure_code': secure_codes.get('role', 'smoke_fallback________'),
        'menu_secure_code': secure_codes.get('menu', 'smoke_fallback________'),
        'unit_secure_code': secure_codes.get('unit', 'smoke_fallback________'),
        'org_secure_code': secure_codes.get('organization', 'smoke_fallback________'),
        'membership_secure_code': 'smoke_fallback________',
        'holiday_secure_code': 'smoke_fallback________',
        'contract_secure_code': 'smoke_fallback________',
        'domain_name': 'smoke.local',
        'org_code': 'SMOKE_ORG',
        'admin_code': 'smoke_fallback________',
        'module_code': 'SMOKE_MODULE',
        'category_code': 'SMOKE_CAT',
        'code': 'SMOKE_CODE',
        'id': '1',
        'hid': '1',
        'token': 'smoke_test_token',
        'position': 'manager',
    }

    result = rule_str
    for param, value in param_map.items():
        result = result.replace(f'<{param}>', str(value))

    # 處理未知參數（安全網）
    result = re.sub(r'<[^>]+>', 'smoke_fallback', result)
    return result


# ============================================================================
# 測試本體
# ============================================================================

class TestSmokeAPI:
    """
    Level 1 冒煙測試：所有 API GET 路由不應回 500。

    測試策略：
    - 以三種身份分別打所有 API GET 路由
    - 500 = 程式錯誤（FAIL）
    - 401/403/404/302 = 正常的權限控制（PASS）
    - 每次請求後 rollback，防止 transaction 污染
    """

    def _run_smoke(self, app, client, user, org, secure_codes, identity_name):
        """對所有 API GET 路由執行冒煙測試，回傳 500 的項目。"""
        _login(client, user, org)

        routes = _discover_api_get_routes(app)
        failures = []
        tested = 0

        for rule_str, endpoint in routes:
            url = _fill_params(rule_str, secure_codes)
            try:
                resp = client.get(url)
                tested += 1
                if resp.status_code == 500:
                    failures.append((url, endpoint))
            except Exception as e:
                failures.append((url, endpoint))
            finally:
                # 防止 500 導致的 transaction 壞掉影響後續請求
                db.session.rollback()

        return failures, tested

    def test_system_admin_no_500(self, smoke_app, smoke_data):
        """SYSTEM_ADMIN 存取所有 API GET 路由不應回 500"""
        client = smoke_app.test_client()
        failures, tested = self._run_smoke(
            smoke_app, client,
            smoke_data['system_admin'],
            smoke_data['system_org'],
            smoke_data['secure_codes'],
            'SYSTEM_ADMIN',
        )
        if failures:
            report = '\n'.join(f'  {url} ({ep})' for url, ep in failures)
            pytest.fail(
                f'SYSTEM_ADMIN: {len(failures)}/{tested} API route(s) returned 500:\n{report}'
            )

    def test_org_admin_no_500(self, smoke_app, smoke_data):
        """ORG_ADMIN 存取所有 API GET 路由不應回 500"""
        client = smoke_app.test_client()
        failures, tested = self._run_smoke(
            smoke_app, client,
            smoke_data['org_admin'],
            smoke_data['test_org'],
            smoke_data['secure_codes'],
            'ORG_ADMIN',
        )
        if failures:
            report = '\n'.join(f'  {url} ({ep})' for url, ep in failures)
            pytest.fail(
                f'ORG_ADMIN: {len(failures)}/{tested} API route(s) returned 500:\n{report}'
            )

    def test_employee_no_500(self, smoke_app, smoke_data):
        """EMPLOYEE 存取所有 API GET 路由不應回 500"""
        client = smoke_app.test_client()
        failures, tested = self._run_smoke(
            smoke_app, client,
            smoke_data['employee'],
            smoke_data['test_org'],
            smoke_data['secure_codes'],
            'EMPLOYEE',
        )
        if failures:
            report = '\n'.join(f'  {url} ({ep})' for url, ep in failures)
            pytest.fail(
                f'EMPLOYEE: {len(failures)}/{tested} API route(s) returned 500:\n{report}'
            )
