"""
Schema API - Export
DOCX / PDF 匯出
"""
import logging
import tempfile

from flask import jsonify, request, send_file
from flask_babel import gettext as _

from app.security.decorators import module_access_required
from app.platform.data import get_current_org

logger = logging.getLogger(__name__)


def register(bp):
    """將路由掛載到 Blueprint"""

    # ── DOCX 匯出 ──

    @bp.route('/export/docx', methods=['POST'])
    @module_access_required('spec_formulate')
    def export_docx():
        """
        匯出多面向規格書為 Word 文件。

        POST body:
        {
            "doc_title": "資料結構規格書",   // 選填
            "specs": [
                {
                    "spec_sc": "xxx",
                    "version": 3,           // 選填，預設最新版
                    "facets": ["postgresql", "excel"]
                }
            ]
        }
        """
        from modules.spec_formulate.models import (
            FwSpecSchema,
            FwSpecSchemaHistory,
        )
        from modules.spec_formulate.services.schema.docx_writer import (
            generate_spec_docx,
        )

        org = get_current_org()
        if not org:
            return jsonify({'success': False, 'error': _('無法取得企業資訊')}), 403

        data = request.get_json(silent=True) or {}
        spec_refs = data.get('specs', [])
        if not spec_refs:
            return jsonify({'success': False, 'error': _('請至少選擇一個規格')}), 400

        doc_title = (data.get('doc_title') or '').strip() or '資料結構規格書'

        entries = []
        for ref in spec_refs:
            spec_sc = ref.get('spec_sc')
            if not spec_sc:
                return jsonify({'success': False, 'error': _('每個項目需有 spec_sc')}), 400

            req_version = ref.get('version')  # None = 最新版
            facets = ref.get('facets', [])
            if not facets:
                return jsonify({
                    'success': False,
                    'error': _('規格 %(sc)s 未指定匯出格式', sc=spec_sc),
                }), 400

            # 查詢 spec
            spec = FwSpecSchema.query.filter_by(
                secure_code=spec_sc,
                org_secure_code=org.secure_code,
                is_deleted=False,
            ).first()

            if not spec:
                return jsonify({'success': False, 'error': _('規格不存在: %(sc)s', sc=spec_sc)}), 404

            # 取得指定版本的 fields
            if req_version and req_version != spec.version:
                # 從歷史記錄取
                history = FwSpecSchemaHistory.query.filter_by(
                    spec_secure_code=spec_sc,
                    version=req_version,
                    is_deleted=False,
                ).first()

                if not history:
                    return jsonify({
                        'success': False,
                        'error': _('找不到 %(name)s 的版本 v%(version)s',
                                   name=spec.name, version=req_version),
                    }), 404

                fields = history.fields_snapshot or []
                active_facets = history.active_facets_snapshot or []
                version = history.version
            else:
                fields = spec.fields or []
                active_facets = spec.active_facets or []
                version = spec.version

            # 驗證所選 facet 是否在 active_facets 中
            invalid_facets = [f for f in facets if f not in active_facets]
            if invalid_facets:
                return jsonify({
                    'success': False,
                    'error': _('%(name)s v%(version)s 未啟用格式: %(facets)s',
                               name=spec.name, version=version,
                               facets=', '.join(invalid_facets)),
                }), 400

            entries.append({
                'name': spec.name,
                'description': spec.description or '',
                'version': version,
                'fields': fields,
                'active_facets': active_facets,
                'facets': facets,
            })

        # 產生 DOCX
        try:
            tmp = tempfile.NamedTemporaryFile(suffix='.docx', delete=False)
            tmp.close()

            generate_spec_docx(entries, tmp.name, doc_title=doc_title)

            # 檔名
            if len(entries) == 1:
                filename = f"{entries[0]['name']}_spec.docx"
            else:
                names = '_'.join(e['name'] for e in entries[:3])
                filename = f"{names}_spec.docx"

            return send_file(
                tmp.name,
                mimetype=(
                    'application/vnd.openxmlformats-officedocument'
                    '.wordprocessingml.document'
                ),
                as_attachment=True,
                download_name=filename,
            )
        except Exception as e:
            logger.exception('DOCX 匯出失敗')
            return jsonify({'success': False, 'error': _('匯出失敗: %(error)s', error=str(e))}), 500

    @bp.route('/export/pdf', methods=['POST'])
    @module_access_required('spec_formulate')
    def export_pdf():
        """
        匯出多面向規格書為 PDF 文件。

        POST body 格式同 /export/docx:
        {
            "doc_title": "資料結構規格書",
            "specs": [
                {
                    "spec_sc": "xxx",
                    "version": 3,
                    "facets": ["postgresql", "excel"]
                }
            ]
        }
        """
        from modules.spec_formulate.models import (
            FwSpecSchema,
            FwSpecSchemaHistory,
        )
        from modules.spec_formulate.services.schema.pdf_writer import (
            generate_spec_pdf,
        )

        org = get_current_org()
        if not org:
            return jsonify({'success': False, 'error': _('無法取得企業資訊')}), 403

        data = request.get_json(silent=True) or {}
        spec_refs = data.get('specs', [])
        if not spec_refs:
            return jsonify({'success': False, 'error': _('請至少選擇一個規格')}), 400

        doc_title = (data.get('doc_title') or '').strip() or '資料結構規格書'

        entries = []
        for ref in spec_refs:
            spec_sc = ref.get('spec_sc')
            if not spec_sc:
                return jsonify({'success': False, 'error': _('每個項目需有 spec_sc')}), 400

            req_version = ref.get('version')
            facets = ref.get('facets', [])
            if not facets:
                return jsonify({
                    'success': False,
                    'error': _('規格 %(sc)s 未指定匯出格式', sc=spec_sc),
                }), 400

            spec = FwSpecSchema.query.filter_by(
                secure_code=spec_sc,
                org_secure_code=org.secure_code,
                is_deleted=False,
            ).first()

            if not spec:
                return jsonify({'success': False, 'error': _('規格不存在: %(sc)s', sc=spec_sc)}), 404

            if req_version and req_version != spec.version:
                history = FwSpecSchemaHistory.query.filter_by(
                    spec_secure_code=spec_sc,
                    version=req_version,
                    is_deleted=False,
                ).first()

                if not history:
                    return jsonify({
                        'success': False,
                        'error': _('找不到 %(name)s 的版本 v%(version)s',
                                   name=spec.name, version=req_version),
                    }), 404

                fields = history.fields_snapshot or []
                active_facets = history.active_facets_snapshot or []
                version = history.version
            else:
                fields = spec.fields or []
                active_facets = spec.active_facets or []
                version = spec.version

            invalid_facets = [f for f in facets if f not in active_facets]
            if invalid_facets:
                return jsonify({
                    'success': False,
                    'error': _('%(name)s v%(version)s 未啟用格式: %(facets)s',
                               name=spec.name, version=version,
                               facets=', '.join(invalid_facets)),
                }), 400

            entries.append({
                'name': spec.name,
                'description': spec.description or '',
                'version': version,
                'fields': fields,
                'active_facets': active_facets,
                'facets': facets,
            })

        try:
            tmp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
            tmp.close()

            generate_spec_pdf(entries, tmp.name, doc_title=doc_title)

            if len(entries) == 1:
                filename = f"{entries[0]['name']}_spec.pdf"
            else:
                names = '_'.join(e['name'] for e in entries[:3])
                filename = f"{names}_spec.pdf"

            return send_file(
                tmp.name,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=filename,
            )
        except Exception as e:
            logger.exception('PDF 匯出失敗')
            return jsonify({'success': False, 'error': _('匯出失敗: %(error)s', error=str(e))}), 500
