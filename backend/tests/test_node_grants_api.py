# -*- coding: utf-8 -*-
"""Node grants platform API tests."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db  # noqa: E402
from app.models import Organization  # noqa: E402
from backend.tests.conftest import _login_user_directly  # noqa: E402
from modules.form_workflow.models import (  # noqa: E402
    WorkflowNodeDefinition,
    WorkflowNodeOrgGrant,
)


APP_PREFIX = '/beakplatform'


@pytest.fixture
def node_grants_data(app, test_org):
    org2 = Organization(
        secure_code='org_second_000000001',
        code='ORG2',
        name='Second Organization',
        domain_name='second.local',
        is_active=True,
        is_deleted=False,
    )
    deleted_org = Organization(
        secure_code='org_deleted_00000001',
        code='DELETED',
        name='Deleted Organization',
        domain_name='deleted.local',
        is_active=True,
        is_deleted=True,
    )
    db.session.add_all([
        org2,
        deleted_org,
        WorkflowNodeDefinition(
            secure_code='node_normal_api_00001',
            node_type='NormalNode',
            category='基本',
            display_name='一般節點',
            execution_handler='tests.NormalNode',
            org_restricted=False,
            is_active=True,
            is_deleted=False,
        ),
        WorkflowNodeDefinition(
            secure_code='node_os_api_00000001',
            node_type='OsExecutor',
            category='系統',
            display_name='OS 命令',
            execution_handler='tests.OsExecutor',
            org_restricted=True,
            is_active=True,
            is_deleted=False,
        ),
        WorkflowNodeDefinition(
            secure_code='node_file_api_000001',
            node_type='FileRead',
            category='系統',
            display_name='檔案讀取',
            execution_handler='tests.FileRead',
            org_restricted=True,
            is_active=False,
            is_deleted=False,
        ),
    ])
    db.session.commit()
    return {'org2': org2, 'deleted_org': deleted_org}


@pytest.fixture
def system_client(client, app, system_admin, test_org):
    _login_user_directly(client, app, system_admin, test_org)
    return client


def _post(client, path, payload):
    return client.post(f'{APP_PREFIX}{path}', json=payload)


def _active_grants(node_type, org_secure_code):
    return WorkflowNodeOrgGrant.query.filter(
        WorkflowNodeOrgGrant.node_type == node_type,
        WorkflowNodeOrgGrant.org_secure_code == org_secure_code,
        WorkflowNodeOrgGrant.is_deleted.is_(False),
    ).all()


def test_org_admin_cannot_get_matrix(admin_client, node_grants_data):
    # ORG_ADMIN 不應可存取 SYSTEM_ADMIN 專用平台授權管理 API。
    res = admin_client.get(f'{APP_PREFIX}/api/node-grants/matrix')

    assert res.status_code != 200


def test_system_admin_matrix_lists_restricted_nodes_including_inactive(
    system_client,
    node_grants_data,
):
    res = system_client.get(f'{APP_PREFIX}/api/node-grants/matrix')

    assert res.status_code == 200
    data = res.get_json()['data']
    node_types = {node['node_type']: node for node in data['nodes']}
    assert set(node_types) == {'FileRead', 'OsExecutor'}
    assert node_types['FileRead']['is_active'] is False
    assert node_types['OsExecutor']['is_active'] is True


def test_grant_is_idempotent(system_client, node_grants_data, test_org):
    first = _post(system_client, '/api/node-grants/grant', {
        'node_type': 'OsExecutor',
        'org_secure_code': test_org.secure_code,
    })
    second = _post(system_client, '/api/node-grants/grant', {
        'node_type': 'OsExecutor',
        'org_secure_code': test_org.secure_code,
    })

    assert first.status_code == 200
    assert first.get_json()['changed'] is True
    assert second.status_code == 200
    assert second.get_json()['changed'] is False
    assert len(_active_grants('OsExecutor', test_org.secure_code)) == 1


def test_revoke_then_grant_creates_new_history_row(system_client, node_grants_data, test_org):
    _post(system_client, '/api/node-grants/grant', {
        'node_type': 'OsExecutor',
        'org_secure_code': test_org.secure_code,
    })

    revoke = _post(system_client, '/api/node-grants/revoke', {
        'node_type': 'OsExecutor',
        'org_secure_code': test_org.secure_code,
    })
    assert revoke.status_code == 200
    assert revoke.get_json()['changed'] is True
    assert len(_active_grants('OsExecutor', test_org.secure_code)) == 0

    second_grant = _post(system_client, '/api/node-grants/grant', {
        'node_type': 'OsExecutor',
        'org_secure_code': test_org.secure_code,
    })
    assert second_grant.status_code == 200
    assert second_grant.get_json()['changed'] is True

    all_rows = WorkflowNodeOrgGrant.query.filter(
        WorkflowNodeOrgGrant.node_type == 'OsExecutor',
        WorkflowNodeOrgGrant.org_secure_code == test_org.secure_code,
    ).order_by(WorkflowNodeOrgGrant.created_at).all()
    assert len(all_rows) == 2
    assert sum(1 for row in all_rows if not row.is_deleted) == 1
    assert sum(1 for row in all_rows if row.is_deleted) == 1


def test_non_restricted_node_rejected(system_client, node_grants_data, test_org):
    res = _post(system_client, '/api/node-grants/grant', {
        'node_type': 'NormalNode',
        'org_secure_code': test_org.secure_code,
    })

    assert res.status_code == 400
    assert res.get_json()['error'] == 'node_not_restricted'


def test_missing_org_rejected(system_client, node_grants_data):
    res = _post(system_client, '/api/node-grants/grant', {
        'node_type': 'OsExecutor',
        'org_secure_code': 'NO_SUCH_ORG',
    })

    assert res.status_code == 400
    assert res.get_json()['error'] == 'org_not_found'


def test_invalid_payload_rejected(system_client, node_grants_data):
    res = _post(system_client, '/api/node-grants/grant', {
        'node_type': 'OsExecutor',
    })

    assert res.status_code == 400
    assert res.get_json()['error'] == 'invalid_payload'


def test_bulk_grant_all_active_orgs_and_rejects_unknown_action(
    system_client,
    node_grants_data,
    test_org,
):
    res = _post(system_client, '/api/node-grants/bulk', {
        'node_type': 'FileRead',
        'action': 'grant',
    })

    assert res.status_code == 200
    assert res.get_json()['changed_count'] == 2
    assert len(_active_grants('FileRead', test_org.secure_code)) == 1
    assert len(_active_grants('FileRead', node_grants_data['org2'].secure_code)) == 1
    assert len(_active_grants('FileRead', node_grants_data['deleted_org'].secure_code)) == 0

    bad = _post(system_client, '/api/node-grants/bulk', {
        'node_type': 'FileRead',
        'action': 'delete',
    })
    assert bad.status_code == 400
    assert bad.get_json()['error'] == 'invalid_payload'
