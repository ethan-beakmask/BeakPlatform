"""
OpenDefense platform-side EDL renderer.

產出每個企業目前應封鎖的 IP/CIDR 清單，供檔案分享與公開 HTTP 端點共用。
"""
import ipaddress
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path

from flask import current_app, has_app_context

from app.models.organization import Organization
from ..models import OdDefenseDecision


logger = logging.getLogger(__name__)

SUPPORTED_TARGET_TYPES = ('ip', 'ipv6', 'cidr')
ACTIVE_BLOCK_STATUSES = ('pending', 'picked_up', 'applied', 'partial')
OVERRIDE_ACTIONS = ('unblock', 'allow')


def get_output_dir() -> str:
    if has_app_context():
        configured = current_app.config.get('OD_EDL_OUTPUT_DIR')
        if configured:
            return str(configured)

    configured = os.getenv('OD_EDL_OUTPUT_DIR')
    if configured:
        return configured

    repo_root = Path(__file__).resolve().parents[3]
    return str(repo_root / 'data' / 'edl')


def _normalize_target(target_type: str, target_value: str):
    value = (target_value or '').strip()
    if target_type in ('ip', 'ipv6'):
        return ipaddress.ip_address(value)
    if target_type == 'cidr':
        return ipaddress.ip_network(value, strict=False)
    raise ValueError(f'unsupported target_type: {target_type}')


def _sort_key(item):
    version_group = 0 if item.version == 4 else 1
    if isinstance(item, (ipaddress.IPv4Network, ipaddress.IPv6Network)):
        return (version_group, int(item.network_address), item.prefixlen, 1)
    return (version_group, int(item), item.max_prefixlen, 0)


def collect_active_blocks(org_secure_code: str) -> list[str]:
    now = datetime.utcnow()

    blocks = OdDefenseDecision.query.filter(
        OdDefenseDecision.org_secure_code == org_secure_code,
        OdDefenseDecision.is_deleted == False,
        OdDefenseDecision.target_type.in_(SUPPORTED_TARGET_TYPES),
        OdDefenseDecision.action == 'block',
        OdDefenseDecision.status.in_(ACTIVE_BLOCK_STATUSES),
        OdDefenseDecision.revoked_by_decision_secure_code.is_(None),
    ).filter(
        (OdDefenseDecision.expires_at.is_(None)) |
        (OdDefenseDecision.expires_at > now)
    ).all()

    overrides = OdDefenseDecision.query.filter(
        OdDefenseDecision.org_secure_code == org_secure_code,
        OdDefenseDecision.is_deleted == False,
        OdDefenseDecision.action.in_(OVERRIDE_ACTIONS),
    ).all()
    latest_override_by_target = {}
    for decision in overrides:
        decided_at = decision.decided_at
        if decided_at is None:
            continue
        previous = latest_override_by_target.get(decision.target_value)
        if previous is None or decided_at > previous:
            latest_override_by_target[decision.target_value] = decided_at

    normalized = {}
    for decision in blocks:
        override_at = latest_override_by_target.get(decision.target_value)
        if override_at is not None and override_at > decision.decided_at:
            continue

        try:
            parsed = _normalize_target(
                decision.target_type,
                decision.target_value,
            )
        except ValueError:
            logger.warning(
                'invalid EDL target skipped: org=%s target_type=%s target_value=%r',
                org_secure_code,
                decision.target_type,
                decision.target_value,
            )
            continue
        normalized[str(parsed)] = parsed

    return [str(item) for item in sorted(normalized.values(), key=_sort_key)]


def render_edl_text(entries: list[str]) -> str:
    if not entries:
        return ''
    return '\n'.join(entries) + '\n'


def write_org_edl(org_secure_code: str) -> dict:
    output_dir = Path(get_output_dir())
    org_dir = output_dir / org_secure_code
    path = org_dir / 'blocklist.txt'
    temp_path = None
    result = {
        'org_secure_code': org_secure_code,
        'path': str(path),
        'count': 0,
        'written': False,
        'error': None,
    }

    try:
        entries = collect_active_blocks(org_secure_code)
        text = render_edl_text(entries)
        result['count'] = len(entries)

        org_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            'w',
            encoding='utf-8',
            newline='\n',
            dir=str(org_dir),
            delete=False,
        ) as fh:
            temp_path = fh.name
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp_path, path)
        result['written'] = True
        return result
    except Exception as exc:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
        result['error'] = str(exc)
        logger.exception('failed to write EDL for org=%s', org_secure_code)
        return result


def render_all_orgs(*, dry_run: bool = False) -> dict:
    orgs = Organization.query.filter(
        Organization.is_deleted == False,
    ).order_by(Organization.secure_code.asc()).all()

    details = []
    errors = []
    written = 0

    for org in orgs:
        try:
            if dry_run:
                entries = collect_active_blocks(org.secure_code)
                detail = {
                    'org_secure_code': org.secure_code,
                    'path': str(Path(get_output_dir()) / org.secure_code / 'blocklist.txt'),
                    'count': len(entries),
                    'written': False,
                    'error': None,
                }
            else:
                detail = write_org_edl(org.secure_code)
                if detail.get('written'):
                    written += 1

            if detail.get('error'):
                errors.append(detail)
            details.append(detail)
        except Exception as exc:
            logger.exception('failed to render EDL for org=%s', org.secure_code)
            detail = {
                'org_secure_code': org.secure_code,
                'path': str(Path(get_output_dir()) / org.secure_code / 'blocklist.txt'),
                'count': 0,
                'written': False,
                'error': str(exc),
            }
            errors.append(detail)
            details.append(detail)

    return {
        'orgs': len(orgs),
        'written': written,
        'errors': errors,
        'dry_run': dry_run,
        'details': details,
    }
