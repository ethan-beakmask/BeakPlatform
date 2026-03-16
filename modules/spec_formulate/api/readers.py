"""
Spec Formulate Module - Format Readers API
格式讀取 API（Excel、CSV）

URL prefix: /api/spec-formulate/readers
"""
import logging

from flask import Blueprint, jsonify, request

from app.security.decorators import module_access_required

logger = logging.getLogger(__name__)

readers_bp = Blueprint(
    'spec_formulate_readers',
    __name__,
    url_prefix='/api/spec-formulate/readers'
)


@readers_bp.route('/excel', methods=['POST'])
@module_access_required('spec_formulate')
def read_excel():
    """讀取 Excel 檔案為 SPEC fields"""
    from modules.spec_formulate.services.field_spec.format_readers import (
        read_excel_to_spec_fields
    )

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '未提供檔案'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'success': False, 'error': '未選擇檔案'}), 400

    if not file.filename.lower().endswith(('.xlsx', '.xls')):
        return jsonify({'success': False, 'error': '僅支援 .xlsx 格式'}), 400

    try:
        fields = read_excel_to_spec_fields(file)
        return jsonify({
            'success': True,
            'data': {'fields': fields, 'field_count': len(fields)},
            'message': f'已讀取 {len(fields)} 個欄位',
        })
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.error(f'Excel 讀取失敗: {e}', exc_info=True)
        return jsonify({'success': False, 'error': f'讀取失敗: {str(e)}'}), 500


@readers_bp.route('/csv', methods=['POST'])
@module_access_required('spec_formulate')
def read_csv():
    """讀取 CSV 檔案為 SPEC fields"""
    from modules.spec_formulate.services.field_spec.format_readers import (
        read_csv_to_spec_fields
    )

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '未提供檔案'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'success': False, 'error': '未選擇檔案'}), 400

    if not file.filename.lower().endswith('.csv'):
        return jsonify({'success': False, 'error': '僅支援 .csv 格式'}), 400

    try:
        fields = read_csv_to_spec_fields(file)
        return jsonify({
            'success': True,
            'data': {'fields': fields, 'field_count': len(fields)},
            'message': f'已讀取 {len(fields)} 個欄位',
        })
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.error(f'CSV 讀取失敗: {e}', exc_info=True)
        return jsonify({'success': False, 'error': f'讀取失敗: {str(e)}'}), 500
