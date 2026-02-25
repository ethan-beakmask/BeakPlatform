"""
BeakMask Org Database Monitor Web Routes
企業獨立資料庫監視頁面

系統級：/organizations/databases — 可看所有企業
企業級：/admin/org-database — 只能看見自己企業
"""
import logging

import psycopg2
from flask import Blueprint, render_template, abort
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
    """系統級：顯示所有企業的獨立資料庫"""
    org_db_list = _get_org_db_list()
    return render_template(
        'pages/org_databases/monitor.html',
        org_db_list=org_db_list,
        is_system_view=True,
        format_bytes=_format_bytes,
    )


@org_databases_bp.route('/admin/org-database')
@admin_required
def org_view():
    """企業級：只顯示自己企業的獨立資料庫"""
    org_db_list = _get_org_db_list(org_secure_code=current_user.org_secure_code)
    return render_template(
        'pages/org_databases/monitor.html',
        org_db_list=org_db_list,
        is_system_view=False,
        format_bytes=_format_bytes,
    )
