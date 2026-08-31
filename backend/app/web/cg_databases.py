"""
BeakPlatform Conglomerate Database Overview
集團資料庫總覽

系統管理員檢視所有 cg_* 資料庫，包含：
- 有 fw_conglomerate_databases 記錄的正常資料庫
- PostgreSQL 中存在但無記錄的孤兒資料庫
- 各資料庫的成員企業與異動歷程

連線策略：
- cg_* 資料庫有 REVOKE CONNECT FROM PUBLIC，一般帳號無法連入
- 大小查詢用 postgres superuser 從 pg_database_size() 取得
- 表數量需連入個別 DB，此頁不做（避免憑證相依）
"""
import logging
import os

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from flask_babel import gettext as _
from flask import Blueprint, render_template, jsonify, abort

from ..security.decorators import system_admin_required
from ..models.conglomerate import Conglomerate
from ..models.conglomerate_log import ConglomerateLog
from ..models.organization import Organization

logger = logging.getLogger(__name__)

cg_databases_bp = Blueprint('cg_databases', __name__)

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


def _scan_cg_databases_with_size():
    """
    用 superuser 掃描所有 cg_* 資料庫及其大小

    Returns:
        dict: {db_name: size_bytes, ...}
    """
    # superuser 憑證沿用 sql_sync 的 SYNC_PG_ADMIN_URL（.env），不硬編碼（PF-199）。
    # 未設定時降級為「查不到大小」，與連線失敗同一種表現。
    dsn = os.environ.get('SYNC_PG_ADMIN_URL')
    if not dsn:
        logger.warning('CgDB overview: SYNC_PG_ADMIN_URL 未設定，無法掃描 pg_database')
        return {}
    try:
        conn = psycopg2.connect(dsn, connect_timeout=5)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT datname, pg_database_size(datname) "
                    "FROM pg_database "
                    "WHERE datname LIKE 'cg_%' ORDER BY datname"
                )
                return {row[0]: row[1] for row in cur.fetchall()}
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f'CgDB overview: 掃描 pg_database 失敗: {e}')
        return {}


@cg_databases_bp.route('/admin/cg-databases')
@system_admin_required
def overview():
    """集團資料庫總覽頁面"""
    return render_template('pages/cg_databases/overview.html')


@cg_databases_bp.route('/admin/cg-databases/data')
@system_admin_required
def overview_data():
    """
    AJAX: 取得集團資料庫總覽資料

    回傳所有 cg_* 資料庫的資訊，包含孤兒資料庫。
    大小透過 superuser 一次查完，不需逐個連入。
    """
    from modules.form_workflow.models.conglomerate_database import (
        FwConglomerateDatabase,
    )

    # 1. 從 fw_conglomerate_databases 取有記錄的
    cg_db_records = FwConglomerateDatabase.query.filter_by(
        is_deleted=False
    ).all()
    record_map = {r.db_name: r for r in cg_db_records}

    # 2. 掃描 PostgreSQL 中所有 cg_* 資料庫（含大小）
    pg_db_sizes = _scan_cg_databases_with_size()

    # 3. 合併
    all_db_names = sorted(record_map.keys() | pg_db_sizes.keys())

    results = []
    for db_name in all_db_names:
        record = record_map.get(db_name)
        exists_in_pg = db_name in pg_db_sizes
        size_bytes = pg_db_sizes.get(db_name, 0)

        entry = {
            'db_name': db_name,
            'exists_in_pg': exists_in_pg,
            'has_record': record is not None,
            'is_orphan': exists_in_pg and record is None,
            'is_ghost_record': not exists_in_pg and record is not None,
            'db_size_bytes': size_bytes,
            'db_size_display': _format_bytes(size_bytes) if exists_in_pg else '-',
        }

        if record:
            cg = Conglomerate.query.filter_by(
                secure_code=record.conglomerate_secure_code,
                is_deleted=False,
            ).first()

            members = []
            if cg:
                orgs = Organization.query.filter(
                    Organization.conglomerate_secure_code == cg.secure_code,
                    Organization.is_deleted == False,
                ).order_by(Organization.name).all()
                for org in orgs:
                    members.append({
                        'name': org.name,
                        'code': org.code,
                        'is_active': org.is_active,
                        'secure_code': org.secure_code,
                    })

            entry.update({
                'conglomerate_id': record.conglomerate_id,
                'conglomerate_name': cg.name if cg else _('(集團已刪除)'),
                'conglomerate_code': cg.code if cg else '-',
                'conglomerate_active': cg.is_active if cg else False,
                'conglomerate_secure_code': record.conglomerate_secure_code,
                'is_ready': record.is_ready,
                'admin_user': record.admin_user,
                'member_user': record.member_user,
                'db_host': record.db_host,
                'db_port': record.db_port,
                'created_at': record.created_at.isoformat()
                    if record.created_at else None,
                'members': members,
                'member_count': len(members),
            })
        else:
            entry.update({
                'conglomerate_id': None,
                'conglomerate_name': None,
                'conglomerate_code': None,
                'conglomerate_active': None,
                'conglomerate_secure_code': None,
                'is_ready': None,
                'admin_user': None,
                'member_user': None,
                'db_host': None,
                'db_port': None,
                'created_at': None,
                'members': [],
                'member_count': 0,
            })

        results.append(entry)

    return jsonify({'databases': results})


@cg_databases_bp.route(
    '/admin/cg-databases/<conglomerate_secure_code>/logs'
)
@system_admin_required
def db_logs(conglomerate_secure_code):
    """
    AJAX: 查詢指定集團的異動歷程
    """
    logs = ConglomerateLog.query.filter_by(
        conglomerate_secure_code=conglomerate_secure_code,
    ).order_by(ConglomerateLog.created_at.desc()).limit(200).all()

    result = []
    for log in logs:
        org = Organization.query.filter_by(
            secure_code=log.org_secure_code,
        ).first()

        result.append({
            'action': log.action,
            'org_name': org.name if org else f'({log.org_secure_code})',
            'org_code': org.code if org else '-',
            'operator_email': log.operator_email,
            'description': log.description,
            'created_at': log.created_at.isoformat()
                if log.created_at else None,
        })

    return jsonify({'logs': result})
