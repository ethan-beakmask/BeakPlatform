"""
Spec Formulate Module - Export API
匯出 API（Excel、CSV、DOCX）

URL prefix: /api/spec-formulate/export
"""
import logging
import os
import tempfile

from flask import Blueprint, jsonify, request, send_file

from app import db
from app.security.decorators import module_access_required
from app.platform.auth import current_user
from app.platform.data import get_current_org

logger = logging.getLogger(__name__)

export_bp = Blueprint(
    'spec_formulate_export',
    __name__,
    url_prefix='/api/spec-formulate/export'
)


def _get_spec_fields(identifier):
    """
    取得 spec 的 fields 和名稱

    identifier 可以是:
    - standalone spec 的 secure_code
    - form_template 的 secure_code

    Returns:
        tuple: (fields, spec_name, error_msg)
    """
    from modules.spec_formulate.models.form_field_spec import FwFormFieldSpec

    org = get_current_org()
    if not org:
        return None, None, '無法取得企業資訊'

    # 先嘗試 standalone spec
    spec = FwFormFieldSpec.query.filter_by(
        secure_code=identifier,
        org_secure_code=org.secure_code,
        is_deleted=False,
    ).first()

    if spec:
        name = spec.name or spec.secure_code
        return spec.fields or [], name, None

    # 再嘗試 form_template_secure_code
    spec = FwFormFieldSpec.query.filter_by(
        form_template_secure_code=identifier,
        org_secure_code=org.secure_code,
        is_deleted=False,
    ).first()

    if spec:
        name = spec.name or identifier
        return spec.fields or [], name, None

    return None, None, '找不到指定的規格'


@export_bp.route('/<identifier>/excel', methods=['POST'])
@module_access_required('spec_formulate')
def export_excel(identifier):
    """匯出為 Excel"""
    from modules.spec_formulate.services.field_spec.export_writers import (
        export_excel as write_excel
    )

    fields, name, err = _get_spec_fields(identifier)
    if err:
        return jsonify({'success': False, 'error': err}), 404

    if not fields:
        return jsonify({'success': False, 'error': '規格無欄位資料'}), 400

    try:
        path = write_excel(fields, name)
        return send_file(
            path,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'{name}.xlsx',
        )
    except Exception as e:
        logger.error(f'Excel 匯出失敗: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@export_bp.route('/<identifier>/csv', methods=['POST'])
@module_access_required('spec_formulate')
def export_csv(identifier):
    """匯出為 CSV"""
    from modules.spec_formulate.services.field_spec.export_writers import (
        export_csv as write_csv
    )

    fields, name, err = _get_spec_fields(identifier)
    if err:
        return jsonify({'success': False, 'error': err}), 404

    if not fields:
        return jsonify({'success': False, 'error': '規格無欄位資料'}), 400

    try:
        path = write_csv(fields, name)
        return send_file(
            path,
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'{name}.csv',
        )
    except Exception as e:
        logger.error(f'CSV 匯出失敗: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@export_bp.route('/<identifier>/docx', methods=['POST'])
@module_access_required('spec_formulate')
def export_docx(identifier):
    """匯出為 Word 文件"""
    from modules.spec_formulate.services.field_spec.export_writers import (
        export_docx as write_docx
    )

    fields, name, err = _get_spec_fields(identifier)
    if err:
        return jsonify({'success': False, 'error': err}), 404

    if not fields:
        return jsonify({'success': False, 'error': '規格無欄位資料'}), 400

    data = request.get_json(silent=True) or {}
    preamble = data.get('preamble')
    postscript = data.get('postscript')

    try:
        path = write_docx(fields, name, preamble=preamble,
                          postscript=postscript)
        return send_file(
            path,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            as_attachment=True,
            download_name=f'{name}_spec.docx',
        )
    except Exception as e:
        logger.error(f'DOCX 匯出失敗: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500
