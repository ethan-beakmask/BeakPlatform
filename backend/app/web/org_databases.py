"""
BeakMask Org Database Monitor Web Routes
企業獨立資料庫監視頁面

系統級：/organizations/databases — 可看所有企業（master-detail 佈局）
企業級：/admin/org-database — 企業管理員（master-detail 佈局 + 管理功能）
"""
import logging
import re
from datetime import datetime, date
from decimal import Decimal

import psycopg2
from flask import Blueprint, render_template, abort, jsonify, request
from flask_login import current_user

from .. import db
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
        except RuntimeError as e:
            logger.error(f'OrgDB credential config error: {e}')
            stats = {
                'db_size_bytes': 0,
                'table_count': 0,
                'tables': [],
                'error': '憑證解密失敗，請檢查伺服器環境設定',
            }
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
    系統企業不排除（若已建 DB 就會出現）。
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
    except RuntimeError as e:
        # 配置錯誤（如 SYNC_CREDENTIAL_KEY 未設定）
        logger.error(f'OrgDB credential config error: {e}')
        stats = {
            'db_size_bytes': 0,
            'table_count': 0,
            'tables': [],
            'error': '憑證解密失敗，請檢查伺服器環境設定',
        }
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
    """企業級：master-detail 佈局 + 管理功能"""
    from modules.form_workflow.models.org_database import FwOrgDatabase

    odb = FwOrgDatabase.query.filter_by(
        org_secure_code=current_user.org_secure_code,
        is_deleted=False,
        is_ready=True,
    ).first()

    db_info = None
    tables = []

    if odb:
        try:
            dsn = odb.get_admin_dsn()
            stats = _query_db_stats(dsn)
        except RuntimeError as e:
            logger.error(f'OrgDB credential config error: {e}')
            stats = {
                'db_size_bytes': 0,
                'table_count': 0,
                'tables': [],
                'error': '憑證解密失敗，請檢查伺服器環境設定',
            }
        except Exception as e:
            stats = {
                'db_size_bytes': 0,
                'table_count': 0,
                'tables': [],
                'error': str(e),
            }

        db_info = {
            'db_name': odb.db_name,
            'db_host': odb.db_host,
            'db_port': odb.db_port,
            'admin_user': odb.admin_user,
            'sync_user': odb.sync_user,
            'db_size_display': _format_bytes(stats['db_size_bytes']),
            'last_rotation': odb.last_credential_rotation.strftime('%Y-%m-%d %H:%M')
                if odb.last_credential_rotation else None,
            'error': stats.get('error'),
        }

        for t in stats.get('tables', []):
            tables.append({
                'name': t['name'],
                'row_count': t['row_count'],
                'total_bytes': t['total_bytes'],
                'index_bytes': t['index_bytes'],
                'total_display': _format_bytes(t['total_bytes']),
                'index_display': _format_bytes(t['index_bytes']),
            })

    return render_template(
        'pages/org_databases/monitor.html',
        db_info=db_info,
        tables=tables,
        is_system_view=False,
    )


def _get_org_dsn(org_secure_code):
    """取得企業的 admin DSN，不存在時 abort(404)"""
    from modules.form_workflow.models.org_database import FwOrgDatabase

    odb = FwOrgDatabase.query.filter_by(
        org_secure_code=org_secure_code,
        is_deleted=False,
        is_ready=True,
    ).first()
    if not odb:
        abort(404, description='企業資料庫不存在')
    return odb.get_admin_dsn()


def _validate_table_name(name):
    """驗證表名格式，防止 SQL injection"""
    return bool(re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name))


def _table_exists(cur, table_name):
    """檢查表是否存在於 public schema"""
    cur.execute(
        "SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = %s",
        (table_name,)
    )
    return cur.fetchone() is not None


def _serialize_value(val):
    """序列化 psycopg2 回傳值為 JSON 可序列化格式"""
    if val is None:
        return None
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, (bytes, memoryview)):
        return '(binary)'
    if isinstance(val, Decimal):
        return float(val)
    # 其他非基本型別安全轉字串
    if not isinstance(val, (str, int, float, bool)):
        return str(val)
    return val


@org_databases_bp.route('/admin/org-database/preview/<table_name>')
@admin_required
def preview_table(table_name):
    """預覽企業 DB 指定表的前 100 筆資料"""
    if not _validate_table_name(table_name):
        abort(400, description='無效的表名格式')

    dsn = _get_org_dsn(current_user.org_secure_code)

    try:
        conn = psycopg2.connect(dsn, connect_timeout=5)
    except psycopg2.OperationalError as e:
        err_msg = str(e).strip()
        logger.warning(f'Preview: DB connection failed: {err_msg}')
        if 'does not exist' in err_msg:
            return jsonify({'error': '企業資料庫不存在，可能尚未建立或已被移除'})
        return jsonify({'error': f'資料庫連線失敗: {err_msg}'})

    try:
        with conn.cursor() as cur:
            # 確認表存在
            if not _table_exists(cur, table_name):
                conn.close()
                return jsonify({'error': f'資料表 {table_name} 不存在'})

            # 查欄位名稱與是否有 id 欄位
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s "
                "ORDER BY ordinal_position",
                (table_name,)
            )
            columns = [r[0] for r in cur.fetchall()]
            has_id = 'id' in columns

            # 總筆數
            cur.execute(f'SELECT COUNT(*) FROM "{table_name}"')
            total_count = cur.fetchone()[0]

            # 取 100 筆
            order_clause = ' ORDER BY id DESC' if has_id else ''
            cur.execute(f'SELECT * FROM "{table_name}"{order_clause} LIMIT 100')
            raw_rows = cur.fetchall()

            rows = []
            for raw_row in raw_rows:
                rows.append([_serialize_value(v) for v in raw_row])

            return jsonify({
                'columns': columns,
                'rows': rows,
                'total_count': total_count,
            })
    except psycopg2.Error as e:
        logger.warning(f'Preview table {table_name} failed: {e}')
        return jsonify({'error': f'查詢失敗: {str(e).strip()}'})
    finally:
        conn.close()


@org_databases_bp.route('/admin/org-database/check-references', methods=['POST'])
@admin_required
def check_references():
    """檢查待刪除表的引用關係（FwSqlFormRegistry、DcCrudView）"""
    from modules.form_workflow.models.sql_form_registry import FwSqlFormRegistry
    from modules.nocode_builder.models.crud_view import DcCrudView

    data = request.get_json()
    if not data or not isinstance(data.get('tables'), list):
        abort(400)

    table_names = data['tables']
    org_code = current_user.org_secure_code
    references = {}

    for tname in table_names:
        if not _validate_table_name(tname):
            continue

        # 查 FwSqlFormRegistry
        registry = FwSqlFormRegistry.query.filter_by(
            table_name=tname,
            org_secure_code=org_code,
            is_deleted=False,
        ).filter(FwSqlFormRegistry.status != 'table_dropped').first()

        registry_info = None
        if registry:
            registry_info = {
                'secure_code': registry.secure_code,
                'form_version': registry.form_version,
                'status': registry.status,
                'row_count': registry.row_count,
            }

        # 查 DcCrudView
        crud_views = DcCrudView.query.filter_by(
            table_name=tname,
            org_secure_code=org_code,
            is_deleted=False,
        ).filter(DcCrudView.is_active == True).all()

        crud_list = []
        for cv in crud_views:
            crud_list.append({
                'secure_code': cv.secure_code,
                'name': cv.name,
            })

        references[tname] = {
            'registry': registry_info,
            'crud_views': crud_list,
        }

    return jsonify({'references': references})


@org_databases_bp.route('/admin/org-database/drop-tables', methods=['POST'])
@admin_required
def drop_tables():
    """
    刪除企業 DB 中的資料表

    流程：驗證表存在 → 標記主 DB 引用 → DROP TABLE CASCADE
    """
    from modules.form_workflow.models.sql_form_registry import FwSqlFormRegistry
    from modules.nocode_builder.models.crud_view import DcCrudView

    data = request.get_json()
    if not data or not isinstance(data.get('tables'), list):
        abort(400)

    table_names = data['tables']
    org_code = current_user.org_secure_code
    dsn = _get_org_dsn(org_code)

    results = []
    dropped_count = 0

    try:
        conn = psycopg2.connect(dsn, connect_timeout=5)
        conn.autocommit = False
        try:
            with conn.cursor() as cur:
                for tname in table_names:
                    if not _validate_table_name(tname):
                        results.append({'table': tname, 'dropped': False, 'reason': '無效表名'})
                        continue

                    if not _table_exists(cur, tname):
                        results.append({'table': tname, 'dropped': False, 'reason': '表不存在'})
                        continue

                    # 標記主 DB 引用
                    registries = FwSqlFormRegistry.query.filter_by(
                        table_name=tname,
                        org_secure_code=org_code,
                        is_deleted=False,
                    ).filter(FwSqlFormRegistry.status != 'table_dropped').all()
                    for reg in registries:
                        reg.status = 'table_dropped'
                        reg.updated_at = datetime.utcnow()

                    crud_views = DcCrudView.query.filter_by(
                        table_name=tname,
                        org_secure_code=org_code,
                        is_deleted=False,
                    ).filter(DcCrudView.is_active == True).all()
                    for cv in crud_views:
                        cv.is_active = False
                        desc = cv.description or ''
                        cv.description = desc + '\n[已透過企業獨立資料庫管理刪除]'
                        cv.updated_at = datetime.utcnow()

                    # DROP TABLE
                    cur.execute(f'DROP TABLE IF EXISTS "{tname}" CASCADE')
                    results.append({'table': tname, 'dropped': True})
                    dropped_count += 1

            conn.commit()
            db.session.commit()
        except Exception:
            conn.rollback()
            db.session.rollback()
            raise
        finally:
            conn.close()
    except psycopg2.Error as e:
        logger.error(f'Drop tables failed: {e}')
        return jsonify({'error': str(e)}), 500

    return jsonify({'results': results, 'dropped_count': dropped_count})
