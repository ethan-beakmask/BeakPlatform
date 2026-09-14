# -*- coding: utf-8 -*-
"""Sys notification node authorization and tenant isolation tests."""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

os.environ.setdefault('SYSTEM_ORG_CODE', 'system.local')
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db  # noqa: E402
from app.models import Organization, RecipientGroup, SmtpConfig, TelegramConfig  # noqa: E402
from backend.app.constants import SYSTEM_ORG_CODE  # noqa: E402
from modules.form_workflow.models import WorkflowNodeDefinition  # noqa: E402
from modules.form_workflow.services.node_handlers.email_handler import EmailHandler  # noqa: E402
from modules.form_workflow.services.node_handlers.sys_emailrelay_handler import SysEmailRelayHandler  # noqa: E402
from modules.form_workflow.services.node_handlers.telegram_handler import TelegramHandler  # noqa: E402


ORG_A = 'ORG_AAAAAAAAAAAAAAAAAAAA'
ORG_B = 'ORG_BBBBBBBBBBBBBBBBBBBB'


@pytest.fixture
def tenant_orgs(app):
    db.session.add_all([
        Organization(
            secure_code=SYSTEM_ORG_CODE,
            code='SYSTEM',
            name='System Organization',
            domain_name='system.local',
            is_system_org=True,
            is_active=True,
            is_deleted=False,
        ),
        Organization(
            secure_code=ORG_A,
            code='ORGA',
            name='Organization A',
            domain_name='a.local',
            is_active=True,
            is_deleted=False,
        ),
        Organization(
            secure_code=ORG_B,
            code='ORGB',
            name='Organization B',
            domain_name='b.local',
            is_active=True,
            is_deleted=False,
        ),
    ])
    db.session.commit()


def _queue(org_code, node_type='SysTelegram', config=None):
    return SimpleNamespace(
        id=1,
        secure_code='queue_test_000000000000001',
        node_id='node-1',
        node_type=node_type,
        node_config=config or {},
        org_secure_code=org_code,
        workflow_instance_secure_code='wf_test_00000000000000001',
        status='PENDING',
        retry_count=0,
        process_id=None,
    )


def _telegram_config(org_code, secure_code, token):
    config = TelegramConfig(
        secure_code=secure_code,
        org_secure_code=org_code,
        name=secure_code,
        bot_token=token,
        channels=json.dumps({'alerts': f'chat-{secure_code}'}),
        is_active=True,
        is_deleted=False,
    )
    db.session.add(config)
    db.session.commit()
    return config


def _smtp_config(org_code, secure_code, host, *, is_default=False, priority=100):
    config = SmtpConfig(
        secure_code=secure_code,
        org_secure_code=org_code,
        name=secure_code,
        smtp_host=host,
        smtp_port=587,
        use_tls=True,
        use_ssl=False,
        username=f'{secure_code}@example.test',
        from_email=f'{secure_code}@example.test',
        from_name=secure_code,
        provider_type='generic',
        priority=priority,
        is_default=is_default,
        is_active=True,
        is_deleted=False,
    )
    db.session.add(config)
    db.session.commit()
    return config


def test_telegram_config_from_other_org_is_hidden(tenant_orgs):
    _telegram_config(ORG_A, 'tg_org_a_000000000000000001', 'token-a')
    handler = TelegramHandler(_queue(
        ORG_B,
        config={
            'config_id': 'tg_org_a_000000000000000001',
            'channel_name': 'alerts',
        },
    ))

    with pytest.raises(ValueError) as exc_info:
        handler._resolve_telegram_config()

    assert '找不到 Telegram 設定' in str(exc_info.value)
    assert 'tg_org_a_000000000000000001' in str(exc_info.value)


def test_telegram_config_from_system_org_is_shared(tenant_orgs):
    _telegram_config(SYSTEM_ORG_CODE, 'tg_system_0000000000000001', 'system-token')
    handler = TelegramHandler(_queue(
        ORG_B,
        config={
            'config_id': 'tg_system_0000000000000001',
            'channel_name': 'alerts',
        },
    ))

    bot_token, chat_id = handler._resolve_telegram_config()

    assert bot_token == 'system-token'
    assert chat_id == 'chat-tg_system_0000000000000001'


def test_telegram_config_from_same_org_is_resolved(tenant_orgs):
    _telegram_config(ORG_B, 'tg_org_b_000000000000000001', 'token-b')
    handler = TelegramHandler(_queue(
        ORG_B,
        config={
            'config_id': 'tg_org_b_000000000000000001',
            'channel_name': 'alerts',
        },
    ))

    resolved = handler._resolve_telegram_config()

    assert resolved == ('token-b', 'chat-tg_org_b_000000000000000001')


def test_sys_emailrelay_recipient_group_from_other_org_returns_empty(tenant_orgs):
    group = RecipientGroup(
        secure_code='group_org_a_0000000000000001',
        org_secure_code=ORG_A,
        name='Org A recipients',
        priority=10,
        is_active=True,
        is_deleted=False,
    )
    group.included_users = ['user-a']
    db.session.add(group)
    db.session.commit()

    handler = SysEmailRelayHandler(_queue(ORG_B, node_type='SysEmailRelay'))

    assert handler._resolve_group_recipients(['group_org_a_0000000000000001']) == []


def test_smtp_config_from_other_org_is_not_used_and_falls_back_to_system(tenant_orgs):
    _smtp_config(ORG_A, 'smtp_org_a_0000000000000001', 'smtp-a.example.test')
    _smtp_config(
        SYSTEM_ORG_CODE,
        'smtp_system_00000000000001',
        'smtp-system.example.test',
        priority=1,
    )
    handler = EmailHandler(_queue(
        ORG_B,
        node_type='Email',
        config={'smtp_config_id': 'smtp_org_a_0000000000000001'},
    ))
    handler._workflow_instance = SimpleNamespace(org_secure_code=ORG_B)

    smtp = handler._resolve_smtp_config()

    assert smtp['smtp_host'] == 'smtp-system.example.test'
    assert smtp['username'] == 'smtp_system_00000000000001@example.test'


def test_sys_emailrelay_handle_denies_unauthorized_org_before_subprocess(tenant_orgs):
    db.session.add(WorkflowNodeDefinition(
        secure_code='node_sysemailrelay_test_0001',
        node_type='SysEmailRelay',
        category='系統',
        display_name='SysEmailRelay',
        execution_handler='tests.SysEmailRelay',
        org_restricted=True,
        is_active=True,
        is_deleted=False,
    ))
    db.session.commit()

    handler = SysEmailRelayHandler(_queue(
        ORG_B,
        node_type='SysEmailRelay',
        config={
            'subject': 'Blocked',
            'body': 'Blocked',
            'recipient_type': 'manual',
            'recipient_manual': 'blocked@example.test',
        },
    ))

    with patch.object(handler, 'report_running') as report_running, \
            patch.object(handler, 'log_error') as log_error, \
            patch(
                'modules.form_workflow.services.node_handlers.'
                'sys_emailrelay_handler.subprocess.run'
            ) as run:
        result = handler.handle()

    assert result == {
        'status': 'error',
        'message': '企業未取得 SysEmailRelay 節點授權',
    }
    report_running.assert_called_once_with()
    log_error.assert_called_once()
    run.assert_not_called()
