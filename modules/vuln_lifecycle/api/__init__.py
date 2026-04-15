"""
VulnLifecycle Module - API Routes
弱點生命週期模組 API

提供弱點儀表板、資產查詢、風險調整的 RESTful API。
資料來源：外部 vulnmgmt PostgreSQL 資料庫。
"""
from flask import Blueprint, jsonify, request

from app.security.decorators import public_route, module_access_required
from app.platform.auth import require_permission, current_user

# 建立 API Blueprint
api_bp = Blueprint(
    'vuln_lifecycle_api',
    __name__,
    url_prefix='/api/vuln-lifecycle'
)


# =============================================================================
# 模組資訊
# =============================================================================

@api_bp.route('/info')
@public_route
def module_info():
    """取得模組資訊"""
    from .. import MODULE_INFO
    return jsonify({
        'success': True,
        'data': {
            'name': MODULE_INFO['name'],
            'display_name': MODULE_INFO['display_name'],
            'version': MODULE_INFO['version'],
        }
    })


# =============================================================================
# 儀表板 API
# =============================================================================

@api_bp.route('/dashboard/summary')
@module_access_required('vuln_lifecycle')
@require_permission('vuln_lifecycle.dashboard.view')
def dashboard_summary():
    """儀表板摘要統計"""
    from ..services.vulnmgmt_db import query, get_deployment_mode

    scanners = query("""
        SELECT ss.name, ss.scanner_type, ss.import_method,
               COUNT(DISTINCT se.id) AS session_count,
               MAX(se.scan_end) AS last_scan
        FROM scanner_sources ss
        LEFT JOIN scan_sessions se ON se.scanner_id = ss.id AND se.status = 'completed'
        GROUP BY ss.id, ss.name, ss.scanner_type, ss.import_method
        ORDER BY ss.name
    """)

    severity_dist = query("""
        SELECT
            COUNT(*) FILTER (WHERE original_severity >= 9.0) AS critical,
            COUNT(*) FILTER (WHERE original_severity >= 7.0 AND original_severity < 9.0) AS high,
            COUNT(*) FILTER (WHERE original_severity >= 4.0 AND original_severity < 7.0) AS medium,
            COUNT(*) FILTER (WHERE original_severity > 0 AND original_severity < 4.0) AS low,
            COUNT(*) FILTER (WHERE original_severity = 0) AS info,
            COUNT(*) AS total
        FROM scan_findings sf
        JOIN scan_sessions se ON sf.session_id = se.id
        WHERE se.status = 'completed'
          AND se.id = (
              SELECT MAX(se2.id) FROM scan_sessions se2
              WHERE se2.scanner_id = se.scanner_id AND se2.status = 'completed'
          )
    """, fetchone=True)

    asset_counts = query("""
        SELECT asset_type, COUNT(*) AS cnt
        FROM assets GROUP BY asset_type
    """)

    adj_stats = query("""
        SELECT adjustment_type, COUNT(*) AS cnt
        FROM risk_adjustments WHERE status = 'ACTIVE'
        GROUP BY adjustment_type
    """)

    return jsonify({
        'success': True,
        'data': {
            'scanners': scanners,
            'severity': severity_dist or {},
            'assets': {r['asset_type']: r['cnt'] for r in asset_counts},
            'adjustments': {r['adjustment_type']: r['cnt'] for r in adj_stats},
            'mode': get_deployment_mode(),
        }
    })


# =============================================================================
# 資產 API
# =============================================================================

@api_bp.route('/assets')
@module_access_required('vuln_lifecycle')
@require_permission('vuln_lifecycle.asset.view')
def asset_list():
    """資產清冊"""
    from ..services.vulnmgmt_db import query

    asset_type = request.args.get('type', '')
    severity_min = float(request.args.get('severity_min', 0))

    sql = """
        SELECT a.id, a.ip, a.hostname, a.asset_type, a.asset_group,
               a.first_seen, a.last_seen,
               COUNT(DISTINCT se.id) AS scan_count,
               COUNT(DISTINCT sf.id) AS finding_count,
               COALESCE(MAX(sf.original_severity), 0) AS max_severity
        FROM assets a
        LEFT JOIN scan_findings sf ON sf.asset_id = a.id
        LEFT JOIN scan_sessions se ON sf.session_id = se.id AND se.status = 'completed'
        WHERE 1=1
    """
    params = []

    if asset_type:
        sql += " AND a.asset_type = %s"
        params.append(asset_type)

    sql += """
        GROUP BY a.id, a.ip, a.hostname, a.asset_type, a.asset_group,
                 a.first_seen, a.last_seen
    """

    if severity_min > 0:
        sql += " HAVING COALESCE(MAX(sf.original_severity), 0) >= %s"
        params.append(severity_min)

    sql += " ORDER BY max_severity DESC, a.ip"

    rows = query(sql, params)
    return jsonify({'success': True, 'data': rows, 'total': len(rows)})


@api_bp.route('/assets/<int:asset_id>/findings')
@module_access_required('vuln_lifecycle')
@require_permission('vuln_lifecycle.finding.view')
def asset_findings(asset_id):
    """單一資產的弱點列表與時間軸"""
    from ..services.vulnmgmt_db import query

    severity_min = float(request.args.get('severity_min', 0))

    asset = query("SELECT * FROM assets WHERE id = %s", (asset_id,), fetchone=True)
    if not asset:
        return jsonify({'success': False, 'message': 'Asset not found'}), 404

    sessions = query("""
        SELECT DISTINCT se.id, se.scan_start, se.scan_end,
               ss.name AS scanner_name
        FROM scan_sessions se
        JOIN scanner_sources ss ON se.scanner_id = ss.id
        JOIN scan_findings sf ON sf.session_id = se.id
        WHERE sf.asset_id = %s AND se.status = 'completed'
        ORDER BY se.scan_start
    """, (asset_id,))

    findings = query("""
        SELECT vd.id AS vuln_id, vd.name AS vuln_name, vd.cve,
               vd.cvss_base, vd.family, vd.epss_score,
               sf.port_number, sf.protocol, sf.original_severity,
               sf.session_id, se.scan_start,
               ra.id AS adj_id, ra.adjustment_type, ra.adjusted_severity,
               ra.status AS adj_status, ra.reviewer, ra.expires_at
        FROM scan_findings sf
        JOIN scan_sessions se ON sf.session_id = se.id
        JOIN vuln_definitions vd ON sf.vuln_id = vd.id
        LEFT JOIN risk_adjustments ra ON ra.asset_id = sf.asset_id
            AND ra.vuln_id = sf.vuln_id AND ra.status = 'ACTIVE'
        WHERE sf.asset_id = %s AND se.status = 'completed'
            AND sf.original_severity >= %s
        ORDER BY vd.name, se.scan_start
    """, (asset_id, severity_min))

    # 組織時間軸
    session_ids = [s['id'] for s in sessions]
    vuln_map = {}
    for f in findings:
        key = (f['vuln_id'], f['port_number'], f['protocol'])
        if key not in vuln_map:
            vuln_map[key] = {
                'vuln_id': f['vuln_id'],
                'vuln_name': f['vuln_name'],
                'cve': f['cve'],
                'cvss_base': float(f['cvss_base']) if f['cvss_base'] else 0,
                'family': f['family'],
                'port': f'{f["port_number"]}/{f["protocol"]}' if f['port_number'] else '-',
                'max_severity': 0,
                'adjustment': None,
                'sessions_found': [],
            }
            if f['adj_id']:
                vuln_map[key]['adjustment'] = {
                    'id': f['adj_id'],
                    'type': f['adjustment_type'],
                    'adjusted_severity': float(f['adjusted_severity']) if f['adjusted_severity'] else None,
                    'reviewer': f['reviewer'],
                }
        sev = float(f['original_severity']) if f['original_severity'] else 0
        if sev > vuln_map[key]['max_severity']:
            vuln_map[key]['max_severity'] = sev
        vuln_map[key]['sessions_found'].append(f['session_id'])

    # 計算生命週期狀態
    timeline = []
    for v in vuln_map.values():
        found_in = set(v['sessions_found'])
        if len(session_ids) >= 2:
            last_id, prev_id = session_ids[-1], session_ids[-2]
            in_last = last_id in found_in
            in_prev = prev_id in found_in
            ever_fixed = any(
                session_ids[i-1] in found_in and session_ids[i] not in found_in
                for i in range(1, len(session_ids))
            )
            if in_last and not in_prev and ever_fixed:
                v['status'] = 'RECURRED'
            elif in_last and in_prev:
                v['status'] = 'OPEN'
            elif in_last and not in_prev:
                v['status'] = 'NEW'
            elif not in_last and in_prev:
                v['status'] = 'FIXED'
            else:
                v['status'] = 'NEW'
        else:
            v['status'] = 'NEW'

        v['presence'] = [sid in found_in for sid in session_ids]
        del v['sessions_found']
        timeline.append(v)

    timeline.sort(key=lambda x: -x['max_severity'])

    return jsonify({
        'success': True,
        'data': {
            'asset': asset,
            'sessions': sessions,
            'findings': timeline,
        }
    })


# =============================================================================
# 風險調整 API
# =============================================================================

@api_bp.route('/risk/adjustments')
@module_access_required('vuln_lifecycle')
@require_permission('vuln_lifecycle.risk.view')
def risk_list():
    """列出風險調整紀錄"""
    from ..services.vulnmgmt_db import query

    status = request.args.get('status', 'ACTIVE')
    rows = query("""
        SELECT ra.*, a.ip, a.hostname, vd.name AS vuln_name, vd.cve
        FROM risk_adjustments ra
        JOIN assets a ON ra.asset_id = a.id
        JOIN vuln_definitions vd ON ra.vuln_id = vd.id
        WHERE ra.status = %s
        ORDER BY ra.updated_at DESC
    """, (status,))
    return jsonify({'success': True, 'data': rows})


@api_bp.route('/risk/adjust', methods=['POST'])
@module_access_required('vuln_lifecycle')
@require_permission('vuln_lifecycle.risk.adjust')
def risk_adjust():
    """提交風險調整（模式2: 將建立表單簽核流程）"""
    from ..services.vulnmgmt_db import execute, get_deployment_mode

    data = request.get_json()
    asset_id = data.get('asset_id')
    vuln_id = data.get('vuln_id')
    adj_type = data.get('adjustment_type')
    adjusted_severity = data.get('adjusted_severity', 0)
    justification = data.get('justification', '')
    expires_at = data.get('expires_at')

    if not justification:
        return jsonify({'success': False, 'message': 'Justification is required'}), 400

    mode = get_deployment_mode()
    reviewer = current_user.display_name if current_user else 'system'

    # 關閉既有 ACTIVE 調整
    execute("""
        UPDATE risk_adjustments
        SET status = 'SUPERSEDED', updated_at = NOW()
        WHERE asset_id = %s AND vuln_id = %s AND status = 'ACTIVE'
    """, (asset_id, vuln_id))

    # 新增調整
    execute("""
        INSERT INTO risk_adjustments
            (asset_id, vuln_id, adjustment_type, adjusted_severity,
             reviewer, review_date, justification, expires_at, status)
        VALUES (%s, %s, %s, %s, %s, NOW(), %s, %s, 'ACTIVE')
    """, (asset_id, vuln_id, adj_type, adjusted_severity,
          reviewer, justification, expires_at))

    # TODO: 模式2時，建立 form_workflow 簽核流程實例
    # if mode == 'platform':
    #     form_instance_code = create_risk_adjustment_form(...)
    #     update risk_adjustments set form_instance_code = ...

    return jsonify({'success': True, 'message': 'Risk adjustment saved'})
