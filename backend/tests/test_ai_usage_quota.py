# -*- coding: utf-8 -*-
"""
AiAgent 節點用量記錄與配額測試

不呼叫真的 claude CLI；handler 行為一律 mock `_run_cli`。
"""
import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db  # noqa: E402
from app.models import Organization  # noqa: E402
from app.models.system_setting import SystemSetting  # noqa: E402
from modules.form_workflow.models import FwAiUsageRecord  # noqa: E402
from modules.form_workflow.services import ai_usage_service  # noqa: E402
from modules.form_workflow.services.node_handlers.ai_agent_handler import (  # noqa: E402
    AiAgentHandler,
)


def _seed_system_defaults(include_defaults=True, **overrides):
    data = dict(ai_usage_service.HARDCODED_DEFAULTS) if include_defaults else {}
    data.update(overrides)
    setting = SystemSetting(
        key=ai_usage_service.SYSTEM_SETTING_KEY,
        value=json.dumps(data),
        value_type='json',
        description='test',
        category='ai_node',
    )
    db.session.add(setting)
    db.session.commit()
    return setting


def _usage(org_code, status=FwAiUsageRecord.STATUS_SUCCESS, started_at=None,
           cost='0', model='claude-sonnet-5'):
    rec = FwAiUsageRecord(
        org_secure_code=org_code,
        workflow_instance_secure_code='wi_test',
        node_id='ai1',
        node_name='AI',
        node_queue_secure_code='q_test',
        model=model,
        status=status,
        input_tokens=10,
        output_tokens=5,
        cost_usd=cost,
        started_at=started_at or datetime.utcnow(),
        finished_at=started_at or datetime.utcnow(),
    )
    db.session.add(rec)
    db.session.commit()
    return rec


def _set_org(test_org, **updates):
    ai_usage_service.set_org_config(test_org, updates)
    db.session.commit()


def _queue(org_code='test_org_00000000001', config=None):
    node_config = {
        'result_var': 'ai_result',
        'payload_template': 'payload',
        'write_approval_note': False,
    }
    node_config.update(config or {})
    return SimpleNamespace(
        id=1,
        secure_code='queue_000000000000000001',
        org_secure_code=org_code,
        workflow_instance_secure_code='wi_handler_test',
        node_id='ai1',
        node_name='AI',
        node_config=node_config,
        status='PENDING',
    )


def _run_handler(queue):
    handler = AiAgentHandler(queue)
    envelope = {
        'result': '{"canary":"fixed","verdict":"benign","score":1,"reasons":[],"note":"ok"}',
        'usage': {'input_tokens': 2, 'output_tokens': 3},
        'total_cost_usd': 0.01,
        'modelUsage': {'claude-sonnet-5': {'costUSD': 0.01}},
    }
    with patch.object(AiAgentHandler, 'report_running'), \
            patch.object(AiAgentHandler, 'set_flow_var'), \
            patch.object(AiAgentHandler, 'log_info'), \
            patch.object(AiAgentHandler, 'log_warning'), \
            patch.object(AiAgentHandler, '_run_cli', return_value=(envelope['result'], None, envelope)) as run_cli, \
            patch('modules.form_workflow.services.node_handlers.ai_agent_handler.build_prompt',
                  return_value=('prompt', 'fixed')):
        result = handler.handle()
    return result, run_cli


def test_get_effective_config_three_level_fallback(test_org):
    _seed_system_defaults(
        include_defaults=False,
        enabled=True,
        daily_max_runs=77,
        monthly_max_runs=1700,
        daily_max_cost_usd=3.5,
    )
    _set_org(test_org, daily_max_runs=5)

    cfg = ai_usage_service.get_effective_config(test_org)

    assert cfg['daily_max_runs'] == 5
    assert cfg['monthly_max_runs'] == 1700
    assert cfg['daily_max_cost_usd'] == 3.5
    assert cfg['monthly_max_cost_usd'] == 20.0

    sources = {row['key']: row['source'] for row in ai_usage_service.get_config_with_source(test_org)}
    assert sources['daily_max_runs'] == 'org'
    assert sources['monthly_max_runs'] == 'system'
    assert sources['monthly_max_cost_usd'] == 'default'


def test_zero_limit_means_unlimited_for_runs(test_org):
    _seed_system_defaults()
    _set_org(test_org, daily_max_runs=0, monthly_max_runs=0)
    _usage(test_org.secure_code)

    record, err = ai_usage_service.check_and_reserve(
        test_org.secure_code, 'wi', 'ai1', 'AI', 'q1', None, 'claude-sonnet-5')

    assert err is None
    assert record.status == FwAiUsageRecord.STATUS_RUNNING


def test_none_limit_means_unlimited_for_cost(test_org):
    _seed_system_defaults()
    _set_org(test_org, daily_max_runs=10, monthly_max_runs=10,
             daily_max_cost_usd=None, monthly_max_cost_usd=None)
    _usage(test_org.secure_code, cost='999.99')

    record, err = ai_usage_service.check_and_reserve(
        test_org.secure_code, 'wi', 'ai1', 'AI', 'q1', None, 'claude-sonnet-5')

    assert err is None
    assert record.status == FwAiUsageRecord.STATUS_RUNNING


def test_enabled_false_blocks_and_records_blocked(test_org):
    _seed_system_defaults()
    _set_org(test_org, enabled=False)

    record, err = ai_usage_service.check_and_reserve(
        test_org.secure_code, 'wi', 'ai1', 'AI', 'q1', None, 'claude-sonnet-5')

    assert record is None
    assert err == '本企業已停用 AI 分析節點'
    blocked = FwAiUsageRecord.query.filter_by(org_secure_code=test_org.secure_code).one()
    assert blocked.status == FwAiUsageRecord.STATUS_BLOCKED
    assert float(blocked.cost_usd) == 0.0


def test_run_limit_blocks_with_numbers_in_reason(test_org):
    _seed_system_defaults()
    _set_org(test_org, daily_max_runs=1, monthly_max_runs=100)
    _usage(test_org.secure_code)

    record, err = ai_usage_service.check_and_reserve(
        test_org.secure_code, 'wi', 'ai1', 'AI', 'q1', None, 'claude-sonnet-5')

    assert record is None
    assert '今日執行次數' in err
    assert '1/1' in err


def test_cost_limit_blocks_when_runs_not_full(test_org):
    _seed_system_defaults()
    _set_org(test_org, daily_max_runs=50, monthly_max_runs=1000,
             daily_max_cost_usd=0.5, monthly_max_cost_usd=100)
    _usage(test_org.secure_code, cost='0.50')

    record, err = ai_usage_service.check_and_reserve(
        test_org.secure_code, 'wi', 'ai1', 'AI', 'q1', None, 'claude-sonnet-5')

    assert record is None
    assert '今日估算成本' in err
    assert '$0.5000/$0.50' in err


def test_blocked_records_do_not_count_in_period_usage(test_org):
    _seed_system_defaults()
    _set_org(test_org, enabled=False)

    for queue_code in ('q1', 'q2'):
        ai_usage_service.check_and_reserve(
            test_org.secure_code, 'wi', 'ai1', 'AI', queue_code, None, 'claude-sonnet-5')

    usage = ai_usage_service.get_period_usage(test_org.secure_code, 'Asia/Taipei')
    assert usage['daily_runs'] == 0
    assert FwAiUsageRecord.query.filter_by(
        org_secure_code=test_org.secure_code,
        status=FwAiUsageRecord.STATUS_BLOCKED,
    ).count() == 2


def test_daily_boundary_uses_org_timezone_not_utc_date(test_org):
    _seed_system_defaults()
    test_org.set_setting('timezone', 'Asia/Taipei')
    db.session.commit()
    _usage(test_org.secure_code, started_at=datetime(2026, 8, 20, 15, 30))

    with patch('modules.form_workflow.services.ai_usage_service.datetime') as dt:
        dt.utcnow.return_value = datetime(2026, 8, 20, 16, 30)
        usage = ai_usage_service.get_period_usage(test_org.secure_code, 'Asia/Taipei')

    assert usage['day_start'] == datetime(2026, 8, 20, 16, 0)
    assert usage['daily_runs'] == 0
    assert usage['monthly_runs'] == 1


def test_month_boundary_uses_org_timezone_not_utc_month(test_org):
    _seed_system_defaults()
    test_org.set_setting('timezone', 'Asia/Taipei')
    db.session.commit()
    _usage(test_org.secure_code, started_at=datetime(2026, 8, 31, 15, 30))

    with patch('modules.form_workflow.services.ai_usage_service.datetime') as dt:
        dt.utcnow.return_value = datetime(2026, 8, 31, 16, 30)
        usage = ai_usage_service.get_period_usage(test_org.secure_code, 'Asia/Taipei')

    assert usage['month_start'] == datetime(2026, 8, 31, 16, 0)
    assert usage['monthly_runs'] == 0
    assert usage['daily_runs'] == 0


def test_finalize_extracts_tokens_cost_and_marks_success(test_org):
    rec = _usage(test_org.secure_code, status=FwAiUsageRecord.STATUS_RUNNING, cost='0')
    envelope = {
        'usage': {
            'input_tokens': 11,
            'output_tokens': 12,
            'cache_creation_input_tokens': 13,
            'cache_read_input_tokens': 14,
        },
        'total_cost_usd': 0.12345678,
        'duration_ms': 1500,
        'num_turns': 2,
        'modelUsage': {'claude-sonnet-5': {'costUSD': 0.12345678}},
    }

    ai_usage_service.finalize(rec, envelope)

    assert rec.status == FwAiUsageRecord.STATUS_SUCCESS
    assert rec.input_tokens == 11
    assert rec.output_tokens == 12
    assert float(rec.cost_usd) == 0.12345678
    assert rec.model_usage['claude-sonnet-5']['costUSD'] == 0.12345678


def test_finalize_failure_still_records_tokens_and_cost(test_org):
    rec = _usage(test_org.secure_code, status=FwAiUsageRecord.STATUS_RUNNING, cost='0')

    ai_usage_service.finalize(rec, {
        'usage': {'input_tokens': 21, 'output_tokens': 22},
        'total_cost_usd': 0.25,
    }, 'canary failed')

    assert rec.status == FwAiUsageRecord.STATUS_FAILED
    assert rec.error_message == 'canary failed'
    assert rec.input_tokens == 21
    assert float(rec.cost_usd) == 0.25


def test_finalize_tolerates_partial_malformed_envelope(test_org):
    rec = _usage(test_org.secure_code, status=FwAiUsageRecord.STATUS_RUNNING, cost='0')

    ai_usage_service.finalize(rec, {
        'total_cost_usd': 'not-a-number',
        'duration_ms': 'bad',
        'modelUsage': ['not', 'dict'],
    })

    assert rec.status == FwAiUsageRecord.STATUS_SUCCESS
    assert float(rec.cost_usd) == 0.0
    assert rec.model_usage is None
    assert rec.duration_ms == 0


def test_finalize_sums_multiple_model_usage_when_total_cost_missing(test_org):
    rec = _usage(test_org.secure_code, status=FwAiUsageRecord.STATUS_RUNNING, cost='0')

    ai_usage_service.finalize(rec, {
        'usage': {},
        'modelUsage': {
            'model-a': {'costUSD': 0.10},
            'model-b': {'costUSD': '0.20'},
        },
    })

    assert rec.status == FwAiUsageRecord.STATUS_SUCCESS
    assert float(rec.cost_usd) == 0.30


def test_handler_allows_execution_when_quota_service_raises(test_org):
    with patch('modules.form_workflow.services.ai_usage_service.check_and_reserve',
               side_effect=RuntimeError('quota db down')):
        result, run_cli = _run_handler(_queue(test_org.secure_code))

    assert result['status'] == 'success'
    assert run_cli.called


def test_handler_quota_error_ignores_on_error_continue(test_org):
    with patch('modules.form_workflow.services.ai_usage_service.check_and_reserve',
               return_value=(None, 'AI 分析節點今日執行次數已達上限（50/50）')):
        result, run_cli = _run_handler(_queue(test_org.secure_code, {'on_error': 'continue'}))

    assert result['status'] == 'error'
    assert result['message'] == 'AI 分析節點今日執行次數已達上限（50/50）'
    assert not run_cli.called


def test_tenant_usage_isolated_between_organizations(test_org):
    _seed_system_defaults()
    _set_org(test_org, daily_max_runs=1, monthly_max_runs=10)
    _usage(test_org.secure_code)
    org_b = Organization(
        secure_code='test_org_00000000002',
        code='TEST_ORG_B',
        name='Test Organization B',
        domain_name='test-b.local',
        is_active=True,
        is_deleted=False,
    )
    db.session.add(org_b)
    db.session.commit()
    _set_org(org_b, daily_max_runs=1, monthly_max_runs=10)

    record_a, err_a = ai_usage_service.check_and_reserve(
        test_org.secure_code, 'wi', 'ai1', 'AI', 'qa', None, 'claude-sonnet-5')
    record_b, err_b = ai_usage_service.check_and_reserve(
        org_b.secure_code, 'wi', 'ai1', 'AI', 'qb', None, 'claude-sonnet-5')

    assert record_a is None
    assert '今日執行次數' in err_a
    assert err_b is None
    assert record_b.org_secure_code == org_b.secure_code


def test_blocked_dedupes_per_node_queue_on_engine_retry(test_org):
    """引擎對回 error 的節點會重試到 max_retries，但同一節點只該記一次 blocked。

    重試時配額不會恢復，若每次都寫一筆，管理頁的「被擋次數」會虛報成重試次數。
    """
    _seed_system_defaults()
    _set_org(test_org, enabled=False)

    for _ in range(3):        # 模擬引擎的三次重試，node_queue_secure_code 相同
        record, reason = ai_usage_service.check_and_reserve(
            test_org.secure_code, 'wi', 'ai1', 'AI', 'queue_retry_1', None, 'claude-sonnet-5')
        assert record is None
        assert reason == '本企業已停用 AI 分析節點'

    assert FwAiUsageRecord.query.filter_by(
        node_queue_secure_code='queue_retry_1',
        status=FwAiUsageRecord.STATUS_BLOCKED,
    ).count() == 1

    # 換一個節點佇列項目仍要各自記一筆
    ai_usage_service.check_and_reserve(
        test_org.secure_code, 'wi', 'ai2', 'AI', 'queue_retry_2', None, 'claude-sonnet-5')
    assert FwAiUsageRecord.query.filter_by(
        org_secure_code=test_org.secure_code,
        status=FwAiUsageRecord.STATUS_BLOCKED,
    ).count() == 2
