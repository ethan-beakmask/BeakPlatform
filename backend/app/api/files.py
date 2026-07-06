"""
BeakPlatform Files API
統一檔案上傳/下載/管理 API

所有檔案存取都經過此 blueprint，不再直接暴露 /static/uploads/ 路徑。
下載採一次性 token 機制：前端 POST 取 token（權限檢查 + 稽核），
再導向 /api/files/dl/<token> 取得檔案。token 60 秒過期、用後即銷。
"""
import json
import logging
import os
import secrets
from urllib.parse import quote

import redis
from flask import Blueprint, jsonify, request, Response, g
from flask_login import current_user

from ..security.decorators import login_required, public_route
from .. import db, csrf
from ..services import file_service
from ..services.file_service import FileTamperError
from ..models.file_access_log import FileAccessLog

logger = logging.getLogger(__name__)

files_bp = Blueprint('files', __name__, url_prefix='/api/files')

# ── Download token Redis ─────────────────────────────────────
_DOWNLOAD_TOKEN_TTL = 60  # 秒
_DOWNLOAD_TOKEN_PREFIX = 'file_dl:'

_redis_pool = None


def _get_dl_redis():
    """取得下載 token 專用的 Redis 連線"""
    global _redis_pool
    if _redis_pool is None:
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/1')
        _redis_pool = redis.ConnectionPool.from_url(redis_url)
    return redis.Redis(connection_pool=_redis_pool)


# ── Helpers ──────────────────────────────────────────────────

def _log_file_access(record, action, user_sc=None, username=None,
                     ip_addr=None, org_sc=None):
    """寫入檔案存取稽核記錄（best-effort，不影響主流程）"""
    try:
        log = FileAccessLog(
            org_secure_code=org_sc or current_user.organization.secure_code,
            file_secure_code=record.secure_code,
            original_name=record.original_name,
            context_type=record.context_type,
            context_id=record.context_id,
            action=action,
            user_secure_code=user_sc or current_user.secure_code,
            username=username or current_user.display_name or current_user.username,
            ip_address=ip_addr or request.remote_addr,
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        logger.warning("寫入檔案稽核記錄失敗: %s", e)
        try:
            db.session.rollback()
        except Exception:
            pass


def _make_cd_header(original_name):
    """產生 Content-Disposition header（RFC 5987 非 ASCII 編碼）"""
    try:
        original_name.encode('ascii')
        return f'attachment; filename="{original_name}"'
    except UnicodeEncodeError:
        ascii_fallback = original_name.encode('ascii', 'ignore').decode() or 'download'
        return (
            f"attachment; filename=\"{ascii_fallback}\"; "
            f"filename*=UTF-8''{quote(original_name)}"
        )


def _get_disk_size(record):
    """取得磁碟檔案大小（log 用，best-effort）"""
    try:
        if record.storage_type == 'encrypted':
            path = file_service._resolve_encrypted_path(record.storage_ref)
        else:
            path = file_service._resolve_local_path(record.storage_ref)
        return os.path.getsize(path) if os.path.exists(path) else 'MISSING'
    except Exception:
        return '?'


def _warn_page(status_code):
    """產生檔案下載違規警告 HTML 頁面"""
    html = """<!DOCTYPE html>
<html lang="zh-TW">
<head><meta charset="UTF-8"><title>""" + str(status_code) + """</title>
<style>
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
       max-width: 600px; margin: 80px auto; padding: 20px; }
</style></head>
<body>
<h1 style="color: #dc2626; font-size: 28px;">警告</h1>
<p>違規下載！檔案下載連結只限一次性且限時下載</p>
</body></html>"""
    return html, status_code, {'Content-Type': 'text/html; charset=utf-8'}


# ── Upload ───────────────────────────────────────────────────

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


# ── Serve (public) ───────────────────────────────────────────

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


# ── Download: token 申請 ─────────────────────────────────────

@files_bp.route('/<secure_code>/download-token', methods=['POST'])
@csrf.exempt
@login_required
def request_download_token(secure_code):
    """
    申請一次性下載 token。

    權限檢查 + 稽核記錄在此完成。
    回傳暫時 URL，60 秒過期、用後即銷。
    """
    org = current_user.organization
    if not org:
        return jsonify({'success': False, 'message': '找不到企業'}), 404

    record = file_service.get_file_by_sc(secure_code, org_sc=org.secure_code)
    if not record:
        return jsonify({'success': False, 'message': '檔案不存在'}), 404

    # 物件級授權：這個用戶跟這個檔案有沒有關係
    if not file_service.can_access_file(current_user, record):
        logger.warning(
            "[SEC] 下載 token 申請被拒（無檔案存取權）: file_sc=%s "
            "context_type=%s user=%s ip=%s",
            secure_code, record.context_type,
            current_user.username, request.remote_addr,
        )
        _log_file_access(record, 'denied')
        return jsonify({'success': False, 'message': '無此檔案的存取權限'}), 403

    # 前置檢查：檔案存在 + 大小合理（微秒級，不讀檔）
    preflight = file_service.preflight_check(record)
    if preflight:
        logger.critical(
            "[SEC] 下載前置檢查失敗: file_sc=%s org=%s reason=%s "
            "user=%s ip=%s",
            secure_code, org.secure_code, preflight,
            current_user.username, request.remote_addr,
        )
        return jsonify({
            'success': False,
            'message': '檔案異常！疑似竄改',
        }), 403

    # 產生 token 並���入 Redis
    token = secrets.token_urlsafe(32)
    payload = json.dumps({
        'file_sc': record.secure_code,
        'org_sc': org.secure_code,
        'user_sc': current_user.secure_code,
        'username': current_user.display_name or current_user.username,
        'ip': request.remote_addr,
    })

    try:
        r = _get_dl_redis()
        r.setex(f'{_DOWNLOAD_TOKEN_PREFIX}{token}', _DOWNLOAD_TOKEN_TTL, payload)
    except Exception as e:
        logger.exception("Redis 寫入下載 token 失敗")
        return jsonify({'success': False, 'message': '系統暫時無法處理下載'}), 503

    # 稽核記錄在 token 申請時寫入（有完整身份資訊）
    _log_file_access(record, 'download')

    return jsonify({
        'success': True,
        'url': f'{request.script_root}/api/files/dl/{token}',
    })


# ── Download: token 兌換 ─────────────────────────────────────

@files_bp.route('/dl/<token>', methods=['GET'])
@public_route
def token_download(token):
    """
    憑一次性 token 下載檔案。

    Token 由 download-token endpoint 產生，60 秒過期。
    GET+DEL 原子操作確保只能使用一次。
    不需 session 認證（token 本身即授權憑證）。
    """
    # 原子性取出並刪除 token（Lua script 確保一次性）
    lua_get_del = """
    local val = redis.call('GET', KEYS[1])
    if val then
        redis.call('DEL', KEYS[1])
    end
    return val
    """
    try:
        r = _get_dl_redis()
        raw = r.eval(lua_get_del, 1, f'{_DOWNLOAD_TOKEN_PREFIX}{token}')
    except Exception as e:
        logger.exception("Redis 讀取下載 token 失敗")
        return jsonify({'success': False, 'message': '系統暫時無法處理下載'}), 503

    if not raw:
        return _warn_page(410)

    payload = json.loads(raw)
    file_sc = payload['file_sc']
    org_sc = payload['org_sc']

    record = file_service.get_file_by_sc(file_sc, org_sc=org_sc)
    if not record:
        return jsonify({'success': False, 'message': '檔案不存在'}), 404

    try:
        data, mime_type, original_name = file_service.serve_file(record)
    except FileNotFoundError:
        logger.warning(
            "[SEC] 加密檔案遺失: file_sc=%s org=%s ref=%s user=%s ip=%s",
            file_sc, org_sc, record.storage_ref,
            payload.get('username', '?'), payload.get('ip', '?'),
        )
        return jsonify({'success': False, 'message': '檔案不存在'}), 404
    except FileTamperError as e:
        logger.critical(
            "[SEC] 檔案大小異常！疑似竄改: file_sc=%s org=%s ref=%s "
            "db_size=%s disk_size=%s user=%s ip=%s",
            file_sc, org_sc, record.storage_ref, record.file_size,
            _get_disk_size(record), payload.get('username', '?'),
            payload.get('ip', '?'),
        )
        return jsonify({'success': False, 'message': '檔案完整性驗證失敗，已通報管理員'}), 500
    except Exception as e:
        logger.error(
            "[SEC] 檔案解密失敗（可能被竄改）: file_sc=%s org=%s ref=%s "
            "db_size=%s user=%s ip=%s error=%s",
            file_sc, org_sc, record.storage_ref, record.file_size,
            payload.get('username', '?'), payload.get('ip', '?'), e,
        )
        return jsonify({'success': False, 'message': '下載失敗，檔案異常'}), 500

    # 完整性驗證：比對 SHA-256
    if not file_service.verify_file_integrity(record, data):
        logger.critical(
            "[SEC] 檔案完整性驗證失敗！疑似竄改: file_sc=%s org=%s "
            "original_name=%s db_hash=%s user=%s ip=%s",
            file_sc, org_sc, original_name, record.file_hash,
            payload.get('username', '?'), payload.get('ip', '?'),
        )
        return jsonify({'success': False, 'message': '檔案完整性驗證失敗，已通報管理員'}), 500

    return Response(
        data,
        mimetype=mime_type or 'application/octet-stream',
        headers={
            'Content-Disposition': _make_cd_header(original_name),
            'X-Content-Type-Options': 'nosniff',
            'Cache-Control': 'no-store',
        }
    )


# ── 舊 download endpoint: 封鎖直接存取 ──────────────────────

@files_bp.route('/<secure_code>/download', methods=['GET'])
@login_required
def download_blocked(secure_code):
    """舊的直接下載路徑已停用，必須透過 download-token 取得一次性連結。"""
    logger.warning(
        "[SEC] 直接下載嘗試被阻擋: file_sc=%s user=%s ip=%s",
        secure_code,
        current_user.username if current_user else 'unknown',
        request.remote_addr,
    )
    return _warn_page(403)


# ── Metadata ─────────────────────────────────────────────────

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

    # 物件級授權（同 download-token）
    if not file_service.can_access_file(current_user, record):
        logger.warning(
            "[SEC] metadata 讀取被拒（無檔案存取權）: file_sc=%s "
            "context_type=%s user=%s ip=%s",
            secure_code, record.context_type,
            current_user.username, request.remote_addr,
        )
        _log_file_access(record, 'denied')
        return jsonify({'success': False, 'message': '無此檔案的存取權限'}), 403

    return jsonify({
        'success': True,
        'data': record.to_dict()
    })


# ── Delete ───────────────────────────────────────────────────

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


# ── Revert single delete ──────────────────────────────────────

@files_bp.route('/<secure_code>/revert-delete', methods=['POST'])
@csrf.exempt
@login_required
def revert_single_delete(secure_code):
    """
    撤銷單一檔案的待刪除標記，回復為 active。
    只有上傳者本人可以撤銷。
    """
    org = current_user.organization
    if not org:
        return jsonify({'success': False, 'message': '找不到企業'}), 404

    record = file_service.get_file_by_sc(secure_code, org_sc=org.secure_code)
    if not record:
        return jsonify({'success': False, 'message': '檔案不存在'}), 404

    if record.uploader_sc and record.uploader_sc != current_user.secure_code:
        return jsonify({'success': False, 'message': '只能撤銷自己標記刪除的檔案'}), 403

    try:
        file_service.revert_single_pending_delete(record)
        db.session.commit()
        return jsonify({'success': True, 'message': '已撤銷刪除'})
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        logger.exception("撤銷刪除失敗: %s", secure_code)
        return jsonify({'success': False, 'message': f'撤銷失敗: {str(e)}'}), 500


# ── Revert deletes ───────────────────────────────────────────

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


# ── List ─────────────────────────────────────────────────────

@files_bp.route('/list', methods=['GET'])
@login_required
def list_files():
    """
    列出檔案

    Query params:
        context_type: 用途類型 (選填)
        context_id: 關聯記錄 SC (選填)

    授權規則：
        - 無 context_id：只回自己上傳的檔案
        - 有 context_id：逐筆過 can_access_file，只回有權限的
    """
    org = current_user.organization
    if not org:
        return jsonify({'success': False, 'message': '找不到企業'}), 404

    context_type = request.args.get('context_type')
    context_id = request.args.get('context_id')

    if context_id:
        records = file_service.list_files(
            org_sc=org.secure_code,
            context_type=context_type,
            context_id=context_id,
        )
        records = [r for r in records
                   if file_service.can_access_file(current_user, r)]
    else:
        # 無 context 時不開放列全企業檔案，只回自己上傳的
        records = file_service.list_files(
            org_sc=org.secure_code,
            context_type=context_type,
            uploader_sc=current_user.secure_code,
        )

    return jsonify({
        'success': True,
        'data': [r.to_dict() for r in records]
    })
