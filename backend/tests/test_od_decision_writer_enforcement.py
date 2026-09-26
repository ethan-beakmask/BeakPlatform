"""
DecisionWriter handler -- enforcement_points 依 action 過濾（PF-125，2026-09-13 裁示）

背景：od-bridge 的 nftables／crowdsec 執行器只實作 block/unblock
(Integrated-WAF/od-bridge/od_bridge/enforcers/nftables.py、crowdsec.py)，
拉到 action=allow 的決策會回 unsupported_action，讓整筆決策從 pending
掉成 failed。DecisionWriterHandler 因此在寫入 od_defense_decisions 之前，
對 action=allow 只保留支援 allow 的執行點（目前只有 edl）。
block/unblock/observe 維持既有行為，不受此變更影響。
"""
import sys
import types
from pathlib import Path

import pytest
from sqlalchemy import inspect

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db  # noqa: E402
from app.utils.security import generate_secure_code  # noqa: E402
from modules.form_workflow.models import FwNodeExecutionQueue  # noqa: E402
from modules.form_workflow.services.node_handlers.decision_writer_handler import (  # noqa: E402
    DecisionWriterHandler,
)
from modules.open_defense.models import OdDefenseDecision  # noqa: E402


def _require_od_defense_decisions_table():
    inspector = inspect(db.engine)
    if not inspector.has_table('od_defense_decisions'):
        pytest.skip(
            'PF-83: pytest app fixture 未建出 open_defense 模組表 od_defense_decisions'
        )


def _queue(org, config_overrides, *, target_value='203.0.113.5'):
    """建立一個最小可執行的 DecisionWriter 節點佇列項。

    刻意不建真正的 FwWorkflowInstance/FwFormInstance -- handler 對這兩者的存取
    都包在 try/except 或做了 None 檢查（_infer_decided_via / _infer_decided_by /
    _lookup_source_event），config 明寫 decided_via 也讓 handler 不必查
    workflow_instance 來推斷來源。
    """
    config = {
        'action': 'block',
        'target_type': 'ip',
        'target_value': target_value,
        'decided_via': 'auto',
    }
    config.update(config_overrides)
    queue = FwNodeExecutionQueue(
        org_secure_code=org.secure_code,
        workflow_instance_secure_code=generate_secure_code(),
        node_id='node-DecisionWriter-test',
        node_type='DecisionWriter',
        status='PENDING',
        node_config=config,
    )
    db.session.add(queue)
    db.session.commit()
    return queue


def _run(queue, form_data=None):
    handler = DecisionWriterHandler(queue)
    if form_data is not None:
        handler._form_instance = types.SimpleNamespace(form_data=form_data)
    # target_value / reason_template 在測試裡都是字面值，不必真的解析變數
    # （既有測試 test_sys_sqlexecutor_node.py 也用同樣手法繞過變數系統）。
    handler.replace_variables = lambda raw, **kwargs: raw
    return handler.handle()


def _decisions_for_queue(queue):
    return OdDefenseDecision.query.filter_by(
        org_secure_code=queue.org_secure_code,
        case_secure_code=queue.workflow_instance_secure_code,
        workflow_node_id=queue.node_id,
    ).order_by(OdDefenseDecision.id.asc()).all()


def _written_enforcement_points(result):
    assert result['status'] == 'success', result
    sc = result['data']['decision_secure_code']
    decision = OdDefenseDecision.query.filter_by(secure_code=sc).one()
    return decision.enforcement_points


def test_allow_decision_drops_nftables_keeps_edl(test_org):
    _require_od_defense_decisions_table()
    queue = _queue(test_org, {
        'action': 'allow',
        'enforcement_points': ['nftables', 'edl'],
    }, target_value='203.0.113.10')

    result = _run(queue)

    assert _written_enforcement_points(result) == ['edl']


def test_allow_decision_with_only_unsupported_point_falls_back_to_edl(test_org):
    _require_od_defense_decisions_table()
    queue = _queue(test_org, {
        'action': 'allow',
        'enforcement_points': ['nftables'],
    }, target_value='203.0.113.11')

    result = _run(queue)

    assert _written_enforcement_points(result) == ['edl']


def test_allow_decision_with_no_enforcement_points_defaults_to_edl(test_org):
    _require_od_defense_decisions_table()
    queue = _queue(test_org, {
        'action': 'allow',
        'enforcement_points': [],
    }, target_value='203.0.113.12')

    result = _run(queue)

    assert _written_enforcement_points(result) == ['edl']


def test_allow_decision_drops_crowdsec_too(test_org):
    _require_od_defense_decisions_table()
    queue = _queue(test_org, {
        'action': 'allow',
        'enforcement_points': ['crowdsec', 'edl'],
    }, target_value='203.0.113.13')

    result = _run(queue)

    assert _written_enforcement_points(result) == ['edl']


def test_block_decision_enforcement_points_unaffected(test_org):
    """block／unblock 維持原樣，不套用 allow 的過濾規則。"""
    _require_od_defense_decisions_table()
    queue = _queue(test_org, {
        'action': 'block',
        'enforcement_points': ['nftables', 'edl'],
    }, target_value='203.0.113.14')

    result = _run(queue)

    assert _written_enforcement_points(result) == ['nftables', 'edl']


def test_unblock_decision_enforcement_points_unaffected(test_org):
    _require_od_defense_decisions_table()
    queue = _queue(test_org, {
        'action': 'unblock',
        'enforcement_points': ['nftables', 'crowdsec'],
    }, target_value='203.0.113.15')

    result = _run(queue)

    assert _written_enforcement_points(result) == ['nftables', 'crowdsec']


def test_observe_decision_enforcement_points_unaffected(test_org):
    """observe 維持既有行為：即使配了 nftables（本就不支援 observe），
    這裡也不主動介入——那是操作者自己要避免的既有陷阱（dev-notes/
    OPEN_DEFENSE_ARCHITECTURE.md「observe 動作不可加 edl 執行點」），
    不是本次 allow 過濾要處理的範圍。
    """
    _require_od_defense_decisions_table()
    queue = _queue(test_org, {
        'action': 'observe',
        'enforcement_points': ['nftables'],
    }, target_value='203.0.113.16')

    result = _run(queue)

    assert _written_enforcement_points(result) == ['nftables']


def test_actor_ips_expansion_writes_three_ipv4_decisions_with_batch_metadata(test_org):
    _require_od_defense_decisions_table()
    queue = _queue(test_org, {
        'target_source': 'actor_ips',
        'enforcement_points': ['edl'],
    })

    result = _run(queue, {
        'od_actor_ips': ['203.0.113.21', '203.0.113.22', '203.0.113.23'],
    })

    decisions = _decisions_for_queue(queue)
    assert result['status'] == 'success', result
    assert len(decisions) == 3
    assert [decision.target_type for decision in decisions] == ['ip', 'ip', 'ip']
    assert len(result['data']['decision_secure_codes']) == 3
    assert result['data']['decision_secure_code'] == result['data']['decision_secure_codes'][0]

    batches = [decision.decision_metadata['batch'] for decision in decisions]
    assert len({batch['id'] for batch in batches}) == 1
    assert [batch['index'] for batch in batches] == [0, 1, 2]
    assert [batch['total'] for batch in batches] == [3, 3, 3]
    assert {batch['source'] for batch in batches} == {'od_actor_ips'}


def test_actor_ips_expansion_infers_ipv6_target_type(test_org):
    _require_od_defense_decisions_table()
    queue = _queue(test_org, {
        'target_source': 'actor_ips',
        'enforcement_points': ['edl'],
    })

    result = _run(queue, {
        'od_actor_ips': ['203.0.113.24', '2001:db8::5'],
    })

    assert result['status'] == 'success', result
    ipv6_decision = OdDefenseDecision.query.filter_by(
        case_secure_code=queue.workflow_instance_secure_code,
        target_value='2001:db8::5',
    ).one()
    assert ipv6_decision.target_type == 'ipv6'


def test_actor_ips_missing_falls_back_to_single_target_without_batch_metadata(test_org):
    _require_od_defense_decisions_table()
    queue = _queue(test_org, {
        'target_source': 'actor_ips',
        'enforcement_points': ['edl'],
    }, target_value='203.0.113.25')

    result = _run(queue, {'od_events': []})

    decisions = _decisions_for_queue(queue)
    assert result['status'] == 'success', result
    assert len(decisions) == 1
    assert decisions[0].target_value == '203.0.113.25'
    assert decisions[0].decision_metadata is None


def test_actor_ips_expansion_over_max_targets_errors_without_writes(test_org):
    _require_od_defense_decisions_table()
    queue = _queue(test_org, {
        'target_source': 'actor_ips',
        'max_targets': 2,
        'enforcement_points': ['edl'],
    })

    result = _run(queue, {
        'od_actor_ips': ['203.0.113.26', '203.0.113.27', '203.0.113.28'],
    })

    assert result['status'] == 'error'
    assert '3' in result['message'] and '2' in result['message']
    assert _decisions_for_queue(queue) == []


def test_actor_ips_expansion_invalid_ip_errors_without_writes(test_org):
    _require_od_defense_decisions_table()
    queue = _queue(test_org, {
        'target_source': 'actor_ips',
        'enforcement_points': ['edl'],
    })

    result = _run(queue, {
        'od_actor_ips': ['203.0.113.29', 'not-an-ip'],
    })

    assert result['status'] == 'error'
    assert 'not-an-ip' in result['message']
    assert _decisions_for_queue(queue) == []


def test_actor_ips_expansion_protected_hit_errors_without_writes(test_org):
    _require_od_defense_decisions_table()
    queue = _queue(test_org, {
        'target_source': 'actor_ips',
        'enforcement_points': ['edl'],
    })

    result = _run(queue, {
        'od_actor_ips': ['203.0.113.30', '192.168.1.9'],
    })

    assert result['status'] == 'error'
    assert '192.168.1.9' in result['message']
    assert _decisions_for_queue(queue) == []


def test_actor_ips_expansion_protected_skip_writes_remaining_targets(test_org):
    _require_od_defense_decisions_table()
    queue = _queue(test_org, {
        'target_source': 'actor_ips',
        'on_protected': 'skip',
        'enforcement_points': ['edl'],
    })

    result = _run(queue, {
        'od_actor_ips': ['203.0.113.31', '192.168.1.9', '203.0.113.32'],
    })

    decisions = _decisions_for_queue(queue)
    assert result['status'] == 'success', result
    assert [decision.target_value for decision in decisions] == ['203.0.113.31', '203.0.113.32']
    assert result['data']['skipped'][0]['target_value'] == '192.168.1.9'
    assert result['data']['skipped'][0]['hit_network'] == '192.168.0.0/16'


def test_actor_ips_expansion_unblock_is_not_blocked_by_protected_list(test_org):
    _require_od_defense_decisions_table()
    queue = _queue(test_org, {
        'action': 'unblock',
        'target_source': 'actor_ips',
        'enforcement_points': ['edl'],
    })

    result = _run(queue, {
        'od_actor_ips': ['203.0.113.33', '192.168.1.9', '203.0.113.34'],
    })

    decisions = _decisions_for_queue(queue)
    assert result['status'] == 'success', result
    assert len(decisions) == 3
    assert {decision.target_value for decision in decisions} == {
        '203.0.113.33', '192.168.1.9', '203.0.113.34',
    }


def test_unknown_target_source_uses_single_value_mode(test_org):
    _require_od_defense_decisions_table()
    queue = _queue(test_org, {
        'target_source': 'weird',
        'enforcement_points': ['edl'],
    }, target_value='203.0.113.35')

    result = _run(queue, {
        'od_actor_ips': ['203.0.113.36', '203.0.113.37'],
    })

    decisions = _decisions_for_queue(queue)
    assert result['status'] == 'success', result
    assert len(decisions) == 1
    assert decisions[0].target_value == '203.0.113.35'
