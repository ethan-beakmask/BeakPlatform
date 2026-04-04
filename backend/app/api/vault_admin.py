"""
BeakPlatform Vault Admin API
BeakSeal 加密保險庫管理 API - 僅系統管理員可用

端點：
- GET  /api/vault/status                    取得 Vault 狀態
- GET  /api/vault/config                    取得 BeakSeal 設定 (脫敏)
- POST /api/vault/service/<action>          服務控制 (start/stop/restart)
- POST /api/vault/unseal                    Unseal vault
- POST /api/vault/seal                      Seal vault
- GET  /api/vault/file-stats                檔案統計
- GET  /api/vault/keys/<org_code>           取得金鑰世代列表
- POST /api/vault/keys/<org_code>/rotate    手動金鑰輪替
- GET  /api/vault/audit                     查詢稽核記錄
- GET  /api/vault/audit/verify              驗證 hash chain
"""
import logging
import os
import subprocess

import yaml
from flask import Blueprint, jsonify, request

from ..security.decorators import system_admin_required
from .. import csrf, db
from ..services.vault_service import VaultService, get_client
from ..utils.vault_client import VaultError

logger = logging.getLogger(__name__)

vault_admin_bp = Blueprint('vault_admin', __name__,
                           url_prefix='/api/vault')

BEAKSEAL_CONFIG_PATH = os.getenv('BEAKSEAL_CONFIG',
                                  '/opt/BeakSeal/beakseal.yaml')
BEAKSEAL_SERVICE_NAME = 'beakseal'


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


# ──────────────────── Config ────────────────────

@vault_admin_bp.route('/config', methods=['GET'])
@system_admin_required
def vault_config():
    """取得 BeakSeal 設定檔 (脫敏，不顯示密碼)"""
    try:
        with open(BEAKSEAL_CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # 脫敏：移除可能的密碼欄位
        db_cfg = config.get('database', {})
        if 'password' in db_cfg:
            db_cfg['password'] = '***'

        return jsonify({
            'success': True,
            'data': {
                'config': config,
                'config_path': BEAKSEAL_CONFIG_PATH,
            }
        })
    except FileNotFoundError:
        return jsonify({'success': False, 'error': '設定檔不存在'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ──────────────────── Service Control ────────────────────

@vault_admin_bp.route('/service/<action>', methods=['POST'])
@csrf.exempt
@system_admin_required
def vault_service_control(action):
    """
    控制 BeakSeal systemd 服務

    action: start / stop / restart
    """
    if action not in ('start', 'stop', 'restart'):
        return jsonify({'success': False, 'error': '無效的操作'}), 400

    try:
        result = subprocess.run(
            ['sudo', 'systemctl', action, BEAKSEAL_SERVICE_NAME],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            logger.info("BeakSeal service %s by admin", action)
            return jsonify({'success': True, 'message': f'服務已{action}'})
        else:
            return jsonify({
                'success': False,
                'error': result.stderr.strip() or f'{action} 失敗'
            }), 500
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': '操作逾時'}), 504
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@vault_admin_bp.route('/service/status', methods=['GET'])
@system_admin_required
def vault_service_status():
    """取得 BeakSeal systemd 服務狀態"""
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', BEAKSEAL_SERVICE_NAME],
            capture_output=True, text=True, timeout=5
        )
        active = result.stdout.strip()

        result2 = subprocess.run(
            ['systemctl', 'show', BEAKSEAL_SERVICE_NAME,
             '--property=ActiveState,SubState,MainPID,MemoryCurrent,ExecMainStartTimestamp'],
            capture_output=True, text=True, timeout=5
        )
        props = {}
        for line in result2.stdout.strip().split('\n'):
            if '=' in line:
                k, v = line.split('=', 1)
                props[k] = v

        return jsonify({
            'success': True,
            'data': {
                'active': active,
                'state': props.get('ActiveState', ''),
                'sub_state': props.get('SubState', ''),
                'main_pid': props.get('MainPID', '0'),
                'memory': props.get('MemoryCurrent', '0'),
                'start_time': props.get('ExecMainStartTimestamp', ''),
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ──────────────────── Unseal / Seal ────────────────────

@vault_admin_bp.route('/unseal', methods=['POST'])
@csrf.exempt
@system_admin_required
def vault_unseal():
    """Unseal BeakSeal vault"""
    data = request.get_json() or {}
    password = data.get('password', '')
    if not password:
        return jsonify({'success': False, 'error': '密碼不可為空'}), 400

    try:
        result = get_client().unseal(password)
        logger.info("BeakSeal vault unsealed by admin")
        return jsonify({'success': True, 'data': result})
    except VaultError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': 'Unseal 失敗: ' + str(e)}), 500


@vault_admin_bp.route('/seal', methods=['POST'])
@csrf.exempt
@system_admin_required
def vault_seal():
    """Seal BeakSeal vault"""
    try:
        result = get_client().seal()
        logger.info("BeakSeal vault sealed by admin")
        return jsonify({'success': True, 'data': result})
    except VaultError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': 'Seal 失敗: ' + str(e)}), 500


# ──────────────────── File Stats ────────────────────

@vault_admin_bp.route('/file-stats', methods=['GET'])
@system_admin_required
def vault_file_stats():
    """取得 BeakSeal 加密檔案統計"""
    from ..models.platform_file import PlatformFile
    from sqlalchemy import func

    try:
        stats = db.session.query(
            PlatformFile.context_type,
            func.count(PlatformFile.id).label('count'),
            func.coalesce(func.sum(PlatformFile.file_size), 0).label('total_size'),
        ).filter(
            PlatformFile.storage_type == 'beakseal',
            PlatformFile.is_deleted == False,
        ).group_by(PlatformFile.context_type).all()

        data = []
        total_count = 0
        total_size = 0
        for ctx, cnt, sz in stats:
            data.append({
                'context_type': ctx,
                'count': cnt,
                'total_size': int(sz),
            })
            total_count += cnt
            total_size += int(sz)

        return jsonify({
            'success': True,
            'data': {
                'by_context': data,
                'total_count': total_count,
                'total_size': total_size,
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
