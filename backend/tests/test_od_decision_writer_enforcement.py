"""
DecisionWriter handler -- enforcement_points 依 action 過濾（PF-125，2026-09-13 Ethan 裁示）

背景：od-bridge 的 nftables／crowdsec 執行器只實作 block/unblock
(Integrated-WAF/od-bridge/od_bridge/enforcers/nftables.py、crowdsec.py)，
拉到 action=allow 的決策會回 unsupported_action，讓整筆決策從 pending
掉成 failed。DecisionWriterHandler 因此在寫入 od_defense_decisions 之前，
對 action=allow 只保留支援 allow 的執行點（目前只有 edl）。
block/unblock/observe 維持既有行為，不受此變更影響。
"""
import sys
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


def _run(queue):
    handler = DecisionWriterHandler(queue)
    # target_value / reason_template 在測試裡都是字面值，不必真的解析變數
    # （既有測試 test_sys_sqlexecutor_node.py 也用同樣手法繞過變數系統）。
    handler.replace_variables = lambda raw, **kwargs: raw
    return handler.handle()


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
