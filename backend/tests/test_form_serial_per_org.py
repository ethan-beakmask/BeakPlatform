"""Form serial_number per-org unique semantics."""
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
from modules.form_workflow.models import FwFormInstance
from modules.form_workflow.services.sequence_code_service import next_form_serial_number


ORG_A = 'test_org_form_serial_a'
ORG_B = 'test_org_form_serial_b'


def _require_form_instance_table():
    inspector = inspect(db.engine)
    if not inspector.has_table('fw_form_instances'):
        pytest.skip(
            'pytest app fixture did not create fw_form_instances; '
            'skip form serial_number per-org DB constraint tests'
        )


def _form_instance(
    org_secure_code: str,
    serial_number: str,
    *,
    org_form_seq: int | None = None,
    is_deleted: bool = False,
):
    return FwFormInstance(
        secure_code=uuid.uuid4().hex,
        org_secure_code=org_secure_code,
        form_template_secure_code='tmpl_form_serial_000000001',
        workflow_template_secure_code='wf_form_serial_0000000001',
        form_data={'field': 'value'},
        serial_number=serial_number,
        org_form_seq=org_form_seq,
        subject='Form serial per-org test',
        status='INITIAL',
        source_type='WEB',
        submitted_at=datetime.utcnow(),
        is_deleted=is_deleted,
    )


def test_serial_number_unique_per_org_allows_same_number_in_different_orgs(app, db_session):
    _require_form_instance_table()

    db.session.add(_form_instance(ORG_A, 'FORM-2608-00001'))
    db.session.add(_form_instance(ORG_B, 'FORM-2608-00001'))
    db.session.commit()

    assert db.session.query(FwFormInstance).count() == 2


def test_serial_number_unique_per_org_rejects_duplicate_in_same_org(app, db_session):
    _require_form_instance_table()

    db.session.add(_form_instance(ORG_A, 'FORM-2608-00002'))
    db.session.commit()

    db.session.add(_form_instance(ORG_A, 'FORM-2608-00002'))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_deleted_serial_number_does_not_reserve_number_in_same_org(app, db_session):
    _require_form_instance_table()

    db.session.add(_form_instance(ORG_A, 'FORM-2608-00003', is_deleted=True))
    db.session.commit()

    db.session.add(_form_instance(ORG_A, 'FORM-2608-00003'))
    db.session.commit()

    active_count = db.session.query(FwFormInstance).filter_by(
        org_secure_code=ORG_A,
        serial_number='FORM-2608-00003',
        is_deleted=False,
    ).count()
    assert active_count == 1


def test_next_form_serial_number_sequence_is_per_org(app, db_session):
    """直接呼叫唯一實作，確保序號池以 org_secure_code 為界。"""
    _require_form_instance_table()

    date_str = datetime.utcnow().strftime('%Y%m%d')
    for seq in range(1, 4):
        db.session.add(_form_instance(ORG_A, f'TEST-{date_str}-{seq:04d}'))
    db.session.commit()

    assert next_form_serial_number(
        org_secure_code=ORG_B,
        prefix='TEST-',
        date_str=date_str,
        digits=4,
    ) == f'TEST-{date_str}-0001'
    assert next_form_serial_number(
        org_secure_code=ORG_A,
        prefix='TEST-',
        date_str=date_str,
        digits=4,
    ) == f'TEST-{date_str}-0004'


def test_form_fallback_serial_number_keeps_five_digit_format(app, db_session):
    _require_form_instance_table()

    date_str = datetime.utcnow().strftime('%Y%m%d')

    assert next_form_serial_number(
        org_secure_code=ORG_A,
        prefix='FORM-',
        date_str=date_str,
        digits=5,
    ) == f'FORM-{date_str}-00001'


def test_form_fallback_serial_number_counts_legacy_variable_width_suffix(app, db_session):
    _require_form_instance_table()

    date_str = datetime.utcnow().strftime('%Y%m%d')
    db.session.add(_form_instance(ORG_A, f'FORM-{date_str}-9'))
    db.session.commit()

    assert next_form_serial_number(
        org_secure_code=ORG_A,
        prefix='FORM-',
        date_str=date_str,
        digits=5,
    ) == f'FORM-{date_str}-00010'


def test_next_form_serial_number_requires_org_fail_closed(app, db_session):
    _require_form_instance_table()

    with pytest.raises(ValueError):
        next_form_serial_number(
            org_secure_code='',
            prefix='TEST-',
            date_str='20260816',
            digits=4,
        )


def test_org_form_seq_unique_per_org_and_allows_nulls(app, db_session):
    _require_form_instance_table()

    db.session.add(_form_instance(ORG_A, 'SEQ-A-1', org_form_seq=1))
    db.session.add(_form_instance(ORG_B, 'SEQ-B-1', org_form_seq=1))
    db.session.add(_form_instance(ORG_A, 'SEQ-A-NULL-1', org_form_seq=None))
    db.session.add(_form_instance(ORG_A, 'SEQ-A-NULL-2', org_form_seq=None))
    db.session.commit()

    db.session.add(_form_instance(ORG_A, 'SEQ-A-2', org_form_seq=1))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()
