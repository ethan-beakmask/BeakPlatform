import sys
import json
import ipaddress
from pathlib import Path

import pytest
from sqlalchemy import inspect

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db
from app.defaults.od_protected_defaults import (
    BUILTIN_PROTECTED_DEFAULTS,
    seed_org_builtin_protected_targets,
)
from app.utils.security import generate_secure_code
from modules.open_defense.models import OdDefenseDecision, OdProtectedTarget
from modules.open_defense.services.decision_service import (
    DecisionValidationError,
    ProtectedTargetError,
    create_decision,
)
from modules.open_defense.services.protected_target_service import (
    InvalidTargetValueError,
    BUILTIN_PROTECTED_NETWORKS,
    check_block_target,
    describe_protection,
    list_effective_networks,
    parse_target_network,
)


ORG_SC = 'test_org_00000000001'
OTHER_ORG_SC = 'test_org_00000000002'


def _require_od_protected_tables():
    required = {
        'od_protected_targets',
        'od_defense_decisions',
    }
    inspector = inspect(db.engine)
    missing = sorted(table for table in required if not inspector.has_table(table))
    if missing:
        pytest.skip(
            'PF-83: pytest app fixture did not create module tables required for '
            f'OpenDefense protected target integration tests: {", ".join(missing)}'
        )


def _check(target_value, *, action='block', target_type='ip', org_secure_code=ORG_SC):
    return check_block_target(
        org_secure_code=org_secure_code,
        action=action,
        target_type=target_type,
        target_value=target_value,
    )


def _protected_target(
    *,
    org_secure_code=ORG_SC,
    entry_type='protect',
    target_value='203.0.113.0/24',
    is_active=True,
    name='test protected target',
    origin='custom',
):
    entry = OdProtectedTarget(
        secure_code=generate_secure_code(),
        org_secure_code=org_secure_code,
        entry_type=entry_type,
        origin=origin,
        target_value=target_value,
        name=name,
        is_active=is_active,
        is_deleted=False,
    )
    db.session.add(entry)
    db.session.flush()
    return entry


def test_private_proxy_address_hits_builtin_or_config_without_db():
    hit = _check('192.168.0.112')

    assert hit is not None
    assert hit.source in {'builtin', 'config'}


@pytest.mark.parametrize(
    'target_value',
    ['10.1.2.3', '127.0.0.1', '169.254.1.1', '::1', 'fe80::1'],
)
def test_builtin_protected_addresses_hit_without_db(target_value):
    assert _check(target_value) is not None


@pytest.mark.parametrize(
    'target_value',
    ['203.0.113.77', '8.8.8.8', '2001:4860:4860::8888'],
)
def test_public_addresses_do_not_hit_without_db(target_value):
    assert _check(target_value) is None


@pytest.mark.parametrize('target_value', ['0.0.0.0/0', '192.168.0.0/24'])
def test_cidr_overlap_hits_without_db(target_value):
    assert _check(target_value, target_type='cidr') is not None


def test_ipv4_mapped_ipv6_is_normalized_without_db():
    hit = _check('::ffff:192.168.0.112', target_type='ipv6')

    assert hit is not None
    assert hit.network == '192.168.0.0/16'


@pytest.mark.parametrize('action', ['unblock', 'observe'])
def test_only_block_action_is_checked_without_db(action):
    assert _check('10.1.2.3', action=action) is None


def test_non_ip_target_type_is_not_checked_without_db():
    assert _check('evil.example.com', target_type='domain') is None


def test_parse_target_network_rejects_invalid_value_without_db():
    with pytest.raises(InvalidTargetValueError):
        parse_target_network('not-an-ip')


def test_describe_protection_reports_hit_without_db():
    result = describe_protection(org_secure_code=ORG_SC, target_value='10.1.2.3')

    assert result['target_value'] == '10.1.2.3'
    assert result['protected'] is True
    assert result['hit']['network'] == '10.0.0.0/8'
    assert result['error'] is None


def test_describe_protection_reports_invalid_target_without_db():
    result = describe_protection(org_secure_code=ORG_SC, target_value='not-an-ip')

    assert result == {
        'target_value': 'not-an-ip',
        'protected': False,
        'hit': None,
        'error': 'invalid_target',
    }


def test_custom_protect_makes_public_address_protected(app, db_session):
    _require_od_protected_tables()
    _protected_target(target_value='203.0.113.0/24')

    hit = _check('203.0.113.77')

    assert hit is not None
    assert hit.source == 'custom'


def test_inactive_custom_protect_is_ignored(app, db_session):
    _require_od_protected_tables()
    _protected_target(target_value='203.0.113.0/24', is_active=False)

    assert _check('203.0.113.77') is None


def test_builtin_db_record_is_used(app, db_session):
    _require_od_protected_tables()
    entry = _protected_target(
        target_value='10.0.0.0/8',
        origin='builtin',
        name='org builtin 10',
    )

    hit = _check('10.1.2.3')

    assert hit is not None
    assert hit.source == 'builtin'
    assert hit.entry_secure_code == entry.secure_code


def test_org_can_disable_builtin_protection(app, db_session):
    _require_od_protected_tables()
    _protected_target(
        target_value='10.0.0.0/8',
        origin='builtin',
        is_active=False,
    )

    assert _check('10.1.2.3') is None


def test_builtin_fallback_applies_when_org_has_no_builtin_records(app, db_session):
    _require_od_protected_tables()

    hit = _check('10.1.2.3')

    assert hit is not None
    assert hit.source == 'builtin'
    assert hit.entry_secure_code is None


@pytest.mark.parametrize('target_value', ['10.1.2.3', '127.0.0.1', '192.168.0.112'])
def test_all_builtin_disabled_does_not_trigger_fallback(app, db_session, target_value):
    """企業把出廠的 16 條全部停用是合法設定，不得被誤判成「seed 漏了」。

    fail-safe 的判斷若誤帶 is_active 過濾，這裡會回退硬編碼常數而拿到 hit
    ——使用者的停用被靜默忽略且沒有任何錯誤訊息。
    """
    _require_od_protected_tables()
    app.config['TRUSTED_PROXY_IPS'] = ()
    app.config['OD_PROTECTED_EXTRA_NETWORKS'] = ()
    assert seed_org_builtin_protected_targets(ORG_SC) == 16
    OdProtectedTarget.query.filter_by(
        org_secure_code=ORG_SC,
        origin='builtin',
        is_deleted=False,
    ).update({'is_active': False})
    db.session.flush()

    assert _check(target_value) is None


def test_builtin_protection_is_per_org(app, db_session):
    _require_od_protected_tables()
    _protected_target(
        org_secure_code=ORG_SC,
        target_value='10.0.0.0/8',
        origin='builtin',
        is_active=False,
    )
    _protected_target(
        org_secure_code=OTHER_ORG_SC,
        target_value='10.0.0.0/8',
        origin='builtin',
        is_active=True,
    )

    assert _check('10.1.2.3', org_secure_code=ORG_SC) is None
    hit = _check('10.1.2.3', org_secure_code=OTHER_ORG_SC)
    assert hit is not None
    assert hit.source == 'builtin'


def test_builtin_record_is_not_reported_as_custom(app, db_session):
    _require_od_protected_tables()
    _protected_target(target_value='10.0.0.0/8', origin='builtin')

    hit = _check('10.1.2.3')

    assert hit is not None
    assert hit.source == 'builtin'


def test_list_effective_networks_only_returns_builtin_on_fallback(app, db_session):
    _require_od_protected_tables()

    fallback_builtin, _config = list_effective_networks(ORG_SC)
    assert len(fallback_builtin) == 16

    _protected_target(target_value='10.0.0.0/8', origin='builtin')
    builtin, _config = list_effective_networks(ORG_SC)
    assert builtin == []


def test_builtin_defaults_match_service_constants():
    defaults = {
        str(ipaddress.ip_network(network))
        for network, _label in BUILTIN_PROTECTED_DEFAULTS
    }
    constants = {
        str(network)
        for network, _label in BUILTIN_PROTECTED_NETWORKS
    }

    assert defaults == constants


def test_seed_builtin_protected_targets_is_idempotent(app, db_session):
    _require_od_protected_tables()

    assert seed_org_builtin_protected_targets(ORG_SC) == 16
    assert seed_org_builtin_protected_targets(ORG_SC) == 0

    count = OdProtectedTarget.query.filter_by(
        org_secure_code=ORG_SC,
        origin='builtin',
        entry_type='protect',
        is_deleted=False,
    ).count()
    assert count == 16


def test_seed_does_not_overwrite_existing_custom_same_network(app, db_session):
    _require_od_protected_tables()
    custom = _protected_target(
        target_value='10.0.0.0/8',
        origin='custom',
        name='custom 10',
    )

    seed_org_builtin_protected_targets(ORG_SC)

    db.session.refresh(custom)
    assert custom.origin == 'custom'
    assert OdProtectedTarget.query.filter_by(
        org_secure_code=ORG_SC,
        origin='builtin',
        entry_type='protect',
        target_value='10.0.0.0/8',
        is_deleted=False,
    ).count() == 0


def test_custom_exempt_requires_target_to_be_subnet_of_exempt(app, db_session):
    _require_od_protected_tables()
    _protected_target(
        entry_type='exempt',
        target_value='10.1.2.3/32',
        name='single host exempt',
    )

    assert _check('10.1.2.3') is None
    hit = _check('10.0.0.0/8', target_type='cidr')
    assert hit is not None
    assert hit.network == '10.0.0.0/8'


def test_custom_entry_from_other_org_is_ignored(app, db_session):
    _require_od_protected_tables()
    _protected_target(
        org_secure_code=OTHER_ORG_SC,
        target_value='203.0.113.0/24',
    )

    assert _check('203.0.113.77', org_secure_code=ORG_SC) is None


def test_create_decision_rejects_protected_target_without_insert(app, db_session):
    _require_od_protected_tables()
    before = db.session.query(OdDefenseDecision).count()

    with pytest.raises(ProtectedTargetError):
        create_decision(
            org_secure_code=ORG_SC,
            action='block',
            target_type='ip',
            target_value='192.168.0.112',
            decided_via='auto',
        )

    assert db.session.query(OdDefenseDecision).count() == before


def test_create_decision_allows_protected_target_with_override(app, db_session):
    _require_od_protected_tables()

    decision = create_decision(
        org_secure_code=ORG_SC,
        action='block',
        target_type='ip',
        target_value='192.168.0.112',
        decided_via='auto',
        decision_metadata={'source': 'test'},
        allow_protected_target=True,
        protected_override_reason='confirmed by admin',
    )

    assert decision.secure_code
    assert decision.decision_metadata['source'] == 'test'
    assert decision.decision_metadata['protected_override']['network']
    assert decision.decision_metadata['protected_override']['reason'] == 'confirmed by admin'


def test_create_decision_rejects_invalid_ip_fail_closed(app, db_session):
    _require_od_protected_tables()

    with pytest.raises(DecisionValidationError):
        create_decision(
            org_secure_code=ORG_SC,
            action='block',
            target_type='ip',
            target_value='not-an-ip',
            decided_via='auto',
        )


# ---------------------------------------------------------------------------
# 設定來源的保護網段（OD_PROTECTED_EXTRA_NETWORKS / TRUSTED_PROXY_IPS）
# 平台自身若是公網位址，內建私有網段清單救不了，只剩這條路徑。
# ---------------------------------------------------------------------------
def test_extra_networks_config_protects_public_address(app):
    app.config['OD_PROTECTED_EXTRA_NETWORKS'] = ('198.51.100.0/24',)

    hit = _check('198.51.100.10')

    assert hit is not None
    assert hit.source == 'config'
    assert hit.network == '198.51.100.0/24'


def test_trusted_proxy_ips_are_protected(app):
    app.config['TRUSTED_PROXY_IPS'] = ('198.51.100.20',)

    hit = _check('198.51.100.20')

    assert hit is not None
    assert hit.source == 'platform'


def test_invalid_config_network_is_skipped_not_fatal(app):
    """設定值髒掉時略過該筆即可（略過方向仍是保護更多），不可讓整個判定掛掉。"""
    app.config['OD_PROTECTED_EXTRA_NETWORKS'] = ('not-an-ip', '198.51.100.0/24')

    hit = _check('198.51.100.10')

    assert hit is not None
    assert hit.source == 'config'


# ---------------------------------------------------------------------------
# 平台反向代理位址一律保護，但對租戶公開回應不得具名揭露 TRUSTED_PROXY_IPS。
# ---------------------------------------------------------------------------
def test_list_effective_networks_hides_trusted_proxy_ips(app):
    app.config['TRUSTED_PROXY_IPS'] = ('198.51.100.20',)
    app.config['OD_PROTECTED_EXTRA_NETWORKS'] = ('198.51.100.0/24',)

    _builtin, config = list_effective_networks()
    serialized = json.dumps(config, ensure_ascii=False, sort_keys=True)

    assert '198.51.100.0/24' in serialized
    assert '198.51.100.20' not in serialized


def test_platform_trusted_proxy_public_address_remains_protected(app):
    app.config['TRUSTED_PROXY_IPS'] = ('198.51.100.20',)
    app.config['OD_PROTECTED_EXTRA_NETWORKS'] = ()

    hit = _check('198.51.100.20')

    assert hit is not None
    assert hit.source == 'platform'


def test_describe_protection_masks_platform_trusted_proxy_address(app):
    """管理員拿網段試算時，不得從回應反推出平台反向代理的精確位址。

    目標故意用涵蓋該位址的網段：使用者自己輸入的值照樣原樣回傳（那不是機密），
    被遮蔽的只有命中的 TRUSTED_PROXY_IPS 網段本身。
    """
    app.config['TRUSTED_PROXY_IPS'] = ('198.51.100.20',)
    app.config['OD_PROTECTED_EXTRA_NETWORKS'] = ()

    result = describe_protection(org_secure_code=ORG_SC, target_value='198.51.100.0/24')
    serialized = json.dumps(result, ensure_ascii=False, sort_keys=True)

    assert result['protected'] is True
    assert result['hit']['source'] == 'platform'
    assert result['hit']['network'] is None
    assert result['target_value'] == '198.51.100.0/24'
    assert '198.51.100.20' not in serialized


def test_create_decision_error_masks_platform_trusted_proxy_address(app, db_session):
    _require_od_protected_tables()
    app.config['TRUSTED_PROXY_IPS'] = ('198.51.100.20',)
    app.config['OD_PROTECTED_EXTRA_NETWORKS'] = ()

    with pytest.raises(ProtectedTargetError) as excinfo:
        create_decision(
            org_secure_code=ORG_SC,
            action='block',
            target_type='cidr',
            target_value='198.51.100.0/24',
            decided_via='auto',
        )

    message = str(excinfo.value)
    assert '198.51.100.20' not in message
    # 使用者自己要封的目標仍必須說出來，否則訊息無法辨識是哪一筆被擋
    assert '198.51.100.0/24' in message


# ---------------------------------------------------------------------------
# DecisionWriter 節點的三條路徑：error（預設）/ skip / 覆寫
# ---------------------------------------------------------------------------
class _FakeQueueItem:
    """只提供 handler 用得到的欄位，避免測試依賴整條工作流。"""

    def __init__(self, node_config, org_secure_code=ORG_SC):
        self.id = 1
        self.node_config = node_config
        self.org_secure_code = org_secure_code
        self.workflow_instance_secure_code = None
        self.node_id = 'node-test-decision-writer'


def _decision_writer(node_config, monkeypatch):
    from modules.form_workflow.services.node_handlers.decision_writer_handler import (
        DecisionWriterHandler,
    )

    handler = DecisionWriterHandler(_FakeQueueItem(node_config))
    monkeypatch.setattr(handler, 'report_running', lambda *a, **k: None)
    monkeypatch.setattr(handler, 'log_info', lambda *a, **k: None)
    monkeypatch.setattr(handler, 'log_error', lambda *a, **k: None)
    monkeypatch.setattr(handler, 'replace_variables', lambda value: value)
    monkeypatch.setattr(handler, '_lookup_source_event', lambda: None)
    monkeypatch.setattr(handler, '_infer_decided_via', lambda: 'auto')
    monkeypatch.setattr(handler, '_infer_decided_by', lambda: None)
    return handler


_PROTECTED_NODE_CONFIG = {
    'action': 'block',
    'target_type': 'ip',
    'target_value': '192.168.0.112',
    'enforcement_points': ['crowdsec'],
}


def test_decision_writer_defaults_to_error_on_protected(app, db_session, monkeypatch):
    _require_od_protected_tables()
    before = db.session.query(OdDefenseDecision).count()

    result = _decision_writer(dict(_PROTECTED_NODE_CONFIG), monkeypatch).handle()

    assert result['status'] == 'error'
    assert db.session.query(OdDefenseDecision).count() == before


def test_decision_writer_skip_mode_does_not_write_decision(app, db_session, monkeypatch):
    _require_od_protected_tables()
    before = db.session.query(OdDefenseDecision).count()
    config = dict(_PROTECTED_NODE_CONFIG, on_protected='skip')

    result = _decision_writer(config, monkeypatch).handle()

    assert result['status'] == 'success'
    assert result['data']['skipped'] is True
    assert db.session.query(OdDefenseDecision).count() == before


@pytest.mark.parametrize('unknown_mode', ['ignore', 'SKIP', '', None])
def test_decision_writer_unknown_on_protected_falls_back_to_error(
    app, db_session, monkeypatch, unknown_mode,
):
    """on_protected 只認 'skip'，拼錯或空值一律 fail-closed 回 error。"""
    _require_od_protected_tables()
    config = dict(_PROTECTED_NODE_CONFIG, on_protected=unknown_mode)

    result = _decision_writer(config, monkeypatch).handle()

    assert result['status'] == 'error'


@pytest.mark.parametrize('truthy', [True, 'true', 'TRUE', '1', 'yes'])
def test_decision_writer_override_writes_decision(app, db_session, monkeypatch, truthy):
    _require_od_protected_tables()
    config = dict(_PROTECTED_NODE_CONFIG, allow_protected_target=truthy)

    result = _decision_writer(config, monkeypatch).handle()

    assert result['status'] == 'success'
    decision = OdDefenseDecision.query.filter_by(
        secure_code=result['data']['decision_secure_code'],
    ).first()
    assert decision is not None
    override = decision.decision_metadata['protected_override']
    # 同時命中內建 192.168.0.0/16 與平台反向代理 /32 時，對外回報優先使用
    # 內建網段；覆寫稽核仍寫入判定回傳的真值。
    assert override['source'] == 'builtin'
    assert override['network'] == '192.168.0.0/16'


def test_decision_writer_public_target_still_writes_decision(app, db_session, monkeypatch):
    """既有行為不得改變：公網目標照樣寫得進去。"""
    _require_od_protected_tables()
    config = dict(_PROTECTED_NODE_CONFIG, target_value='203.0.113.77')

    result = _decision_writer(config, monkeypatch).handle()

    assert result['status'] == 'success'
    decision = OdDefenseDecision.query.filter_by(
        secure_code=result['data']['decision_secure_code'],
    ).first()
    assert decision is not None
    assert 'protected_override' not in (decision.decision_metadata or {})
