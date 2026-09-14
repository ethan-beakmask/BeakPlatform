"""PF-116 execution_code per-org unique semantics."""
from __future__ import annotations

import sys
import uuid
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db
from modules.form_workflow.models import FwWorkflowInstance
from modules.form_workflow.services.sequence_code_service import next_execution_code


ORG_A = 'test_org_exec_code_a'
ORG_B = 'test_org_exec_code_b'


def _require_workflow_instance_table():
    inspector = inspect(db.engine)
    if not inspector.has_table('fw_workflow_instances'):
        pytest.skip(
            'PF-116: pytest app fixture did not create fw_workflow_instances; '
            'skip execution_code per-org DB constraint tests'
        )


def _workflow_instance(org_secure_code: str, execution_code: str, *, is_deleted: bool = False):
    return FwWorkflowInstance(
        secure_code=uuid.uuid4().hex,
        org_secure_code=org_secure_code,
        workflow_template_secure_code=f'wf_{org_secure_code}',
        execution_code=execution_code,
        status='RUNNING',
        is_deleted=is_deleted,
    )


def test_execution_code_unique_per_org_allows_same_code_in_different_orgs(app, db_session):
    _require_workflow_instance_table()

    db.session.add(_workflow_instance(ORG_A, 'OD-20260816-0001'))
    db.session.add(_workflow_instance(ORG_B, 'OD-20260816-0001'))
    db.session.commit()

    assert db.session.query(FwWorkflowInstance).count() == 2


def test_execution_code_unique_per_org_rejects_duplicate_in_same_org(app, db_session):
    _require_workflow_instance_table()

    db.session.add(_workflow_instance(ORG_A, 'OD-20260816-0002'))
    db.session.commit()

    db.session.add(_workflow_instance(ORG_A, 'OD-20260816-0002'))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_deleted_execution_code_does_not_reserve_code_in_same_org(app, db_session):
    _require_workflow_instance_table()

    db.session.add(_workflow_instance(ORG_A, 'OD-20260816-0003', is_deleted=True))
    db.session.commit()

    db.session.add(_workflow_instance(ORG_A, 'OD-20260816-0003'))
    db.session.commit()

    active_count = db.session.query(FwWorkflowInstance).filter_by(
        org_secure_code=ORG_A,
        execution_code='OD-20260816-0003',
        is_deleted=False,
    ).count()
    assert active_count == 1


def test_next_execution_code_sequence_is_per_org(app, db_session):
    """序號池以企業為界：A 已用到 0003 時，B 仍從 0001 開始。

    直接呼叫唯一實作 next_execution_code()，不要複製它的 SQL 到測試裡——
    複製一份會讓「實作把 org 過濾拿掉」這種回歸完全測不出來。
    """
    _require_workflow_instance_table()

    date_str = datetime.utcnow().strftime('%Y%m%d')
    for seq in range(1, 4):
        db.session.add(_workflow_instance(ORG_A, f'OD-{date_str}-{seq:04d}'))
    db.session.commit()

    assert next_execution_code(
        org_secure_code=ORG_B, prefix='OD-', date_str=date_str,
    ) == f'OD-{date_str}-0001'
    assert next_execution_code(
        org_secure_code=ORG_A, prefix='OD-', date_str=date_str,
    ) == f'OD-{date_str}-0004'


def test_next_execution_code_pool_is_separated_by_prefix(app, db_session):
    """同企業同日的不同 prefix 各自計數（OD- 用到 0003 不影響 PROC-）。"""
    _require_workflow_instance_table()

    date_str = datetime.utcnow().strftime('%Y%m%d')
    for seq in range(1, 4):
        db.session.add(_workflow_instance(ORG_A, f'OD-{date_str}-{seq:04d}'))
    db.session.commit()

    assert next_execution_code(
        org_secure_code=ORG_A, prefix='PROC-', date_str=date_str,
    ) == f'PROC-{date_str}-0001'


def test_next_execution_code_requires_org_fail_closed(app, db_session):
    """org 為空時拒絕配號，不可靜默落回全域序號池。"""
    _require_workflow_instance_table()

    with pytest.raises(ValueError):
        next_execution_code(
            org_secure_code='', prefix='OD-', date_str='20260816',
        )
