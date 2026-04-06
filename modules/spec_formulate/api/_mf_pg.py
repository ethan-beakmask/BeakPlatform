"""
Multifaceted API - PostgreSQL
企業專屬 DB 資料表操作
"""
import logging
import re

from flask import jsonify, request

from app import db
from app.security.decorators import module_access_required
from app.platform.data import get_current_org

logger = logging.getLogger(__name__)


def register(bp):
    """將路由掛載到 Blueprint"""

    @bp.route('/pg/ensure-db', methods=['POST'])
    @module_access_required('spec_formulate')
    def pg_ensure_db():
        """確保企業專屬 DB 存在，回傳 DB 資訊"""
        from modules.spec_formulate.services.multifaceted.pg_table_manager import (
            ensure_org_database,
        )

        org = get_current_org()
        if not org:
            return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

        try:
            org_db = ensure_org_database(org)
            return jsonify({
                'success': True,
                'data': {
                    'db_name': org_db.db_name,
                    'is_ready': org_db.is_ready,
                },
            })
        except Exception as e:
            logger.exception('企業 DB 建立失敗')
            return jsonify({'success': False, 'error': f'資料庫建立失敗: {str(e)}'}), 500

    @bp.route('/pg/tables', methods=['GET'])
    @module_access_required('spec_formulate')
    def pg_list_tables():
        """列出企業 DB 中的所有資料表"""
        from modules.spec_formulate.services.multifaceted.pg_table_manager import (
            list_tables,
            ensure_org_database,
        )

        org = get_current_org()
        if not org:
            return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

        try:
            ensure_org_database(org)
            tables = list_tables(org.secure_code)
            return jsonify({'success': True, 'data': tables})
        except Exception as e:
            logger.exception('列出資料表失敗')
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route('/pg/tables/<table_name>/introspect', methods=['GET'])
    @module_access_required('spec_formulate')
    def pg_introspect_table(table_name):
        """讀取資料表結構"""
        from modules.spec_formulate.services.multifaceted.pg_table_manager import (
            introspect_table,
        )

        org = get_current_org()
        if not org:
            return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

        try:
            columns = introspect_table(org.secure_code, table_name)
            return jsonify({'success': True, 'data': columns})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route('/specs/<spec_sc>/pg/compare/<table_name>', methods=['GET'])
    @module_access_required('spec_formulate')
    def pg_compare(spec_sc, table_name):
        """比對 SPEC 與資料表結構"""
        from modules.spec_formulate.models import FwSpecMultifaceted
        from modules.spec_formulate.services.multifaceted.pg_table_manager import (
            introspect_table,
            compare_spec_with_table,
        )

        org = get_current_org()
        if not org:
            return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

        spec = FwSpecMultifaceted.query.filter_by(
            secure_code=spec_sc,
            org_secure_code=org.secure_code,
            is_deleted=False,
        ).first()
        if not spec:
            return jsonify({'success': False, 'error': '規格不存在'}), 404

        try:
            columns = introspect_table(org.secure_code, table_name)
            diff = compare_spec_with_table(spec.fields, columns)
            return jsonify({'success': True, 'data': diff})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route('/specs/<spec_sc>/pg/create-table', methods=['POST'])
    @module_access_required('spec_formulate')
    def pg_create_table(spec_sc):
        """
        從 SPEC 建立資料表

        Body: { "table_name": "spec_xxx" }  // 選填，預設用 spec.table_name
        """
        from modules.spec_formulate.models import FwSpecMultifaceted
        from modules.spec_formulate.services.multifaceted.pg_table_manager import (
            ensure_org_database,
            create_table_from_spec,
        )

        org = get_current_org()
        if not org:
            return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

        spec = FwSpecMultifaceted.query.filter_by(
            secure_code=spec_sc,
            org_secure_code=org.secure_code,
            is_deleted=False,
        ).first()
        if not spec:
            return jsonify({'success': False, 'error': '規格不存在'}), 404

        if 'postgresql' not in (spec.active_facets or []):
            return jsonify({
                'success': False,
                'error': '此規格尚未啟用 PostgreSQL 格式',
            }), 400

        data = request.get_json(silent=True) or {}
        table_name = (data.get('table_name') or '').strip() or spec.table_name
        if not table_name:
            return jsonify({
                'success': False,
                'error': '請指定資料表名稱',
            }), 400

        # 驗證表名
        if not re.match(r'^[a-z][a-z0-9_]*$', table_name):
            return jsonify({
                'success': False,
                'error': '資料表名稱只能包含小寫英文、數字和底線，且以英文開頭',
            }), 400

        try:
            ensure_org_database(org)
            result = create_table_from_spec(org.secure_code, table_name, spec.fields)

            if result['success']:
                # 記錄關聯
                spec.linked_sql_table = table_name
                spec.linked_sql_target = 'org'
                db.session.commit()

            return jsonify({
                'success': result['success'],
                'data': result,
                'message': result['message'],
            })
        except Exception as e:
            logger.exception('建立資料表失敗')
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route('/specs/<spec_sc>/pg/apply-to-table', methods=['POST'])
    @module_access_required('spec_formulate')
    def pg_apply_to_table(spec_sc):
        """
        SPEC 覆蓋既有資料表（新增/修改欄位）

        Body: { "table_name": "xxx" }
        """
        from modules.spec_formulate.models import FwSpecMultifaceted
        from modules.spec_formulate.services.multifaceted.pg_table_manager import (
            introspect_table,
            apply_spec_to_table,
        )

        org = get_current_org()
        if not org:
            return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

        spec = FwSpecMultifaceted.query.filter_by(
            secure_code=spec_sc,
            org_secure_code=org.secure_code,
            is_deleted=False,
        ).first()
        if not spec:
            return jsonify({'success': False, 'error': '規格不存在'}), 404

        data = request.get_json(silent=True) or {}
        table_name = (data.get('table_name') or '').strip()
        if not table_name:
            return jsonify({'success': False, 'error': '請指定資料表名稱'}), 400

        try:
            columns = introspect_table(org.secure_code, table_name)
            result = apply_spec_to_table(
                org.secure_code, table_name, spec.fields, columns
            )

            if result['success']:
                spec.linked_sql_table = table_name
                db.session.commit()

            return jsonify({
                'success': result['success'],
                'data': result,
                'message': result['message'],
            })
        except Exception as e:
            logger.exception('覆蓋資料表失敗')
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route('/specs/<spec_sc>/pg/unlink-table', methods=['POST'])
    @module_access_required('spec_formulate')
    def pg_unlink_table(spec_sc):
        """解除資料表關聯"""
        from modules.spec_formulate.models import FwSpecMultifaceted

        org = get_current_org()
        if not org:
            return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

        spec = FwSpecMultifaceted.query.filter_by(
            secure_code=spec_sc,
            org_secure_code=org.secure_code,
            is_deleted=False,
        ).first()
        if not spec:
            return jsonify({'success': False, 'error': '規格不存在'}), 404

        spec.linked_sql_table = None
        spec.linked_sql_target = None
        db.session.commit()

        return jsonify({'success': True, 'message': '已解除資料表關聯'})
