from pathlib import Path
import sys

import pytest
from sqlalchemy import inspect

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db
from app.models.api_key import ApiKey
from modules.form_workflow.models import FwFormTemplate, FwPublishedFormWorkflow
from modules.form_workflow.services.trigger_scope_service import list_triggerable_forms


ORG_SC = 'test_org_00000000001'
SECURITY_CATEGORY_SC = 'CAT_SECURITY_scope_test'
GENERAL_CATEGORY_SC = 'CAT_GENERAL_scope_test'


def _require_trigger_scope_tables():
    required = {
        'api_keys',
        'fw_form_templates',
        'fw_published_form_workflows',
    }
    inspector = inspect(db.engine)
    missing = sorted(table for table in required if not inspector.has_table(table))
    if missing:
        pytest.skip(
            'trigger scope tests require tables: ' + ', '.join(missing)
        )


def _schema():
    keys = [
        'severity_id',
        'actor_ip',
        'source_system',
        'finding_rule_id',
    ]
    return {'components': [{'type': 'textfield', 'key': key, 'input': True} for key in keys]}


def _published_fixture(category_sc):
    suffix = category_sc.replace('CAT_', '').lower()
    template = FwFormTemplate(
        secure_code=f'tmpl_{suffix}',
        org_secure_code=ORG_SC,
        code=f'FORM_{suffix}',
        name=f'Trigger Form {suffix}',
        category_secure_code=category_sc,
        schema=_schema(),
        version='AA',
        is_published=True,
        is_active=True,
    )
    db.session.add(template)
    db.session.flush()

    published = FwPublishedFormWorkflow(
        secure_code=f'pub_{suffix}',
        org_secure_code=ORG_SC,
        source_mapping_id=1,
        source_mapping_secure_code=f'map_{suffix}',
        source_form_template_id=template.id,
        source_form_template_secure_code=template.secure_code,
        source_form_version='AA',
        source_form_revision=1,
        source_workflow_template_id=1,
        source_workflow_template_secure_code=f'wf_tmpl_{suffix}',
        source_workflow_version='AA',
        source_workflow_revision=1,
        publish_version=1,
        name=f'Published Trigger Form {suffix}',
        form_snapshot={
            'name': template.name,
            'code': template.code,
            'schema': _schema(),
            'builder_config': {},
        },
        workflow_snapshot={
            'name': 'WF',
            'graph': {'nodes': [{'id': 'node-Start-1', 'type': 'Start'}], 'edges': []},
        },
        status='Published',
    )
    db.session.add(published)
    db.session.flush()
    return template, published


def _api_key_fixture():
    key = ApiKey(
        secure_code='api_key_trigger_scope_test',
        org_secure_code=ORG_SC,
        key_id='ak_trigger_scope_test',
        name='Trigger Scope Test',
        secret_ciphertext=b'x',
        secret_file_nonce=b'x',
        secret_wrapped_dek='x',
        secret_dek_nonce='x',
        secret_encryption_key_sc='x',
        scopes={'form_category': [SECURITY_CATEGORY_SC, GENERAL_CATEGORY_SC]},
        status='active',
    )
    db.session.add(key)
    db.session.flush()
    return key


def test_list_triggerable_forms_marks_security_category(app):
    with app.app_context():
        _require_trigger_scope_tables()
        _published_fixture(SECURITY_CATEGORY_SC)
        _published_fixture(GENERAL_CATEGORY_SC)
        api_key = _api_key_fixture()
        db.session.commit()

        items = list_triggerable_forms(api_key, ORG_SC)

    by_code = {item['form_code']: item for item in items}
    assert by_code['FORM_security_scope_test']['is_security'] is True
    assert by_code['FORM_general_scope_test']['is_security'] is False
    assert by_code['FORM_security_scope_test']['published_secure_code'] == 'pub_security_scope_test'
    assert by_code['FORM_security_scope_test']['field_keys'] == [
        'actor_ip',
        'finding_rule_id',
        'severity_id',
        'source_system',
    ]
