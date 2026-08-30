# -*- coding: utf-8 -*-
"""Workflow node organization grant service tests."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db  # noqa: E402
from modules.form_workflow.models import (  # noqa: E402
    WorkflowNodeDefinition,
    WorkflowNodeOrgGrant,
)
from modules.form_workflow.services.node_grant_service import (  # noqa: E402
    find_unauthorized_node_types,
    is_node_allowed,
)


ORG_A = 'ORG_AAAAAAAAAAAAAAAAAAAA'
ORG_B = 'ORG_BBBBBBBBBBBBBBBBBBBB'


@pytest.fixture
def node_grant_data(app):
    db.session.add_all([
        WorkflowNodeDefinition(
            secure_code='node_normal_0000000000001',
            node_type='NormalNode',
            category='基本',
            display_name='一般節點',
            execution_handler='tests.NormalNode',
            org_restricted=False,
            is_active=True,
            is_deleted=False,
        ),
        WorkflowNodeDefinition(
            secure_code='node_os_00000000000000001',
            node_type='OsExecutor',
            category='系統',
            display_name='OS 命令',
            execution_handler='tests.OsExecutor',
            org_restricted=True,
            is_active=True,
            is_deleted=False,
        ),
        WorkflowNodeDefinition(
            secure_code='node_file_000000000000001',
            node_type='FileRead',
            category='系統',
            display_name='檔案讀取',
            execution_handler='tests.FileRead',
            org_restricted=True,
            is_active=True,
            is_deleted=False,
        ),
    ])
    db.session.commit()


def _grant(node_type='OsExecutor', org_secure_code=ORG_A, *, is_deleted=False):
    grant = WorkflowNodeOrgGrant(
        node_type=node_type,
        org_secure_code=org_secure_code,
        granted_by_name='test',
        is_deleted=is_deleted,
    )
    db.session.add(grant)
    db.session.commit()
    return grant


def test_non_restricted_node_is_always_allowed(node_grant_data):
    assert is_node_allowed('NormalNode', ORG_A) is True


def test_restricted_node_without_grant_is_denied(node_grant_data):
    assert is_node_allowed('OsExecutor', ORG_A) is False


def test_restricted_node_with_grant_is_allowed(node_grant_data):
    _grant()

    assert is_node_allowed('OsExecutor', ORG_A) is True


def test_soft_deleted_grant_is_denied(node_grant_data):
    _grant(is_deleted=True)

    assert is_node_allowed('OsExecutor', ORG_A) is False


def test_unknown_node_type_is_denied(node_grant_data):
    """定義不存在 → fail-closed（否則刪掉節點定義就能繞過授權閘門）。"""
    assert is_node_allowed('NoSuchNode', ORG_A) is False


def test_soft_deleted_node_definition_is_denied(node_grant_data):
    node_def = WorkflowNodeDefinition.query.filter_by(
        node_type='OsExecutor'
    ).first()
    node_def.is_deleted = True
    db.session.commit()
    _grant()

    assert is_node_allowed('OsExecutor', ORG_A) is False


@pytest.mark.parametrize('org_secure_code', [None, '', 123])
def test_missing_org_is_denied_for_restricted_node(node_grant_data, org_secure_code):
    assert is_node_allowed('OsExecutor', org_secure_code) is False


def test_find_unauthorized_node_types_for_ungranted_and_granted_org(node_grant_data):
    graph = {
        'nodes': [
            {'id': 'n1', 'type': 'Start'},
            {'id': 'n2', 'type': 'OsExecutor'},
            {'id': 'n3', 'type': 'NormalNode'},
        ],
        'edges': [],
    }

    assert find_unauthorized_node_types(graph, ORG_B) == ['OsExecutor']

    _grant(org_secure_code=ORG_B)

    assert find_unauthorized_node_types(graph, ORG_B) == []


@pytest.mark.parametrize('graph', [
    None,
    {},
    {'nodes': 'x'},
    {'nodes': [{'id': 'n1'}, {'id': 'n2', 'type': None}, 'bad']},
])
def test_find_unauthorized_node_types_ignores_malformed_input(node_grant_data, graph):
    assert find_unauthorized_node_types(graph, ORG_A) == []
