"""
BeakMask Org Database Monitor Web Routes
企業獨立資料庫監視頁面

系統級：/organizations/databases — 可看所有企業（master-detail 佈局）
企業級：/admin/org-database — 只能看見自己企業（卡片佈局）
"""
import logging

import psycopg2
from flask import Blueprint, render_template, abort, jsonify
from flask_login import current_user

from ..security.decorators import system_admin_required, admin_required
from ..models.organization import Organization

logger = logging.getLogger(__name__)

org_databases_bp = Blueprint('org_databases', __name__)


def _query_db_stats(dsn):
    """
    連入企業 DB 查詢統計資訊

    Returns:
        dict with keys: db_size_bytes, table_count, tables[]
        tables[] each: {name, row_count, total_bytes, index_bytes}
    """
    try:
        conn = psycopg2.connect(dsn, connect_timeout=5)
        try:
            with conn.cursor() as cur:
                # 資料庫總大小
                cur.execute("SELECT pg_database_size(current_database())")
                db_size_bytes = cur.fetchone()[0]

                # 各表統計
                cur.execute("""
                    SELECT
                        t.tablename AS table_name,
                        COALESCE(s.n_live_tup, 0) AS row_count,
                        pg_total_relation_size(
                            quote_ident(t.schemaname) || '.' || quote_ident(t.tablename)
                        ) AS total_bytes,
                        pg_indexes_size(
                            (quote_ident(t.schemaname) || '.' || quote_ident(t.tablename))::regclass
                        ) AS index_bytes
                    FROM pg_tables t
                    LEFT JOIN pg_stat_user_tables s
                        ON t.tablename = s.relname AND t.schemaname = s.schemaname
                    WHERE t.schemaname = 'public'
                    ORDER BY total_bytes DESC
                """)
                tables = []
                for row in cur.fetchall():
                    tables.append({
                        'name': row[0],
                        'row_count': row[1],
                        'total_bytes': row[2],
                        'index_bytes': row[3],
                    })

                return {
                    'db_size_bytes': db_size_bytes,
                    'table_count': len(tables),
                    'tables': tables,
                    'error': None,
                }
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f'OrgDB stats query failed: {e}')
        return {
            'db_size_bytes': 0,
            'table_count': 0,
            'tables': [],
            'error': str(e),
        }


def _format_bytes(size_bytes):
    """格式化位元組為人類可讀格式"""
    if size_bytes is None or size_bytes == 0:
        return '0 B'
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    idx = 0
    size = float(size_bytes)
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024
        idx += 1
    if idx == 0:
        return f'{int(size)} B'
    return f'{size:.2f} {units[idx]}'


def _get_org_db_list(org_secure_code=None):
    """
    取得企業 DB 清單及統計

    Args:
        org_secure_code: 若指定，只取該企業的 DB

    Returns:
        list of dict
    """
    from modules.form_workflow.models.org_database import FwOrgDatabase

    query = FwOrgDatabase.query.filter_by(is_deleted=False, is_ready=True)
    if org_secure_code:
        query = query.filter_by(org_secure_code=org_secure_code)

    org_dbs = query.all()
    results = []

    for odb in org_dbs:
        # 查企業名稱
        org = Organization.query.filter_by(id=odb.org_id).first()
        org_name = org.name if org else f'(ID: {odb.org_id})'
        org_domain = org.domain_name if org else '-'
        org_active = org.is_active if org else False

        # 查 DB 統計
        try:
            dsn = odb.get_admin_dsn()
            stats = _query_db_stats(dsn)
        except Exception as e:
            stats = {
                'db_size_bytes': 0,
                'table_count': 0,
                'tables': [],
                'error': str(e),
            }

        results.append({
            'org_id': odb.org_id,
            'org_name': org_name,
            'org_domain': org_domain,
            'org_active': org_active,
            'org_secure_code': odb.org_secure_code,
            'db_name': odb.db_name,
            'db_host': odb.db_host,
            'db_port': odb.db_port,
            'admin_user': odb.admin_user,
            'sync_user': odb.sync_user,
            'is_ready': odb.is_ready,
            'last_rotation': odb.last_credential_rotation,
            'stats': stats,
            'db_size_display': _format_bytes(stats['db_size_bytes']),
        })

    return results


@org_databases_bp.route('/organizations/databases')
@system_admin_required
def system_view():
    """
    系統級：master-detail 佈局，只顯示有獨立 DB 的企業

    資料來源：FwOrgDatabase 取有 DB 的 org_id → Organization 取企業資訊。
    system.local 不排除（若已建 DB 就會出現）。
    """
    from modules.form_workflow.models.org_database import FwOrgDatabase

    # 取得有 DB 的 org_id 集合
    org_db_records = FwOrgDatabase.query.filter_by(
        is_deleted=False, is_ready=True
    ).all()
    org_ids_with_db = {r.org_id for r in org_db_records}

    org_list = []
    if org_ids_with_db:
        orgs = Organization.query.filter(
            Organization.is_deleted == False,
            Organization.id.in_(org_ids_with_db),
        ).order_by(Organization.id.asc()).all()

        for org in orgs:
            org_list.append({
                'id': org.id,
                'name': org.name,
                'domain_name': org.domain_name,
                'is_active': org.is_active,
                'secure_code': org.secure_code,
            })

    return render_template(
        'pages/org_databases/monitor.html',
        org_list=org_list,
        is_system_view=True,
    )


@org_databases_bp.route('/organizations/databases/<org_secure_code>/stats')
@system_admin_required
def system_org_stats(org_secure_code):
    """
    AJAX endpoint：查詢指定企業的 DB 統計

    流程：Organization 表確認企業存在 → FwOrgDatabase 取 DSN → 連線查統計
    """
    from modules.form_workflow.models.org_database import FwOrgDatabase

    org = Organization.query.filter_by(
        secure_code=org_secure_code,
        is_deleted=False,
    ).first()
    if not org:
        abort(404)

    odb = FwOrgDatabase.query.filter_by(
        org_id=org.id,
        is_deleted=False,
        is_ready=True,
    ).first()

    if not odb:
        return jsonify({'has_database': False})

    try:
        dsn = odb.get_admin_dsn()
        stats = _query_db_stats(dsn)
    except Exception as e:
        stats = {
            'db_size_bytes': 0,
            'table_count': 0,
            'tables': [],
            'error': str(e),
        }

    return jsonify({
        'has_database': True,
        'db_name': odb.db_name,
        'db_host': odb.db_host,
        'db_port': odb.db_port,
        'admin_user': odb.admin_user,
        'sync_user': odb.sync_user,
        'last_rotation': odb.last_credential_rotation.strftime('%Y-%m-%d %H:%M')
            if odb.last_credential_rotation else None,
        'db_size_display': _format_bytes(stats['db_size_bytes']),
        'stats': stats,
    })


@org_databases_bp.route('/admin/org-database')
@admin_required
def org_view():
    """企業級：只顯示自己企業的獨立資料庫（保留原卡片佈局）"""
    org_db_list = _get_org_db_list(org_secure_code=current_user.org_secure_code)
    return render_template(
        'pages/org_databases/monitor.html',
        org_db_list=org_db_list,
        is_system_view=False,
        format_bytes=_format_bytes,
    )
