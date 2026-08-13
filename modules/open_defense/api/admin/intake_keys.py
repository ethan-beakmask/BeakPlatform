"""Admin API:intake keys(P2 起唯讀遺留)

OdIntakeKey 已由 migration 079 遷移至平台 ApiKey(scopes.od_intake),
金鑰的建立/暫停/撤銷改在 /security/api-keys/ 管理。
本表保留唯讀一個版本週期後刪除(規格: dev-notes/API_KEY_TRIGGER_SPEC.md P2)。
"""
from flask import jsonify
from flask_babel import gettext as _
from flask_login import current_user

from app.security.decorators import admin_required

from . import admin_bp
from ...models import OdIntakeKey

def _migrated_msg():
    return _('Intake key 已遷移至平台 API Key,請至 /security/api-keys/ 管理(scope: od_intake)')


@admin_bp.route('/intake-keys', methods=['GET'])
@admin_required
def list_intake_keys():
    """唯讀遺留清單(僅供比對遷移前資料)"""
    org_sc = current_user.org_secure_code
    rows = OdIntakeKey.query.filter_by(
        org_secure_code=org_sc, is_deleted=False,
    ).order_by(OdIntakeKey.created_at.desc()).all()
    return jsonify({
        'keys': [r.to_dict() for r in rows],
        'readonly': True,
        'migrated_message': _migrated_msg(),
    })


@admin_bp.route('/intake-keys', methods=['POST'])
@admin_required
def create_intake_key_api():
    return jsonify({'error': 'migrated', 'message': _migrated_msg()}), 410


@admin_bp.route('/intake-keys/<secure_code>', methods=['DELETE'])
@admin_required
def revoke_intake_key_api(secure_code):
    return jsonify({'error': 'migrated', 'message': _migrated_msg()}), 410
