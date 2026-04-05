"""
BeakPlatform Files API
統一檔案上傳/下載/管理 API

所有檔案存取都經過此 blueprint，不再直接暴露 /static/uploads/ 路徑。
"""
import logging

from flask import Blueprint, jsonify, request, Response, g
from flask_login import current_user

from ..security.decorators import login_required, public_route
from .. import db, csrf
from ..services import file_service
from ..models.file_access_log import FileAccessLog

logger = logging.getLogger(__name__)

files_bp = Blueprint('files', __name__, url_prefix='/api/files')


def _log_file_access(record, action):
    """寫入檔案存取稽核記錄（best-effort，不影響主流程）"""
    try:
        org = current_user.organization
        log = FileAccessLog(
            org_secure_code=org.secure_code,
            file_secure_code=record.secure_code,
            original_name=record.original_name,
            context_type=record.context_type,
            context_id=record.context_id,
            action=action,
            user_secure_code=current_user.secure_code,
            username=current_user.display_name or current_user.username,
            ip_address=request.remote_addr,
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        logger.warning("寫入檔案稽核記錄失敗: %s", e)
        try:
            db.session.rollback()
        except Exception:
            pass


@files_bp.route('/upload', methods=['POST'])
@csrf.exempt
@login_required
def upload():
    """
    通用檔案上傳

    Form Data:
        file: 檔案
        context_type: 用途類型 (必填)
        context_id: 關聯記錄 SC (選填)
        node_id: 簽核關卡 ID (選填，表單附件用)
    """
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '未提供檔案'}), 400

    file = request.files['file']
    context_type = request.form.get('context_type', '').strip()
    context_id = request.form.get('context_id', '').strip() or None
    node_id = request.form.get('node_id', '').strip() or None

    if not context_type:
        return jsonify({'success': False, 'message': '未指定 context_type'}), 400

    org = current_user.organization
    if not org:
        return jsonify({'success': False, 'message': '找不到企業'}), 404

    try:
        record = file_service.upload_file(
            org_sc=org.secure_code,
            file=file,
            context_type=context_type,
            context_id=context_id,
            uploader_sc=current_user.secure_code,
            uploader_node_id=node_id,
        )
        db.session.commit()

        _log_file_access(record, 'upload')

        return jsonify({
            'success': True,
            'message': '上傳成功',
            'data': {
                'secure_code': record.secure_code,
                'serve_url': record.serve_url,
                'download_url': record.download_url,
                'original_name': record.original_name,
                'file_size': record.file_size,
                'mime_type': record.mime_type,
            }
        }), 201

    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        logger.exception("檔案上傳失敗")
        return jsonify({'success': False, 'message': f'上傳失敗: {str(e)}'}), 500


@files_bp.route('/<secure_code>/serve', methods=['GET'])
@public_route
def serve(secure_code):
    """
    Serve 公開資源（如 Logo、背景圖）。

    標記為 @public_route 讓登入頁面也能載入 Logo。
    透過 secure_code 存取，外部無法猜測。
    """
    record = file_service.get_file_by_sc(secure_code)
    if not record:
        return '', 404

    try:
        data, mime_type, _ = file_service.serve_file(record)
    except FileNotFoundError:
        return '', 404
    except Exception as e:
        logger.exception("serve 檔案失敗: %s", secure_code)
        return '', 500

    return Response(
        data,
        mimetype=mime_type or 'application/octet-stream',
        headers={
            'Cache-Control': 'public, max-age=86400',
            'X-Content-Type-Options': 'nosniff',
        }
    )


@files_bp.route('/<secure_code>/download', methods=['GET'])
@login_required
def download(secure_code):
    """
    下載機敏檔案（加密檔案自動解密）。

    需登入 + 租戶隔離。
    下載成功後立即寫入稽核記錄。
    """
    org = current_user.organization
    if not org:
        return jsonify({'success': False, 'message': '找不到企業'}), 404

    record = file_service.get_file_by_sc(secure_code, org_sc=org.secure_code)
    if not record:
        return jsonify({'success': False, 'message': '檔案不存在'}), 404

    try:
        data, mime_type, original_name = file_service.serve_file(record)
    except FileNotFoundError:
        return jsonify({'success': False, 'message': '檔案不存在'}), 404
    except Exception as e:
        logger.exception("下載檔案失敗: %s", secure_code)
        return jsonify({'success': False, 'message': '下載失敗'}), 500

    _log_file_access(record, 'download')

    return Response(
        data,
        mimetype=mime_type or 'application/octet-stream',
        headers={
            'Content-Disposition': f'attachment; filename="{original_name}"',
            'X-Content-Type-Options': 'nosniff',
        }
    )


@files_bp.route('/<secure_code>/meta', methods=['GET'])
@login_required
def meta(secure_code):
    """取得檔案 metadata"""
    org = current_user.organization
    if not org:
        return jsonify({'success': False, 'message': '找不到企業'}), 404

    record = file_service.get_file_by_sc(secure_code, org_sc=org.secure_code)
    if not record:
        return jsonify({'success': False, 'message': '檔案不存在'}), 404

    return jsonify({
        'success': True,
        'data': record.to_dict()
    })


@files_bp.route('/<secure_code>', methods=['DELETE'])
@csrf.exempt
@login_required
def delete(secure_code):
    """
    刪除檔案（偽刪除）。
    僅標記為 pending_delete，等簽核確認後才真正刪除。
    只有上傳者本人可以標記刪除。
    """
    org = current_user.organization
    if not org:
        return jsonify({'success': False, 'message': '找不到企業'}), 404

    record = file_service.get_file_by_sc(secure_code, org_sc=org.secure_code)
    if not record:
        return jsonify({'success': False, 'message': '檔案不存在'}), 404

    # 只有上傳者可以刪除
    if record.uploader_sc and record.uploader_sc != current_user.secure_code:
        return jsonify({'success': False, 'message': '只能刪除自己上傳的檔案'}), 403

    _log_file_access(record, 'delete')

    try:
        file_service.mark_pending_delete(record)
        db.session.commit()
        return jsonify({'success': True, 'message': '檔案已標記刪除'})
    except Exception as e:
        db.session.rollback()
        logger.exception("標記刪除失敗: %s", secure_code)
        return jsonify({'success': False, 'message': f'刪除失敗: {str(e)}'}), 500


@files_bp.route('/revert-deletes', methods=['POST'])
@csrf.exempt
@login_required
def revert_deletes():
    """
    回復偽刪除（關閉簽核 modal 時呼叫）。
    將當前用戶在指定 context 下的 pending_delete 回復為 active。
    """
    org = current_user.organization
    if not org:
        return jsonify({'success': False, 'message': '找不到企業'}), 404

    data = request.get_json() or {}
    context_id = data.get('context_id')
    if not context_id:
        return jsonify({'success': False, 'message': '未指定 context_id'}), 400

    try:
        file_service.revert_pending_deletes(org.secure_code, context_id)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        logger.exception("回復刪除失敗")
        return jsonify({'success': False, 'message': str(e)}), 500


@files_bp.route('/list', methods=['GET'])
@login_required
def list_files():
    """
    列出檔案

    Query params:
        context_type: 用途類型 (選填)
        context_id: 關聯記錄 SC (選填)
    """
    org = current_user.organization
    if not org:
        return jsonify({'success': False, 'message': '找不到企業'}), 404

    context_type = request.args.get('context_type')
    context_id = request.args.get('context_id')

    records = file_service.list_files(
        org_sc=org.secure_code,
        context_type=context_type,
        context_id=context_id,
    )

    return jsonify({
        'success': True,
        'data': [r.to_dict() for r in records]
    })
