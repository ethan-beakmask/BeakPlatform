"""
BeakPlatform Security Center API
本機安全 API

安全設計：
- 所有端點需 @admin_required (ORG_ADMIN 或 SYSTEM_ADMIN)
- ORG_ADMIN 只能看自己企業的登入失敗記錄
- SYSTEM_ADMIN 可透過 org_code 參數過濾，預設顯示全部 (含未知網域)
- 時間範圍固定: 上月 1 號 00:00 ~ now
"""
import logging
from datetime import datetime, date
from zoneinfo import ZoneInfo

from flask import Blueprint, request, jsonify, g
from flask_login import current_user
from sqlalchemy import func, extract, text

from ..security.decorators import admin_required
from ..models.audit_log import AuditLog
from ..models.organization import Organization
from ..models.lookup_item import LookupItem
from ..models.broadcast_acknowledgment import BroadcastAcknowledgment
from ..models.user import User
from .. import db

logger = logging.getLogger(__name__)

security_center_bp = Blueprint(
    'api_security_center', __name__,
    url_prefix='/api/security'
)


def _is_sys_admin() -> bool:
    return str(current_user.user_type) == 'SYSTEM_ADMIN'


def _resolve_org_code() -> str:
    """SYSTEM_ADMIN 可指定 org_code，ORG_ADMIN 強制自己企業"""
    if _is_sys_admin():
        return request.args.get('org_code', '')
    return current_user.org_secure_code


def _get_time_range(user_tz):
    """上月 1 號 00:00 ~ now (以用戶時區計算，回傳 UTC 供 DB 查詢)"""
    utc_tz = ZoneInfo('UTC')
    now_local = datetime.now(user_tz)
    if now_local.month == 1:
        start_date = date(now_local.year - 1, 12, 1)
    else:
        start_date = date(now_local.year, now_local.month - 1, 1)
    # 用戶時區的上月 1 號 00:00 → 轉 UTC
    start_local = datetime(start_date.year, start_date.month, start_date.day, 0, 0, 0, tzinfo=user_tz)
    start_utc = start_local.astimezone(utc_tz).replace(tzinfo=None)
    end_utc = datetime.now(utc_tz).replace(tzinfo=None)
    return start_utc, end_utc


@security_center_bp.route('/login-failures', methods=['GET'])
@admin_required
def login_failures():
    """登入錯誤資料 API"""
    org_code = _resolve_org_code()
    is_sys = _is_sys_admin()

    # 用戶時區
    user_tz_name = getattr(g, 'timezone', 'Asia/Taipei')
    try:
        user_tz = ZoneInfo(user_tz_name)
    except Exception:
        user_tz = ZoneInfo('Asia/Taipei')

    start_time, end_time = _get_time_range(user_tz)

    # 基礎查詢條件
    base_filters = [
        AuditLog.action.in_(['LOGIN_FAILED', 'LOGIN_DENIED']),
        AuditLog.created_at >= start_time,
        AuditLog.created_at <= end_time,
        AuditLog.is_deleted == False,
    ]

    # 企業過濾
    if not is_sys:
        # ORG_ADMIN: 只看自己企業 (org_secure_code = 自己的)
        base_filters.append(AuditLog.org_secure_code == org_code)
    elif org_code:
        # SYSTEM_ADMIN 指定了企業
        base_filters.append(AuditLog.org_secure_code == org_code)
    # SYSTEM_ADMIN 未指定企業: 不加過濾，含 NULL

    # 查詢所有記錄
    records = db.session.query(
        AuditLog.action,
        AuditLog.details,
        AuditLog.ip_address,
        AuditLog.user_agent,
        AuditLog.org_secure_code,
        AuditLog.created_at,
        AuditLog.status_code,
        AuditLog.request_path,
    ).filter(*base_filters).order_by(AuditLog.created_at.desc()).all()

    # 企業名稱對照
    org_map = {}
    if records:
        org_codes = set(r.org_secure_code for r in records if r.org_secure_code)
        if org_codes:
            orgs = Organization.query.filter(
                Organization.secure_code.in_(org_codes),
                Organization.is_deleted == False,
            ).all()
            for org in orgs:
                org_map[org.secure_code] = {
                    'name': org.display_name or org.name,
                    'domain': org.domain_name,
                }

    utc_tz = ZoneInfo('UTC')

    def _to_user_tz(dt):
        """將 DB 的 UTC naive datetime 轉為用戶時區 aware datetime"""
        return dt.replace(tzinfo=utc_tz).astimezone(user_tz)

    # 組裝回應
    timeline = []
    heatmap = {}  # "YYYY-MM-DD" -> {hour: count}
    ip_stats = {}
    account_stats = {}
    org_stats = {}

    for r in records:
        local_dt = _to_user_tz(r.created_at)
        dt_str = local_dt.strftime('%Y-%m-%d')
        hour = local_dt.hour
        ip = r.ip_address or 'unknown'
        details = r.details or 'unknown'
        org_sc = r.org_secure_code
        org_info = org_map.get(org_sc, {})
        org_name = org_info.get('name', '未知網域') if org_sc else '未知網域'
        org_domain = org_info.get('domain', '-') if org_sc else '-'

        # 解析 UA 簡要
        ua_raw = r.user_agent or '-'
        ua_brief = ua_raw
        if 'iPhone' in ua_raw:
            ua_brief = 'iPhone'
            if 'CriOS' in ua_raw:
                ua_brief += ' / Chrome'
            elif 'Safari' in ua_raw:
                ua_brief += ' / Safari'
        elif 'Android' in ua_raw:
            ua_brief = 'Android'
            if 'Chrome' in ua_raw:
                ua_brief += ' / Chrome'
        elif 'Windows NT' in ua_raw:
            ua_brief = 'Windows'
            if 'Edg/' in ua_raw:
                ua_brief += ' / Edge'
            elif 'Chrome' in ua_raw:
                ua_brief += ' / Chrome'
        elif 'Macintosh' in ua_raw:
            ua_brief = 'Mac'
            if 'Chrome' in ua_raw:
                ua_brief += ' / Chrome'
            elif 'Safari' in ua_raw:
                ua_brief += ' / Safari'
        elif 'curl' in ua_raw or 'Werkzeug' in ua_raw:
            ua_brief = ua_raw[:40]

        # 分類標籤
        if org_sc is None:
            fail_type = 'unknown_domain'
        elif '未知用戶' in details:
            fail_type = 'unknown_user'
        elif r.action == 'LOGIN_DENIED':
            fail_type = 'denied'
        else:
            fail_type = 'wrong_password'

        # timeline
        timeline.append({
            'time': local_dt.strftime('%Y-%m-%d %H:%M:%S'),
            'action': r.action,
            'details': details,
            'ip': ip,
            'ua': ua_raw,
            'ua_brief': ua_brief,
            'org_name': org_name,
            'org_domain': org_domain,
            'org_secure_code': org_sc,
            'status': r.status_code,
            'path': r.request_path or '-',
            'type': fail_type,
        })

        # heatmap
        if dt_str not in heatmap:
            heatmap[dt_str] = {}
        heatmap[dt_str][str(hour)] = heatmap[dt_str].get(str(hour), 0) + 1

        # IP 統計
        if ip not in ip_stats:
            ip_stats[ip] = {'count': 0, 'accounts': [], 'uas': [], 'first': None, 'last': None}
        ip_stats[ip]['count'] += 1
        if details not in ip_stats[ip]['accounts']:
            ip_stats[ip]['accounts'].append(details)
        if ua_brief not in ip_stats[ip]['uas']:
            ip_stats[ip]['uas'].append(ua_brief)
        ts = local_dt.strftime('%Y-%m-%d %H:%M')
        if ip_stats[ip]['first'] is None:
            ip_stats[ip]['first'] = ts
        ip_stats[ip]['last'] = ts

        # 帳號統計
        if details not in account_stats:
            account_stats[details] = {'count': 0, 'ips': [], 'type': fail_type, 'org_name': org_name}
        account_stats[details]['count'] += 1
        if ip not in account_stats[details]['ips']:
            account_stats[details]['ips'].append(ip)

        # 企業統計
        org_key = org_sc or '(NULL)'
        if org_key not in org_stats:
            org_stats[org_key] = {'count': 0, 'name': org_name, 'domain': org_domain}
        org_stats[org_key]['count'] += 1

    return jsonify({
        'time_range': {
            'start': _to_user_tz(start_time).strftime('%Y-%m-%d %H:%M'),
            'end': _to_user_tz(end_time).strftime('%Y-%m-%d %H:%M'),
        },
        'summary': {
            'total': len(records),
            'unknown_domain': sum(1 for r in timeline if r['type'] == 'unknown_domain'),
            'unique_accounts': len(account_stats),
            'unique_ips': len(ip_stats),
            'target_orgs': len(org_stats),
        },
        'heatmap': heatmap,
        'ip_stats': ip_stats,
        'account_stats': account_stats,
        'org_stats': org_stats,
        'timeline': timeline,
    }), 200


# =============================================================================
# 緊急廣播確認統計
# =============================================================================

@security_center_bp.route('/alert-broadcasts/<secure_code>/acks', methods=['GET'])
@admin_required
def get_broadcast_acks(secure_code):
    """
    取得某筆緊急廣播的已確認名單

    ORG_ADMIN 只能查自己企業的廣播。
    """
    org_code = current_user.org_secure_code
    is_sys_admin = str(current_user.user_type) == 'SYSTEM_ADMIN'

    # 設定 RLS context
    db.session.execute(
        db.text("SELECT set_config('app.current_org', :org, true)"),
        {'org': org_code}
    )

    # 確認廣播存在且屬於該企業
    item = LookupItem.query.filter_by(
        secure_code=secure_code,
        category_code='broadcast',
        is_deleted=False,
    ).first()

    if not item:
        return jsonify({'success': False, 'message': '找不到廣播'}), 404

    if not is_sys_admin and item.org_secure_code != org_code:
        return jsonify({'success': False, 'message': '無權限'}), 403

    # 查詢已確認的用戶
    acks = db.session.query(
        BroadcastAcknowledgment, User
    ).join(
        User, User.secure_code == BroadcastAcknowledgment.user_secure_code
    ).filter(
        BroadcastAcknowledgment.broadcast_secure_code == secure_code,
        BroadcastAcknowledgment.is_deleted == False,
    ).order_by(
        BroadcastAcknowledgment.acknowledged_at.asc()
    ).all()

    ack_list = []
    for ack, user in acks:
        ack_list.append({
            'user_secure_code': user.secure_code,
            'display_name': user.display_name,
            'employee_id': user.employee_id,
            'acknowledged_at': ack.acknowledged_at.isoformat() if ack.acknowledged_at else None,
        })

    return jsonify({
        'success': True,
        'broadcast_code': item.code,
        'title': (item.value or {}).get('title', ''),
        'total_acks': len(ack_list),
        'acks': ack_list,
    })
