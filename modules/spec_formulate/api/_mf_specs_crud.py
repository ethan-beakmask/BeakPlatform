"""
Schema API - Specs CRUD
翻譯、Data Class、規格 CRUD、版本歷史、Facet 填充
"""
import logging
from datetime import datetime, timezone

from flask import jsonify, request
from flask_babel import gettext as _

from app import db
from app.security.decorators import module_access_required, page_keys_required
from app.platform.data import get_current_org

from ._mf_helpers import _get_user_info, _fields_identical

logger = logging.getLogger(__name__)


def register(bp):
    """將路由掛載到 Blueprint"""

    # ── 翻譯輔助 API ──

    @bp.route('/translate', methods=['POST'])
    @module_access_required('spec_formulate')
    @page_keys_required('spec_formulate.spec_schema')
    def translate_name():
        """
        將中文名稱翻譯為英文識別碼（小寫 snake_case）

        POST body:
        {
            "name": "文具庫存表",
            "prefix": "spec_",      // 選填，預設空
            "mode": "table_name"    // table_name 或 field_key
        }

        Response: { "success": true, "code": "spec_stationery_inventory" }
        """
        from app.services.code_generator import get_code_generator

        data = request.get_json(silent=True) or {}
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'success': False, 'error': _('名稱不可為空')}), 400

        prefix = (data.get('prefix') or '').strip()

        generator = get_code_generator()
        try:
            raw = generator.generate(name, exists_checker=None)
            # 轉小寫 snake_case
            code = raw.lower()
            if prefix:
                code = prefix + code
            return jsonify({'success': True, 'code': code})
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 400

    # ── Data Class Registry API ──

    @bp.route('/data-classes', methods=['GET'])
    @module_access_required('spec_formulate')
    @page_keys_required('spec_formulate.spec_schema')
    def list_data_classes():
        """取得所有 data_class 清單（含格式支援資訊）"""
        from modules.spec_formulate.services.schema.data_class_registry import (
            get_data_class_list,
        )
        return jsonify({'success': True, 'data': get_data_class_list()})

    @bp.route('/data-classes/<data_class>/facet-defaults/<facet_name>',
              methods=['GET'])
    @module_access_required('spec_formulate')
    @page_keys_required('spec_formulate.spec_schema')
    def get_data_class_facet_defaults(data_class, facet_name):
        """取得指定 data_class 在特定格式下的預設 facet 值"""
        from modules.spec_formulate.services.schema.data_class_registry import (
            get_facet_defaults,
            is_facet_supported,
            get_unsupported_reason,
        )
        if not is_facet_supported(data_class, facet_name):
            reason = get_unsupported_reason(data_class, facet_name)
            return jsonify({
                'success': False,
                'supported': False,
                'reason': reason,
            }), 200

        defaults = get_facet_defaults(data_class, facet_name)
        # 過濾掉 meta 欄位
        clean = {
            k: v for k, v in defaults.items()
            if k not in ('supported', 'reason', 'note')
        }
        return jsonify({
            'success': True,
            'supported': True,
            'defaults': clean,
            'note': defaults.get('note'),
        })

    # ── SPEC CRUD ──

    @bp.route('/specs', methods=['GET'])
    @module_access_required('spec_formulate')
    @page_keys_required('spec_formulate.spec_schema')
    def list_specs():
        """列出所有多面向規格"""
        from modules.spec_formulate.models import FwSpecSchema

        org = get_current_org()
        if not org:
            return jsonify({'success': False, 'error': _('無法取得企業資訊')}), 403

        specs = FwSpecSchema.query.filter_by(
            org_secure_code=org.secure_code,
            is_deleted=False,
        ).order_by(
            FwSpecSchema.updated_at.desc()
        ).all()

        result = []
        for s in specs:
            d = s.to_dict()
            d['field_count'] = len(s.fields or [])
            result.append(d)

        return jsonify({'success': True, 'data': result})

    @bp.route('/specs', methods=['POST'])
    @module_access_required('spec_formulate')
    @page_keys_required('spec_formulate.spec_schema')
    def create_spec():
        """建立多面向規格"""
        from modules.spec_formulate.models import FwSpecSchema
        from modules.spec_formulate.services.schema.field_normalizer import (
            normalize_fields,
        )

        org = get_current_org()
        if not org:
            return jsonify({'success': False, 'error': _('無法取得企業資訊')}), 403

        data = request.get_json(silent=True) or {}
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'success': False, 'error': _('規格名稱必填')}), 400

        table_name = (data.get('table_name') or '').strip()
        description = (data.get('description') or '').strip()
        raw_fields = data.get('fields', [])

        # 正規化與驗證
        fields, warnings, errors = normalize_fields(raw_fields)
        if errors:
            return jsonify({
                'success': False,
                'error': _('欄位驗證失敗'),
                'details': errors,
            }), 400

        user_sc, user_name = _get_user_info()

        spec = FwSpecSchema(
            org_secure_code=org.secure_code,
            name=name,
            table_name=table_name or None,
            description=description,
            version=1,
            fields=fields,
            active_facets=[],
            status='active',
            last_modified_by=user_sc,
            last_modified_by_name=user_name,
        )
        db.session.add(spec)
        db.session.commit()

        result = spec.to_dict()
        result['field_count'] = len(fields)
        result['warnings'] = warnings

        return jsonify({
            'success': True,
            'data': result,
            'message': _('已建立規格「%(name)s」', name=name),
        }), 201

    @bp.route('/specs/<spec_sc>', methods=['GET'])
    @module_access_required('spec_formulate')
    @page_keys_required('spec_formulate.spec_schema')
    def get_spec(spec_sc):
        """取得單一多面向規格"""
        from modules.spec_formulate.models import FwSpecSchema

        org = get_current_org()
        if not org:
            return jsonify({'success': False, 'error': _('無法取得企業資訊')}), 403

        spec = FwSpecSchema.query.filter_by(
            secure_code=spec_sc,
            org_secure_code=org.secure_code,
            is_deleted=False,
        ).first()

        if not spec:
            return jsonify({'success': False, 'error': _('規格不存在')}), 404

        result = spec.to_dict()
        result['field_count'] = len(spec.fields or [])

        # 補上關聯表單名稱
        if spec.linked_form_template_sc:
            from modules.form_workflow.models.form_template import FwFormTemplate
            ft = FwFormTemplate.query.filter_by(
                secure_code=spec.linked_form_template_sc,
                is_deleted=False,
            ).first()
            result['linked_form_template_name'] = ft.name if ft else ''

        return jsonify({'success': True, 'data': result})

    @bp.route('/specs/<spec_sc>', methods=['POST'])
    @module_access_required('spec_formulate')
    @page_keys_required('spec_formulate.spec_schema')
    def update_spec(spec_sc):
        """更新多面向規格（自動版本遞增 + 歷史記錄）"""
        from modules.spec_formulate.models import (
            FwSpecSchema,
            FwSpecSchemaHistory,
        )
        from modules.spec_formulate.services.schema.field_normalizer import (
            normalize_fields,
            compute_diff,
        )

        org = get_current_org()
        if not org:
            return jsonify({'success': False, 'error': _('無法取得企業資訊')}), 403

        spec = FwSpecSchema.query.filter_by(
            secure_code=spec_sc,
            org_secure_code=org.secure_code,
            is_deleted=False,
        ).first()

        if not spec:
            return jsonify({'success': False, 'error': _('規格不存在')}), 404

        data = request.get_json(silent=True) or {}
        raw_fields = data.get('fields', [])

        # 正規化與驗證
        fields, warnings, errors = normalize_fields(raw_fields)
        if errors:
            return jsonify({
                'success': False,
                'error': _('欄位驗證失敗'),
                'details': errors,
            }), 400

        # 檢查是否有實際變更
        old_fields = spec.fields or []
        name = (data.get('name') or '').strip() or spec.name
        table_name = (data.get('table_name') or '').strip()
        description = data.get('description', spec.description)

        if _fields_identical(old_fields, fields) and name == spec.name:
            return jsonify({
                'success': True,
                'data': spec.to_dict(),
                'message': _('內容無變更，未建立新版本'),
            })

        # 計算差異
        diff = compute_diff(old_fields, fields)
        user_sc, user_name = _get_user_info()

        # 寫入歷史（儲存舊版快照）
        history = FwSpecSchemaHistory(
            spec_secure_code=spec.secure_code,
            version=spec.version,
            fields_snapshot=old_fields,
            active_facets_snapshot=list(spec.active_facets or []),
            change_description=data.get('change_description', ''),
            change_diff=diff,
            changed_by=user_sc,
            changed_by_name=user_name,
            org_secure_code=org.secure_code,
        )
        db.session.add(history)

        # 更新 spec
        spec.name = name
        if table_name:
            spec.table_name = table_name
        spec.description = description
        spec.version += 1
        spec.fields = fields
        spec.last_modified_by = user_sc
        spec.last_modified_by_name = user_name
        spec.updated_at = datetime.now(timezone.utc)

        db.session.commit()

        result = spec.to_dict()
        result['field_count'] = len(fields)
        result['warnings'] = warnings
        result['diff'] = diff

        return jsonify({
            'success': True,
            'data': result,
            'message': _('已更新至 v%(version)s', version=spec.version),
        })

    @bp.route('/specs/<spec_sc>', methods=['DELETE'])
    @module_access_required('spec_formulate')
    @page_keys_required('spec_formulate.spec_schema')
    def delete_spec(spec_sc):
        """軟刪除多面向規格"""
        from modules.spec_formulate.models import FwSpecSchema

        org = get_current_org()
        if not org:
            return jsonify({'success': False, 'error': _('無法取得企業資訊')}), 403

        spec = FwSpecSchema.query.filter_by(
            secure_code=spec_sc,
            org_secure_code=org.secure_code,
            is_deleted=False,
        ).first()

        if not spec:
            return jsonify({'success': False, 'error': _('規格不存在')}), 404

        spec.is_deleted = True
        spec.deleted_at = datetime.now(timezone.utc)
        spec.status = 'archived'
        db.session.commit()

        return jsonify({'success': True, 'message': _('已刪除規格「%(name)s」', name=spec.name)})

    # ── 版本歷史 ──

    @bp.route('/specs/<spec_sc>/history', methods=['GET'])
    @module_access_required('spec_formulate')
    @page_keys_required('spec_formulate.spec_schema')
    def get_history(spec_sc):
        """取得規格版本歷史"""
        from modules.spec_formulate.models import (
            FwSpecSchema,
            FwSpecSchemaHistory,
        )

        org = get_current_org()
        if not org:
            return jsonify({'success': False, 'error': _('無法取得企業資訊')}), 403

        spec = FwSpecSchema.query.filter_by(
            secure_code=spec_sc,
            org_secure_code=org.secure_code,
            is_deleted=False,
        ).first()

        if not spec:
            return jsonify({'success': False, 'error': _('規格不存在')}), 404

        histories = FwSpecSchemaHistory.query.filter_by(
            spec_secure_code=spec_sc,
            is_deleted=False,
        ).order_by(
            FwSpecSchemaHistory.version.desc()
        ).all()

        return jsonify({
            'success': True,
            'data': [h.to_dict() for h in histories],
        })

    # ── Facet 填充 ──

    @bp.route('/specs/<spec_sc>/populate-facet', methods=['POST'])
    @module_access_required('spec_formulate')
    @page_keys_required('spec_formulate.spec_schema')
    def populate_facet(spec_sc):
        """
        為規格的所有欄位填入指定格式的預設 facet 值

        Body: { "facet_name": "postgresql" }
        """
        from modules.spec_formulate.models import FwSpecSchema
        from modules.spec_formulate.services.schema.data_class_registry import (
            populate_facet_defaults,
            is_facet_supported,
            get_unsupported_reason,
            ALL_FACETS,
        )

        org = get_current_org()
        if not org:
            return jsonify({'success': False, 'error': _('無法取得企業資訊')}), 403

        spec = FwSpecSchema.query.filter_by(
            secure_code=spec_sc,
            org_secure_code=org.secure_code,
            is_deleted=False,
        ).first()

        if not spec:
            return jsonify({'success': False, 'error': _('規格不存在')}), 404

        data = request.get_json(silent=True) or {}
        facet_name = data.get('facet_name', '').strip()
        if facet_name not in ALL_FACETS:
            return jsonify({
                'success': False,
                'error': _('未知的格式: %(facet)s（可用: %(available)s）',
                           facet=facet_name, available=', '.join(ALL_FACETS)),
            }), 400

        fields = list(spec.fields or [])
        skipped = []
        populated = []

        for f in fields:
            dc = f.get('core', {}).get('data_class', 'text')
            fk = f.get('field_key', '?')

            if not is_facet_supported(dc, facet_name):
                reason = get_unsupported_reason(dc, facet_name)
                skipped.append({'field_key': fk, 'reason': reason})
                continue

            result = populate_facet_defaults(f, facet_name)
            if result:
                populated.append(fk)

        # 更新 spec
        spec.fields = fields
        spec.add_facet(facet_name)
        spec.updated_at = datetime.now(timezone.utc)
        db.session.commit()

        return jsonify({
            'success': True,
            'data': {
                'populated_count': len(populated),
                'populated_fields': populated,
                'skipped_count': len(skipped),
                'skipped_fields': skipped,
                'active_facets': spec.active_facets,
            },
            'message': _('已為 %(n)s 個欄位填入 %(facet)s 預設值',
                         n=len(populated), facet=facet_name),
        })
