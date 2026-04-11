"""
Schema API - Form Link
版本清單、表單關聯/解連/同步/建立
"""
import logging
import secrets

from flask import jsonify, request

from app import db
from app.security.decorators import module_access_required
from app.platform.data import get_current_org

from ._mf_helpers import (
    _get_user_info,
    _sync_form_to_spec,
    _formio_schema_to_spec_fields,
)

logger = logging.getLogger(__name__)


def register(bp):
    """將路由掛載到 Blueprint"""

    @bp.route('/specs/<spec_sc>/versions', methods=['GET'])
    @module_access_required('spec_formulate')
    def list_versions(spec_sc):
        """取得規格的所有版本號清單（供匯出選擇版本用）"""
        from modules.spec_formulate.models import (
            FwSpecSchema,
            FwSpecSchemaHistory,
        )

        org = get_current_org()
        if not org:
            return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

        spec = FwSpecSchema.query.filter_by(
            secure_code=spec_sc,
            org_secure_code=org.secure_code,
            is_deleted=False,
        ).first()

        if not spec:
            return jsonify({'success': False, 'error': '規格不存在'}), 404

        # 歷史版本
        histories = FwSpecSchemaHistory.query.filter_by(
            spec_secure_code=spec_sc,
            is_deleted=False,
        ).order_by(
            FwSpecSchemaHistory.version.desc()
        ).all()

        versions = []
        # 當前版本（最新）
        versions.append({
            'version': spec.version,
            'is_current': True,
            'active_facets': spec.active_facets or [],
            'field_count': len(spec.fields or []),
        })
        # 歷史版本
        for h in histories:
            versions.append({
                'version': h.version,
                'is_current': False,
                'active_facets': h.active_facets_snapshot or [],
                'field_count': len(h.fields_snapshot or []),
            })

        return jsonify({'success': True, 'data': versions})

    # ── 表單關聯 / 建立 ──

    @bp.route('/by-form-template/<ft_sc>', methods=['GET', 'POST'])
    @module_access_required('spec_formulate')
    def get_or_create_spec_by_form_template(ft_sc):
        """
        依表單模板查找或自動建立關聯的 spec

        GET  -- 查找，找不到回 404
        POST -- 查找，找不到則自動建立空 spec 並關聯，回 201
        """
        from modules.spec_formulate.models import FwSpecSchema
        from modules.form_workflow.models import FwFormTemplate

        org = get_current_org()
        if not org:
            return jsonify({'success': False, 'error': 'no org'}), 403

        spec = FwSpecSchema.query.filter_by(
            org_secure_code=org.secure_code,
            linked_form_template_sc=ft_sc,
            is_deleted=False,
            status='active',
        ).first()

        if spec:
            if request.method == 'POST':
                try:
                    _sync_form_to_spec(spec, ft_sc, org.secure_code)
                except Exception as e:
                    logger.error('表單同步到 spec 失敗: %s', e, exc_info=True)
                    # 同步失敗不阻斷跳轉，仍讓使用者進入 spec 編輯器

            return jsonify({
                'success': True,
                'data': {'secure_code': spec.secure_code, 'name': spec.name},
            })

        # 找不到
        if request.method == 'GET':
            return jsonify({'success': False, 'error': '此表單尚未關聯規格'}), 404

        # POST: 自動建立 spec 並關聯，從 FormIO schema 匯入欄位
        template = FwFormTemplate.query.filter_by(
            secure_code=ft_sc,
            org_secure_code=org.secure_code,
        ).first()
        if not template:
            return jsonify({'success': False, 'error': '表單模板不存在'}), 404

        user_sc, user_name = _get_user_info()

        # 從 FormIO schema 反向轉為 spec fields
        fields = _formio_schema_to_spec_fields(template.schema)
        active_facets = ['formio'] if fields else []

        spec = FwSpecSchema(
            org_secure_code=org.secure_code,
            name=template.name or ft_sc,
            table_name=None,
            description=f'由表單「{template.name}」自動建立',
            version=1,
            fields=fields,
            active_facets=active_facets,
            status='active',
            linked_form_template_sc=ft_sc,
            last_modified_by=user_sc,
            last_modified_by_name=user_name,
        )
        db.session.add(spec)
        db.session.commit()

        return jsonify({
            'success': True,
            'data': {'secure_code': spec.secure_code, 'name': spec.name},
            'message': f'已自動建立規格「{spec.name}」',
        }), 201

    @bp.route('/available-templates', methods=['GET'])
    @module_access_required('spec_formulate')
    def available_templates():
        """列出可關聯的表單模板（未被任何 spec 佔用的）"""
        from modules.spec_formulate.models import FwSpecSchema
        from modules.form_workflow.models import FwFormTemplate

        org = get_current_org()
        if not org:
            return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

        # 已被佔用的 form_template secure_codes
        occupied = set()
        specs = FwSpecSchema.query.filter_by(
            org_secure_code=org.secure_code,
            is_deleted=False,
            status='active',
        ).all()
        for s in specs:
            if s.linked_form_template_sc:
                occupied.add(s.linked_form_template_sc)

        # 查可用的 form_template
        templates = FwFormTemplate.query.filter_by(
            org_secure_code=org.secure_code,
            is_active=True,
            is_deleted=False,
        ).order_by(FwFormTemplate.name).all()

        result = []
        for t in templates:
            if t.secure_code not in occupied:
                result.append({
                    'secure_code': t.secure_code,
                    'name': t.name,
                    'code': t.code,
                })

        return jsonify({'success': True, 'data': result})

    @bp.route('/specs/<spec_sc>/link-form', methods=['POST'])
    @module_access_required('spec_formulate')
    def link_form(spec_sc):
        """
        關聯現有表單模板到 spec

        Body: { "form_template_secure_code": "xxx" }
        """
        from modules.spec_formulate.models import FwSpecSchema
        from modules.form_workflow.models import FwFormTemplate

        org = get_current_org()
        if not org:
            return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

        spec = FwSpecSchema.query.filter_by(
            secure_code=spec_sc,
            org_secure_code=org.secure_code,
            is_deleted=False,
        ).first()
        if not spec:
            return jsonify({'success': False, 'error': '規格不存在'}), 404

        data = request.get_json(silent=True) or {}
        ft_sc = (data.get('form_template_secure_code') or '').strip()
        if not ft_sc:
            return jsonify({'success': False, 'error': '缺少 form_template_secure_code'}), 400

        template = FwFormTemplate.query.filter_by(
            secure_code=ft_sc,
            org_secure_code=org.secure_code,
            is_active=True,
            is_deleted=False,
        ).first()
        if not template:
            return jsonify({'success': False, 'error': '表單模板不存在'}), 404

        # 檢查是否已被其他 spec 佔用
        existing = FwSpecSchema.query.filter_by(
            org_secure_code=org.secure_code,
            linked_form_template_sc=ft_sc,
            is_deleted=False,
            status='active',
        ).first()
        if existing and existing.secure_code != spec_sc:
            return jsonify({
                'success': False,
                'error': f'此表單模板已被「{existing.name}」關聯',
            }), 409

        spec.linked_form_template_sc = ft_sc
        db.session.commit()

        return jsonify({
            'success': True,
            'data': {
                'linked_form_template_sc': ft_sc,
                'template_name': template.name,
                'template_code': template.code,
            },
            'message': f'已關聯表單模板「{template.name}」',
        })

    @bp.route('/specs/<spec_sc>/unlink-form', methods=['POST'])
    @module_access_required('spec_formulate')
    def unlink_form(spec_sc):
        """解除表單關聯"""
        from modules.spec_formulate.models import FwSpecSchema

        org = get_current_org()
        if not org:
            return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

        spec = FwSpecSchema.query.filter_by(
            secure_code=spec_sc,
            org_secure_code=org.secure_code,
            is_deleted=False,
        ).first()
        if not spec:
            return jsonify({'success': False, 'error': '規格不存在'}), 404

        spec.linked_form_template_sc = None
        db.session.commit()

        return jsonify({'success': True, 'message': '已解除表單關聯'})

    @bp.route('/specs/<spec_sc>/sync-to-form', methods=['POST'])
    @module_access_required('spec_formulate')
    def sync_to_form(spec_sc):
        """
        將 spec 的 formio facet 同步回關聯的表單模板

        以 spec fields 產生新的 FormIO schema，覆蓋表單模板的 schema。
        保留表單模板原有的非欄位設定（如 display、settings 等）。
        """
        from modules.spec_formulate.models import FwSpecSchema
        from modules.form_workflow.models import FwFormTemplate
        from modules.spec_formulate.services.schema.formio_generator import (
            spec_fields_to_formio_schema,
        )

        org = get_current_org()
        if not org:
            return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

        spec = FwSpecSchema.query.filter_by(
            secure_code=spec_sc,
            org_secure_code=org.secure_code,
            is_deleted=False,
        ).first()
        if not spec:
            return jsonify({'success': False, 'error': '規格不存在'}), 404

        if not spec.linked_form_template_sc:
            return jsonify({'success': False, 'error': '此規格尚未關聯表單'}), 400

        template = FwFormTemplate.query.filter_by(
            secure_code=spec.linked_form_template_sc,
            org_secure_code=org.secure_code,
        ).first()
        if not template:
            return jsonify({'success': False, 'error': '關聯的表單模板不存在'}), 404

        # 產生新的 FormIO schema（帶入表單名稱作為標題）
        new_schema = spec_fields_to_formio_schema(spec.fields or [], form_title=template.name)

        # 保留原 schema 的非 components 設定
        old_schema = template.schema or {}
        for k, v in old_schema.items():
            if k != 'components':
                new_schema[k] = v

        template.schema = new_schema
        db.session.commit()

        field_count = len(new_schema.get('components', []))
        return jsonify({
            'success': True,
            'message': f'已同步 {field_count} 個欄位回表單「{template.name}」',
            'data': {
                'template_name': template.name,
                'field_count': field_count,
            },
        })

    @bp.route('/specs/<spec_sc>/create-form', methods=['POST'])
    @module_access_required('spec_formulate')
    def create_form(spec_sc):
        """
        從 spec 建立新的 FormIO 表單模板

        Body: {
            "name": "表單名稱",
            "code": "FT_CODE",          // 選填，自動產生
            "category_secure_code": ""   // 選填
        }
        """
        from modules.spec_formulate.models import FwSpecSchema
        from modules.form_workflow.models import FwFormTemplate
        from modules.spec_formulate.services.schema.formio_generator import (
            spec_fields_to_formio_schema,
        )

        org = get_current_org()
        if not org:
            return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

        spec = FwSpecSchema.query.filter_by(
            secure_code=spec_sc,
            org_secure_code=org.secure_code,
            is_deleted=False,
        ).first()
        if not spec:
            return jsonify({'success': False, 'error': '規格不存在'}), 404

        data = request.get_json(silent=True) or {}
        form_name = (data.get('name') or '').strip() or spec.name
        form_code = (data.get('code') or '').strip()
        category_sc = (data.get('category_secure_code') or '').strip() or None

        # 自動產生 code
        if not form_code:
            form_code = f'FT{secrets.token_hex(4).upper()}'

        # 檢查 code 唯一性
        dup = FwFormTemplate.query.filter_by(
            org_secure_code=org.secure_code,
            code=form_code,
            is_deleted=False,
        ).first()
        if dup:
            return jsonify({
                'success': False,
                'error': f'表單代碼 {form_code} 已存在',
            }), 409

        # 確認有 formio facet
        if 'formio' not in (spec.active_facets or []):
            return jsonify({
                'success': False,
                'error': '此規格尚未啟用 FormIO 格式，請先填充 FormIO facet',
            }), 400

        # 產生 FormIO schema
        schema = spec_fields_to_formio_schema(
            spec.fields or [], form_title=form_name
        )

        # 建立 FwFormTemplate
        template = FwFormTemplate(
            org_secure_code=org.secure_code,
            name=form_name,
            code=form_code,
            schema=schema,
            category_secure_code=category_sc,
            is_active=True,
        )
        db.session.add(template)
        db.session.flush()

        # 關聯到 spec
        spec.linked_form_template_sc = template.secure_code
        db.session.commit()

        return jsonify({
            'success': True,
            'data': {
                'spec': spec.to_dict(),
                'form_template': {
                    'secure_code': template.secure_code,
                    'name': template.name,
                    'code': template.code,
                },
            },
            'message': f'已建立並關聯表單「{form_name}」({form_code})',
        })
