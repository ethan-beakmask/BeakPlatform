import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db
from app.models import Organization
from modules.open_defense.models import OdDefenseDecision
from modules.open_defense.services.edl_service import (
    collect_active_blocks,
    render_edl_text,
)
from modules.open_defense.web.edl_public import is_source_ip_allowed


ORG_SC = 'test_org_00000000001'
OTHER_ORG_SC = 'other_org_000000001'


def _decision(
    *,
    org_secure_code=ORG_SC,
    secure_code,
    action='block',
    target_type='ip',
    target_value='192.0.2.10',
    status='applied',
    decided_at=None,
    expires_at=None,
    revoked_by_decision_secure_code=None,
):
    decision = OdDefenseDecision(
        secure_code=secure_code,
        org_secure_code=org_secure_code,
        action=action,
        target_type=target_type,
        target_value=target_value,
        enforcement_points=['nftables', 'edl'],
        expires_at=expires_at,
        decided_via='auto',
        decided_at=decided_at or datetime.utcnow(),
        status=status,
        revoked_by_decision_secure_code=revoked_by_decision_secure_code,
        is_deleted=False,
    )
    db.session.add(decision)
    db.session.flush()
    return decision


def test_render_edl_text_format_deduplicates_and_sorts(app, db_session):
    _decision(
        secure_code='od_fmt_ipv6_000000000000001',
        target_type='ipv6',
        target_value='2001:db8::2',
    )
    _decision(
        secure_code='od_fmt_ipv4_b_00000000001',
        target_value='192.0.2.10',
    )
    _decision(
        secure_code='od_fmt_ipv4_a_00000000001',
        target_value='192.0.2.1',
    )
    _decision(
        secure_code='od_fmt_ipv4_dup_000000001',
        target_value='192.0.2.10',
    )
    db.session.commit()

    text = render_edl_text(collect_active_blocks(ORG_SC))

    assert text == '192.0.2.1\n192.0.2.10\n2001:db8::2\n'
    assert not text.startswith('#')
    assert '\n\n' not in text
    assert text.endswith('\n') and not text.endswith('\n\n')
    assert render_edl_text([]) == ''


def test_invalid_target_values_are_excluded(app, db_session):
    _decision(secure_code='od_valid_000000000000000001', target_value='192.0.2.10')
    _decision(secure_code='od_bad_0000000000000000001', target_value='not-an-ip')
    _decision(secure_code='od_bad_0000000000000000002', target_value='1.2.3.4; DROP')
    db.session.commit()

    text = render_edl_text(collect_active_blocks(ORG_SC))

    assert '192.0.2.10\n' in text
    assert 'not-an-ip' not in text
    assert '1.2.3.4; DROP' not in text


def test_expired_block_is_excluded_even_when_status_applied(app, db_session):
    _decision(
        secure_code='od_expired_000000000000001',
        target_value='192.0.2.20',
        status='applied',
        expires_at=datetime.utcnow() - timedelta(minutes=1),
    )
    _decision(
        secure_code='od_active_0000000000000001',
        target_value='192.0.2.21',
        status='applied',
        expires_at=datetime.utcnow() + timedelta(minutes=10),
    )
    db.session.commit()

    entries = collect_active_blocks(ORG_SC)

    assert '192.0.2.20' not in entries
    assert '192.0.2.21' in entries


def test_later_unblock_overrides_matching_block(app, db_session):
    base_time = datetime.utcnow() - timedelta(minutes=10)
    _decision(
        secure_code='od_block_00000000000000001',
        target_value='192.0.2.30',
        decided_at=base_time,
    )
    _decision(
        secure_code='od_unblock_000000000000001',
        action='unblock',
        target_value='192.0.2.30',
        decided_at=base_time + timedelta(minutes=1),
        status='applied',
    )
    _decision(
        secure_code='od_kept_000000000000000001',
        target_value='192.0.2.31',
        decided_at=base_time,
    )
    db.session.commit()

    entries = collect_active_blocks(ORG_SC)

    assert '192.0.2.30' not in entries
    assert '192.0.2.31' in entries


def test_collect_active_blocks_is_tenant_isolated(app, db_session):
    other = Organization(
        secure_code=OTHER_ORG_SC,
        code='OTHER_ORG',
        name='Other Organization',
        domain_name='other.local',
        is_active=True,
        is_deleted=False,
    )
    db.session.add(other)
    _decision(
        secure_code='od_tenant_self_00000000001',
        target_value='192.0.2.40',
    )
    _decision(
        org_secure_code=OTHER_ORG_SC,
        secure_code='od_tenant_other_0000000001',
        target_value='192.0.2.41',
    )
    db.session.commit()

    entries = collect_active_blocks(ORG_SC)

    assert '192.0.2.40' in entries
    assert '192.0.2.41' not in entries


def test_source_ip_allowlist_matching_cases(app):
    assert is_source_ip_allowed('192.0.2.10', '192.0.2.10,198.51.100.0/24') is True
    assert is_source_ip_allowed('203.0.113.10', '192.0.2.10,198.51.100.0/24') is False
    assert is_source_ip_allowed('192.0.2.10', '') is False
