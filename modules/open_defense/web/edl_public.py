"""
OpenDefense public EDL endpoint.

此端點只讀平台端已產出的 EDL 檔案，不在 request path 重新查 DB 渲染。
"""
import ipaddress
import logging
from pathlib import Path

from flask import Blueprint, Response, current_app

from app import limiter
from app.models.organization import Organization
from app.security.decorators import public_route
from app.security.client_ip import get_client_ip, client_ip_key
from modules.open_defense.services.edl_service import get_output_dir


logger = logging.getLogger(__name__)

edl_bp = Blueprint('open_defense_edl', __name__, url_prefix='/edl')


def _plain_404():
    return Response('404 Not Found\n', status=404, content_type='text/plain; charset=utf-8')


def _parse_allowed_networks(value: str):
    networks = []
    for item in (value or '').split(','):
        item = item.strip()
        if not item:
            continue
        networks.append(ipaddress.ip_network(item, strict=False))
    return networks


def is_source_ip_allowed(client_ip: str | None, allowed_ips: str | None) -> bool:
    if not client_ip:
        return False

    try:
        networks = _parse_allowed_networks(allowed_ips or '')
        if not networks:
            return False
        source_ip = ipaddress.ip_address(client_ip)
    except ValueError:
        logger.warning('invalid EDL allowed IP config or client IP rejected')
        return False

    return any(source_ip in network for network in networks)


@edl_bp.route('/<org_secure_code>/blocklist.txt', methods=['GET'])
@public_route
@limiter.limit('60 per minute; 1000 per hour', key_func=client_ip_key)
def blocklist(org_secure_code):
    allowed_ips = current_app.config.get('OD_EDL_ALLOWED_IPS')
    if not is_source_ip_allowed(get_client_ip(), allowed_ips):
        return _plain_404()

    org = Organization.query.filter(
        Organization.secure_code == org_secure_code,
        Organization.is_deleted == False,
    ).first()
    if org is None:
        return _plain_404()

    path = Path(get_output_dir()) / org_secure_code / 'blocklist.txt'
    if not path.is_file():
        return _plain_404()

    try:
        text = path.read_text(encoding='utf-8')
    except OSError:
        logger.exception('failed to read EDL file for org=%s path=%s', org_secure_code, path)
        return _plain_404()

    response = Response(text, content_type='text/plain; charset=utf-8')
    response.headers['Cache-Control'] = 'no-store'
    return response
