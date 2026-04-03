"""
BeakPlatform Vault Admin API
BeakSeal 加密保險庫管理 API - 僅系統管理員可用

端點：
- GET  /api/vault/status                    取得 Vault 狀態
- GET  /api/vault/keys/<org_code>           取得金鑰世代列表
- POST /api/vault/keys/<org_code>/rotate    手動金鑰輪替
- GET  /api/vault/audit                     查詢稽核記錄
- GET  /api/vault/audit/verify              驗證 hash chain
"""
import logging

from flask import Blueprint, jsonify, request

from ..security.decorators import system_admin_required
from ..services.vault_service import VaultService
from ..utils.vault_client import VaultError

logger = logging.getLogger(__name__)

vault_admin_bp = Blueprint('vault_admin', __name__,
                           url_prefix='/api/vault')


@vault_admin_bp.route('/status', methods=['GET'])
@system_admin_required
def vault_status():
    """取得 BeakSeal Vault 狀態"""
    try:
        status = VaultService.get_status()
        return jsonify({'success': True, 'data': status})
    except VaultError as e:
        return jsonify({'success': False, 'error': str(e)}), 503
    except Exception as e:
        logger.error("取得 vault 狀態失敗: %s", e)
        return jsonify({'success': False, 'error': 'BeakSeal 服務無法連線'}), 503


@vault_admin_bp.route('/keys/<org_code>', methods=['GET'])
@system_admin_required
def key_generations(org_code):
    """取得組織金鑰世代列表"""
    try:
        gens = VaultService.get_key_generations(org_code)
        return jsonify({'success': True, 'data': gens})
    except VaultError as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@vault_admin_bp.route('/keys/<org_code>/rotate', methods=['POST'])
@system_admin_required
def rotate_key(org_code):
    """手動觸發金鑰輪替"""
    try:
        result = VaultService.rotate_key(org_code)
        return jsonify({'success': True, 'data': result})
    except VaultError as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@vault_admin_bp.route('/audit', methods=['GET'])
@system_admin_required
def audit_logs():
    """查詢 BeakSeal 稽核記錄"""
    try:
        kwargs = {}
        for key in ('org_id', 'user_id', 'action', 'file_id',
                     'from_date', 'to_date', 'limit', 'offset'):
            val = request.args.get(key)
            if val:
                kwargs[key] = val

        logs = VaultService.get_audit_logs(**kwargs)
        return jsonify({'success': True, 'data': logs})
    except VaultError as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@vault_admin_bp.route('/audit/verify', methods=['GET'])
@system_admin_required
def audit_verify():
    """驗證稽核記錄 hash chain 完整性"""
    try:
        from_id = request.args.get('from_id', 0, type=int)
        to_id = request.args.get('to_id', 0, type=int)
        result = VaultService.verify_audit_chain(from_id, to_id)
        return jsonify({'success': True, 'data': result})
    except VaultError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
