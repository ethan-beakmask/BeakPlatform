"""企業專屬資料庫 façade 的 fail-closed 守門測試（PF-256）。

這些測試守的是**不可逆動作**：`drop_orphan_database()` 與 `drop_orphan_roles()`
真的會 DROP DATABASE / DROP ROLE。所以重點不是「刪得成功嗎」，
而是「不該刪的時候有沒有拒絕」——真正執行刪除的路徑不在單元測試裡驗
（需要一個可拋棄的實體庫，見 /opt/tmp/verify/20260912-pf256.log 的瀏覽器驗收）。
"""
import pytest

from app import db
from app.models.organization import Organization
from app.services import org_database_service as svc


@pytest.fixture
def orphan_free_org(app):
    """一家 id 已知的企業，用來測「企業還在就拒絕刪它的庫與角色」。"""
    org = Organization(
        secure_code='pf256_org_000000001',
        code='PF256_ORG',
        name='PF256 Org',
        domain_name='pf256.local',
        is_active=True,
        is_deleted=False,
    )
    db.session.add(org)
    db.session.commit()
    db.session.refresh(org)
    return org


class TestDropOrphanDatabaseGuards:
    def test_rejects_invalid_name(self, app):
        for name in ('', 'postgres', 'org_', 'org_1; DROP DATABASE x', 'beakplatform_dev'):
            result = svc.drop_orphan_database(name)
            assert result['ok'] is False, name
            assert result['error']

    def test_rejects_when_database_absent(self, app):
        # id 極大，實體庫不可能存在
        result = svc.drop_orphan_database('org_999999999')
        assert result['ok'] is False
        assert result['error']

    def test_rejects_when_org_still_exists(self, app, orphan_free_org, monkeypatch):
        """企業還在（含軟刪除）就不是孤兒，即使實體庫真的存在也要拒絕。"""
        monkeypatch.setattr(svc, '_pg_database_exists', lambda name: True)
        result = svc.drop_orphan_database(f'org_{orphan_free_org.id}')
        assert result['ok'] is False
        assert result['error']

    def test_rejects_soft_deleted_org(self, app, orphan_free_org, monkeypatch):
        """軟刪除的企業還沒硬刪，它的庫不是孤兒。"""
        orphan_free_org.is_deleted = True
        db.session.commit()
        monkeypatch.setattr(svc, '_pg_database_exists', lambda name: True)
        result = svc.drop_orphan_database(f'org_{orphan_free_org.id}')
        assert result['ok'] is False

    def test_rejects_when_registration_exists(self, app, monkeypatch):
        """登記還在就不是孤兒（企業可能剛被硬刪到一半）。"""
        monkeypatch.setattr(svc, '_pg_database_exists', lambda name: True)
        monkeypatch.setattr(svc, '_registered_org_db_exists', lambda name: True)
        result = svc.drop_orphan_database('org_999999998')
        assert result['ok'] is False


class TestDropOrphanRolesGuards:
    def test_empty_input(self, app):
        assert svc.drop_orphan_roles([]) == {'roles_dropped': [], 'errors': []}

    def test_rejects_invalid_role_names(self, app):
        result = svc.drop_orphan_roles(['postgres', 'beakplatform', 'bfadmin_', 'bfadmin_1x'])
        assert result['roles_dropped'] == []
        assert len(result['errors']) == 4

    def test_rejects_when_org_still_exists(self, app, orphan_free_org, monkeypatch):
        monkeypatch.setattr(svc, '_pg_database_exists', lambda name: False)
        result = svc.drop_orphan_roles([f'bfadmin_{orphan_free_org.id}'])
        assert result['roles_dropped'] == []
        assert result['errors']

    def test_rejects_when_database_still_exists(self, app, monkeypatch):
        """庫還在就先別動角色——角色是 owner，刪了庫就刪不掉。"""
        monkeypatch.setattr(svc, '_pg_database_exists', lambda name: True)
        result = svc.drop_orphan_roles(['bfadmin_999999997'])
        assert result['roles_dropped'] == []
        assert result['errors']


class TestScanHealth:
    def test_shape_and_status(self, app, orphan_free_org):
        result = svc.scan_org_database_health()
        assert set(result) == {
            'provisioning', 'orgs', 'orphan_databases', 'orphan_roles', 'summary'
        }
        assert set(result['summary']) == {
            'total', 'ok', 'abnormal', 'orphan_databases', 'orphan_roles'
        }
        rows = {row['org_secure_code']: row for row in result['orgs']}
        assert orphan_free_org.secure_code in rows
        row = rows[orphan_free_org.secure_code]
        # 測試庫沒有任何企業專屬資料庫，所以一定是 missing_registration
        assert row['status'] == 'missing_registration'
        assert row['registered'] is False
        assert row['db_name'] == f'org_{orphan_free_org.id}'
        assert result['summary']['total'] == len(result['orgs'])
        assert result['summary']['ok'] + result['summary']['abnormal'] == result['summary']['total']

    def test_soft_deleted_org_not_listed(self, app, orphan_free_org):
        orphan_free_org.is_deleted = True
        db.session.commit()
        result = svc.scan_org_database_health()
        codes = {row['org_secure_code'] for row in result['orgs']}
        assert orphan_free_org.secure_code not in codes
        # 但軟刪除的企業仍然「存在」，所以它的庫不會被算成孤兒
        orphan_names = {item['db_name'] for item in result['orphan_databases']}
        assert f'org_{orphan_free_org.id}' not in orphan_names


class TestDropOrphanDatabaseFailureReporting:
    """刪不掉時要把「為什麼」送出去（PF-265）。

    `drop_org_database()` 早就把權限訊息放進 `errors` 並算好 `manual_command`，
    但 façade 舊版只回 `ok` 與原 dict，沒有 `error` 這個鍵，端點於是必然
    落到通用的「刪除孤兒資料庫失敗」，使用者看不出要找 superuser 手動刪。
    """

    @staticmethod
    def _pass_orphan_guards(monkeypatch):
        monkeypatch.setattr(svc, '_pg_database_exists', lambda name: True)
        monkeypatch.setattr(svc, '_registered_org_db_exists', lambda name: False)

    def test_surfaces_permission_error_and_manual_command(self, app, monkeypatch):
        self._pass_orphan_guards(monkeypatch)

        def fake_drop(db_name, admin_dsn=None, drop_roles=True, org_id=None):
            return {
                'db_name': db_name,
                'db_dropped': False,
                'db_existed': True,
                'roles_dropped': [],
                'errors': [{'resource': db_name, 'error': 'must be owner of database org_999999996'}],
                'manual_command': f'sudo -u postgres dropdb {db_name}',
            }

        monkeypatch.setattr(
            'modules.form_workflow.services.sql_sync.org_db_manager.drop_org_database',
            fake_drop,
        )
        result = svc.drop_orphan_database('org_999999996')
        assert result['ok'] is False
        assert 'must be owner of database' in result['error']
        assert result['manual_command'] == 'sudo -u postgres dropdb org_999999996'

    def test_success_path_keeps_ok(self, app, monkeypatch):
        self._pass_orphan_guards(monkeypatch)

        def fake_drop(db_name, admin_dsn=None, drop_roles=True, org_id=None):
            return {
                'db_name': db_name,
                'db_dropped': True,
                'db_existed': True,
                'roles_dropped': ['bfadmin_999999995', 'bfsync_999999995'],
                'errors': [],
                'manual_command': None,
            }

        monkeypatch.setattr(
            'modules.form_workflow.services.sql_sync.org_db_manager.drop_org_database',
            fake_drop,
        )
        result = svc.drop_orphan_database('org_999999995')
        assert result['ok'] is True
        assert result.get('error') is None
