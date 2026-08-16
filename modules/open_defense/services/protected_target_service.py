"""
OpenDefense Module - Protected Target Service

PF-83: 封鎖決策保護清單判定。這是唯一判定實作,其他寫入點需透過本服務檢查。
"""
import ipaddress
import logging
from typing import NamedTuple, Optional

from flask import current_app, has_app_context
from flask_babel import lazy_gettext as _l

from ..models import OdProtectedTarget

logger = logging.getLogger(__name__)


CHECKED_ACTIONS = ('block',)
CHECKED_TARGET_TYPES = ('ip', 'ipv6', 'cidr')

BUILTIN_PROTECTED_NETWORKS = (
    (ipaddress.ip_network('0.0.0.0/8'), _l('本網路')),
    (ipaddress.ip_network('10.0.0.0/8'), _l('私有網段 (RFC1918)')),
    (ipaddress.ip_network('100.64.0.0/10'), _l('CGNAT (RFC6598)')),
    (ipaddress.ip_network('127.0.0.0/8'), _l('回送位址')),
    (ipaddress.ip_network('169.254.0.0/16'), _l('Link-local')),
    (ipaddress.ip_network('172.16.0.0/12'), _l('私有網段 (RFC1918)')),
    (ipaddress.ip_network('192.0.0.0/24'), _l('IETF 協定保留')),
    (ipaddress.ip_network('192.168.0.0/16'), _l('私有網段 (RFC1918)')),
    (ipaddress.ip_network('198.18.0.0/15'), _l('效能測試保留')),
    (ipaddress.ip_network('224.0.0.0/4'), _l('群播位址')),
    (ipaddress.ip_network('240.0.0.0/4'), _l('保留位址')),
    (ipaddress.ip_network('::/128'), _l('未指定位址')),
    (ipaddress.ip_network('::1/128'), _l('回送位址')),
    (ipaddress.ip_network('fc00::/7'), _l('唯一區域位址 (ULA)')),
    (ipaddress.ip_network('fe80::/10'), _l('Link-local')),
    (ipaddress.ip_network('ff00::/8'), _l('群播位址')),
)

# TRUSTED_PROXY_IPS 是平台自身的反向代理位址：判定必須生效，但不得對租戶具名揭露。
PLATFORM_SOURCE = 'platform'
PLATFORM_PROTECTED_LABEL = _l('平台基礎設施')


class InvalidTargetValueError(ValueError):
    """target_value 不是合法的 IP / CIDR"""


class ProtectedHit(NamedTuple):
    source: str
    network: str
    label: str
    entry_secure_code: Optional[str]


def parse_target_network(target_value: str) -> ipaddress._BaseNetwork:
    value = (target_value or '').strip()
    try:
        net = ipaddress.ip_network(value, strict=False)
    except ValueError as exc:
        raise InvalidTargetValueError(str(exc)) from exc

    if net.version == 6 and net.prefixlen >= 96:
        mapped = net.network_address.ipv4_mapped
        if mapped is not None:
            return ipaddress.IPv4Network(f'{mapped}/{net.prefixlen - 96}', strict=False)
    return net


def _networks_overlap(left, right) -> bool:
    return left.version == right.version and left.overlaps(right)


def _is_subnet_of(child, parent) -> bool:
    return child.version == parent.version and child.subnet_of(parent)


def _config_protected_networks():
    if not has_app_context():
        return []

    networks = []
    sources = (
        ('config', current_app.config.get('OD_PROTECTED_EXTRA_NETWORKS') or ()),
        (PLATFORM_SOURCE, current_app.config.get('TRUSTED_PROXY_IPS') or ()),
    )
    for source, values in sources:
        for value in values:
            try:
                net = parse_target_network(str(value))
            except InvalidTargetValueError:
                logger.warning('OpenDefense protected target config ignored invalid network: %r', value)
                continue
            networks.append((net, source, str(value), None))
    return networks


def _fallback_builtin_networks():
    return [
        (network, 'builtin', str(label), None)
        for network, label in BUILTIN_PROTECTED_NETWORKS
    ]


def _org_builtin_networks(org_secure_code):
    """回傳 (networks, fallback_used)。"""
    if not has_app_context() or not org_secure_code:
        return _fallback_builtin_networks(), True

    try:
        # 判斷要不要 fail-safe 看的是有沒有 builtin 記錄（不帶 is_active 過濾）；
        # 實際判定才只取 is_active=True。兩個查詢條件刻意不同：
        # 企業合法地把 16 條全部停用是正常設定，若 fail-safe 帶了 is_active
        # 過濾，這種情況會被誤判成 seed 漏了而回退硬編碼常數，靜默忽略停用。
        entries = OdProtectedTarget.query.filter_by(
            org_secure_code=org_secure_code,
            origin='builtin',
            entry_type='protect',
            is_deleted=False,
        ).all()
    except Exception:
        logger.exception(
            'OpenDefense protected target builtin query failed org=%s',
            org_secure_code,
        )
        return _fallback_builtin_networks(), True

    if not entries:
        return _fallback_builtin_networks(), True

    networks = []
    for entry in entries:
        if not entry.is_active:
            continue
        try:
            net = parse_target_network(entry.target_value)
        except InvalidTargetValueError:
            logger.warning(
                'OpenDefense protected target builtin entry ignored invalid network sc=%s org=%s value=%r',
                entry.secure_code, org_secure_code, entry.target_value,
            )
            continue
        networks.append((
            net,
            'builtin',
            entry.name or entry.target_value,
            entry.secure_code,
        ))
    return networks, False


def list_effective_networks(org_secure_code=None) -> tuple:
    """列出與判定共用的 fail-safe 內建/設定來源保護網段,供管理頁唯讀展示。"""
    builtin_networks, fallback_used = _org_builtin_networks(org_secure_code)
    builtin = []
    if fallback_used:
        builtin = [
            {
                'network': str(network),
                'label': label,
            }
            for network, _source, label, _entry_secure_code in builtin_networks
        ]
    config = [
        {
            'network': str(network),
            'label': str(label),
        }
        for network, source, label, _entry_secure_code in _config_protected_networks()
        if source == 'config'
    ]
    return builtin, config


def _custom_entries(org_secure_code: str, entry_type: str):
    if not has_app_context():
        return []

    return OdProtectedTarget.query.filter_by(
        org_secure_code=org_secure_code,
        origin='custom',
        entry_type=entry_type,
        is_active=True,
        is_deleted=False,
    ).all()


def _custom_networks(org_secure_code: str, entry_type: str):
    networks = []
    for entry in _custom_entries(org_secure_code, entry_type):
        try:
            net = parse_target_network(entry.target_value)
        except InvalidTargetValueError:
            logger.warning(
                'OpenDefense protected target custom entry ignored invalid network sc=%s org=%s value=%r',
                entry.secure_code, org_secure_code, entry.target_value,
            )
            continue
        networks.append((
            net,
            'custom',
            entry.name or entry.target_value,
            entry.secure_code,
        ))
    return networks


def check_block_target(*, org_secure_code, action, target_type, target_value) -> Optional[ProtectedHit]:
    if action not in CHECKED_ACTIONS:
        return None
    if target_type not in CHECKED_TARGET_TYPES:
        return None

    net = parse_target_network(target_value)

    protected = []
    builtin_networks, _fallback_used = _org_builtin_networks(org_secure_code)
    protected.extend(builtin_networks)
    protected.extend(_config_protected_networks())
    protected.extend(_custom_networks(org_secure_code, 'protect'))

    hits = [
        (protected_net, source, label, entry_secure_code)
        for protected_net, source, label, entry_secure_code in protected
        if _networks_overlap(protected_net, net)
    ]
    if not hits:
        return None

    for exempt_net, _source, label, entry_secure_code in _custom_networks(org_secure_code, 'exempt'):
        if _is_subnet_of(net, exempt_net):
            logger.info(
                'OpenDefense protected target exempt applied org=%s target=%s exempt=%s entry=%s label=%s',
                org_secure_code, target_value, exempt_net, entry_secure_code, label,
            )
            return None

    source_priority = {PLATFORM_SOURCE: -1, 'builtin': 0, 'config': 1, 'custom': 2}
    protected_net, source, label, entry_secure_code = max(
        hits,
        key=lambda item: (source_priority.get(item[1], -1), item[0].prefixlen),
    )
    return ProtectedHit(
        source=source,
        network=str(protected_net),
        label=label,
        entry_secure_code=entry_secure_code,
    )


def public_hit_view(hit) -> Optional[dict]:
    """把 ProtectedHit 轉成可對租戶揭露的形式。

    platform 來源（平台自身的反向代理位址）不具名：network 一律回 None，
    label 退為泛稱。其餘來源原樣回傳。
    """
    if hit is None:
        return None
    if hit.source == PLATFORM_SOURCE:
        return {
            'source': PLATFORM_SOURCE,
            'network': None,
            'label': str(PLATFORM_PROTECTED_LABEL),
            'entry_secure_code': None,
        }
    return {
        'source': hit.source,
        'network': hit.network,
        'label': hit.label,
        'entry_secure_code': hit.entry_secure_code,
    }


def describe_protection(*, org_secure_code, target_value) -> dict:
    try:
        hit = check_block_target(
            org_secure_code=org_secure_code,
            action='block',
            target_type='cidr',
            target_value=target_value,
        )
    except InvalidTargetValueError:
        return {
            'target_value': target_value,
            'protected': False,
            'hit': None,
            'error': 'invalid_target',
        }

    return {
        'target_value': target_value,
        'protected': hit is not None,
        'hit': public_hit_view(hit),
        'error': None,
    }
