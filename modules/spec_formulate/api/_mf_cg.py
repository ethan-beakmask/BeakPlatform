"""
Multifaceted API - Conglomerate DB
集團共享 DB 資料表操作
"""
import logging
import re

from flask import jsonify, request

from app import db
from app.security.decorators import module_access_required
from app.platform.data import get_current_org

logger = logging.getLogger(__name__)


def _get_org_conglomerate(org):
    """
    取得企業所屬的集團（需有共享 DB）

    Returns:
        (Conglomerate, error_response) -- 成功時 error_response=None
    """
    from app.models.conglomerate import Conglomerate

    if not org.conglomerate_secure_code:
        return None, (jsonify({
            'success': False, 'error': '此企業不屬於任何集團',
        }), 400)

    cg = Conglomerate.query.filter_by(
        secure_code=org.conglomerate_secure_code,
        is_deleted=False,
    ).first()
    if not cg:
        return None, (jsonify({
            'success': False, 'error': '集團不存在',
        }), 404)

    if not cg.has_shared_db:
        return None, (jsonify({
            'success': False, 'error': '此集團尚未建立共享資料庫',
        }), 400)

    return cg, None


def register(bp):
    """將路由掛載到 Blueprint"""

    @bp.route('/cg/info', methods=['GET'])
    @module_access_required('spec_formulate')
    def cg_info():
        """
        取得當前企業的集團共享 DB 資訊

        用於前端判斷是否顯示集團 DB 選項
        """
        org = get_current_org()
        if not org:
            return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

        if not org.conglomerate_secure_code:
            return jsonify({'success': True, 'data': {'has_conglomerate_db': False}})

        from app.models.conglomerate import Conglomerate
        cg = Conglomerate.query.filter_by(
            secure_code=org.conglomerate_secure_code,
            is_deleted=False,
        ).first()

        if not cg or not cg.has_shared_db:
            return jsonify({'success': True, 'data': {'has_conglomerate_db': False}})

        return jsonify({'success': True, 'data': {
            'has_conglomerate_db': True,
            'conglomerate_name': cg.name,
            'conglomerate_code': cg.code,
        }})

    @bp.route('/cg/tables', methods=['GET'])
    @module_access_required('spec_formulate')
    def cg_list_tables():
        """列出集團共享 DB 中的所有資料表"""
        from modules.spec_formulate.services.multifaceted.pg_table_manager import (
            cg_list_tables as _cg_list_tables,
        )

        org = get_current_org()
        if not org:
            return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

        cg, err = _get_org_conglomerate(org)
        if err:
            return err

        try:
            tables = _cg_list_tables(cg.secure_code)

            # 附加每張表的建立者資訊
            from modules.spec_formulate.models.conglomerate_table_registry import (
                FwConglomerateTableRegistry,
            )
            registry_map = {}
            registries = FwConglomerateTableRegistry.query.filter_by(
                conglomerate_secure_code=cg.secure_code,
                status='active',
                is_deleted=False,
            ).all()
            for r in registries:
                registry_map[r.table_name] = {
                    'creator_org_name': r.creator_org_name,
                    'is_owner': r.creator_org_secure_code == org.secure_code,
                }

            table_list = []
            for t in tables:
                info = registry_map.get(t, {})
                table_list.append({
                    'name': t,
                    'creator_org_name': info.get('creator_org_name', '(unknown)'),
                    'is_owner': info.get('is_owner', False),
                })

            return jsonify({'success': True, 'data': table_list})
        except Exception as e:
            logger.exception('列出集團資料表失敗')
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route('/cg/tables/<table_name>/introspect', methods=['GET'])
    @module_access_required('spec_formulate')
    def cg_introspect_table(table_name):
        """讀取集團共享 DB 中指定表的結構"""
        from modules.spec_formulate.services.multifaceted.pg_table_manager import (
            cg_introspect_table as _cg_introspect,
        )

        org = get_current_org()
        if not org:
            return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

        cg, err = _get_org_conglomerate(org)
        if err:
            return err

        try:
            columns = _cg_introspect(cg.secure_code, table_name)
            return jsonify({'success': True, 'data': columns})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route(
        '/specs/<spec_sc>/cg/compare/<table_name>', methods=['GET']
    )
    @module_access_required('spec_formulate')
    def cg_compare(spec_sc, table_name):
        """比對 SPEC 與集團共享 DB 中的表結構"""
        from modules.spec_formulate.models import FwSpecMultifaceted
        from modules.spec_formulate.services.multifaceted.pg_table_manager import (
            cg_introspect_table as _cg_introspect,
            cg_compare_spec_with_table,
        )

        org = get_current_org()
        if not org:
            return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

        cg, err = _get_org_conglomerate(org)
        if err:
            return err

        spec = FwSpecMultifaceted.query.filter_by(
            secure_code=spec_sc,
            org_secure_code=org.secure_code,
            is_deleted=False,
        ).first()
        if not spec:
            return jsonify({'success': False, 'error': '規格不存在'}), 404

        try:
            columns = _cg_introspect(cg.secure_code, table_name)
            diff = cg_compare_spec_with_table(spec.fields, columns)
            return jsonify({'success': True, 'data': diff})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route(
        '/specs/<spec_sc>/cg/create-table', methods=['POST']
    )
    @module_access_required('spec_formulate')
    def cg_create_table(spec_sc):
        """
        從 SPEC 在集團共享 DB 建立資料表

        自動附加 owner_org_code + RLS policy。
        建立者企業記錄在 FwConglomerateTableRegistry。

        Body: { "table_name": "spec_xxx" }
        """
        from modules.spec_formulate.models import FwSpecMultifaceted
        from modules.spec_formulate.services.multifaceted.pg_table_manager import (
            cg_create_table_from_spec,
        )

        org = get_current_org()
        if not org:
            return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

        cg, err = _get_org_conglomerate(org)
        if err:
            return err

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
            return jsonify({'success': False, 'error': '請指定資料表名稱'}), 400

        if not re.match(r'^[a-z][a-z0-9_]*$', table_name):
            return jsonify({
                'success': False,
                'error': '資料表名稱只能包含小寫英文、數字和底線，且以英文開頭',
            }), 400

        try:
            result = cg_create_table_from_spec(
                conglomerate_secure_code=cg.secure_code,
                table_name=table_name,
                spec_fields=spec.fields,
                creator_org_secure_code=org.secure_code,
                creator_org_name=org.name,
                spec_secure_code=spec.secure_code,
            )

            if result['success']:
                spec.linked_sql_table = table_name
                spec.linked_sql_target = 'conglomerate'
                db.session.commit()

            return jsonify({
                'success': result['success'],
                'data': result,
                'message': result['message'],
            })
        except Exception as e:
            logger.exception('集團 DB 建立資料表失敗')
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route(
        '/specs/<spec_sc>/cg/apply-to-table', methods=['POST']
    )
    @module_access_required('spec_formulate')
    def cg_apply_to_table(spec_sc):
        """
        SPEC 覆蓋集團共享 DB 中的既有資料表

        僅建立者企業可執行（ownership check）。

        Body: { "table_name": "xxx" }
        """
        from modules.spec_formulate.models import FwSpecMultifaceted
        from modules.spec_formulate.services.multifaceted.pg_table_manager import (
            cg_introspect_table as _cg_introspect,
            cg_apply_spec_to_table,
        )

        org = get_current_org()
        if not org:
            return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

        cg, err = _get_org_conglomerate(org)
        if err:
            return err

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
            columns = _cg_introspect(cg.secure_code, table_name)
            result = cg_apply_spec_to_table(
                cg.secure_code, table_name, spec.fields, columns,
                org.secure_code,
            )

            if result['success']:
                spec.linked_sql_table = table_name
                spec.linked_sql_target = 'conglomerate'
                db.session.commit()

            return jsonify({
                'success': result['success'],
                'data': result,
                'message': result['message'],
            })
        except Exception as e:
            logger.exception('集團 DB 覆蓋資料表失敗')
            return jsonify({'success': False, 'error': str(e)}), 500
