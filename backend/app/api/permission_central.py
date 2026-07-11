"""
BeakPlatform Permission Central API
權限中央管理 API

安全設計：
- 所有端點需 @admin_required (ORG_ADMIN 或 SYSTEM_ADMIN)
- 透過 current_user.user_type 判斷權限範圍
- ORG_ADMIN 只能看到/操作自己企業的資料
- SYSTEM_ADMIN 可透過 org_code 參數過濾指定企業
"""
import json
import logging

from flask import Blueprint, request, jsonify, Response
from flask_babel import gettext as _
from flask_login import current_user

from ..security.decorators import admin_required, system_admin_required
from ..services.permission_central_service import PermissionCentralService
from .. import csrf

logger = logging.getLogger(__name__)

permission_central_bp = Blueprint(
    'api_permission_central', __name__,
    url_prefix='/api/permissions'
)


def _is_sys_admin() -> bool:
    """判斷當前用戶是否為系統管理員"""
    return str(current_user.user_type) == 'SYSTEM_ADMIN'


def _resolve_org_code() -> str:
    """
    解析要查詢的企業 org_secure_code

    SYSTEM_ADMIN: 使用 query param org_code，未指定時回傳空字串
    ORG_ADMIN: 強制使用自己的企業，忽略 org_code 參數
    """
    if _is_sys_admin():
        return request.args.get('org_code', '')
    return current_user.org_secure_code


@permission_central_bp.route('/roles', methods=['GET'])
@admin_required
def list_roles():
    """取得角色列表（依權限過濾）"""
    org_code = _resolve_org_code()
    if _is_sys_admin() and not org_code:
        return jsonify({'roles': []}), 200

    roles = PermissionCentralService.get_all_roles(
        org_secure_code=org_code,
        is_system_admin=_is_sys_admin(),
        filter_org_code=org_code if _is_sys_admin() else ''
    )
    return jsonify({'roles': roles}), 200


@permission_central_bp.route('/permissions', methods=['GET'])
@admin_required
def list_permissions():
    """取得權限定義（ORG_ADMIN 看不到 SYSTEM 級）"""
    perms = PermissionCentralService.get_all_permissions(
        is_system_admin=_is_sys_admin()
    )
    return jsonify({'permissions': perms}), 200


@permission_central_bp.route('/menus', methods=['GET'])
@admin_required
def list_menus():
    """取得選單列表（ORG_ADMIN 只看企業相關選單）"""
    org_code = _resolve_org_code()
    menus = PermissionCentralService.get_menu_tree_flat(
        org_secure_code=org_code,
        is_system_admin=_is_sys_admin()
    )
    return jsonify({'menus': menus}), 200


@permission_central_bp.route('/role-view/<role_secure_code>', methods=['GET'])
@admin_required
def role_view(role_secure_code: str):
    """角色視角：取得角色在各層的完整授權"""
    org_code = _resolve_org_code()
    result = PermissionCentralService.get_role_view(
        role_secure_code=role_secure_code,
        org_secure_code=org_code,
        is_system_admin=_is_sys_admin()
    )

    if 'error' in result:
        return jsonify({'error': result['error']}), 404

    return jsonify(result), 200


@permission_central_bp.route('/menu-view/<menu_secure_code>', methods=['GET'])
@admin_required
def menu_view(menu_secure_code: str):
    """功能視角：取得選單在各層的完整權限資訊"""
    org_code = _resolve_org_code()
    result = PermissionCentralService.get_menu_view(
        menu_secure_code=menu_secure_code,
        org_secure_code=org_code,
        is_system_admin=_is_sys_admin()
    )

    if 'error' in result:
        return jsonify({'error': result['error']}), 404

    return jsonify(result), 200


@permission_central_bp.route('/conflicts', methods=['GET'])
@admin_required
def conflicts():
    """衝突偵測：偵測權限配置中的不一致"""
    org_code = _resolve_org_code()
    if _is_sys_admin() and not org_code:
        return jsonify({
            'conflicts': [],
            'summary': {'total': 0, 'errors': 0, 'warnings': 0}
        }), 200

    result = PermissionCentralService.detect_conflicts(
        org_secure_code=org_code,
        is_system_admin=_is_sys_admin()
    )
    return jsonify(result), 200


@permission_central_bp.route('/role-permissions', methods=['PUT'])
@csrf.exempt
@admin_required
def update_role_permissions():
    """批量設定角色的 RBAC 權限（含存取控制）"""
    data = request.get_json()
    if not data:
        return jsonify({'error': _('缺少請求資料')}), 400

    role_secure_code = data.get('role_secure_code')
    permission_secure_codes = data.get('permission_secure_codes', [])

    if not role_secure_code:
        return jsonify({'error': _('缺少 role_secure_code')}), 400

    if not isinstance(permission_secure_codes, list):
        return jsonify({'error': _('permission_secure_codes 必須是陣列')}), 400

    org_code = _resolve_org_code()
    result = PermissionCentralService.set_role_permissions(
        role_secure_code=role_secure_code,
        permission_secure_codes=permission_secure_codes,
        org_secure_code=org_code,
        is_system_admin=_is_sys_admin(),
        operator_user=current_user
    )

    if 'error' in result:
        return jsonify({'error': result['error']}), 400

    return jsonify(result), 200


# =============================================================================
# RBAC 出廠預設值管理
# =============================================================================

@permission_central_bp.route('/save-factory-defaults', methods=['POST'])
@csrf.exempt
@system_admin_required
def save_factory_defaults():
    """
    設定目前組態成出廠值（系統管理員專用）。

    將指定企業的系統角色 RBAC 權限快照存為 rbac_defaults 表。
    """
    org_code = _resolve_org_code()
    if not org_code:
        return jsonify({'error': _('請先選擇企業')}), 400

    result = PermissionCentralService.save_factory_defaults(
        org_secure_code=org_code,
        operator_username=current_user.username
    )

    if 'error' in result:
        return jsonify({'error': result['error']}), 400

    return jsonify(result), 200


@permission_central_bp.route('/export-factory-sql', methods=['POST'])
@csrf.exempt
@system_admin_required
def export_factory_sql():
    """
    從 rbac_defaults 表匯出安裝用 SQL（原廠專用）。

    生成 060_seed_rbac_defaults.sql，供全新安裝時灌入預設值。
    upgrade 不會覆蓋用戶已儲存的預設值。
    """
    try:
        result = PermissionCentralService.export_factory_sql()
        if 'error' in result:
            return jsonify({'error': result['error']}), 400
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': _('匯出 SQL 失敗: %(error)s', error=str(e))}), 500


@permission_central_bp.route('/export', methods=['GET'])
@csrf.exempt
@admin_required
def export_rbac():
    """
    匯出 RBAC 權限（瀏覽器下載 JSON）。

    系統管理員: 匯出出廠預設值
    企業管理員: 匯出該企業的當前設定
    """
    org_code = _resolve_org_code()
    result = PermissionCentralService.export_rbac(
        org_secure_code=org_code,
        is_system_admin=_is_sys_admin()
    )

    if 'error' in result:
        return jsonify({'error': result['error']}), 400

    # 回傳 JSON 檔案下載
    json_str = json.dumps(result['data'], ensure_ascii=False, indent=2)
    filename = result['filename']

    return Response(
        json_str,
        mimetype='application/json',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"'
        }
    )


@permission_central_bp.route('/import', methods=['POST'])
@csrf.exempt
@admin_required
def import_rbac():
    """
    匯入 RBAC 權限（上傳 JSON 檔案）。

    系統管理員: 匯入為新的出廠預設值
    企業管理員: 匯入覆蓋該企業的角色權限
    """
    # 支援 file upload 或 JSON body
    import_data = None

    if request.files and 'file' in request.files:
        f = request.files['file']
        if not f.filename:
            return jsonify({'error': _('未選擇檔案')}), 400
        try:
            content = f.read().decode('utf-8')
            import_data = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            return jsonify({'error': _('檔案格式無效: %(error)s', error=str(e))}), 400
    else:
        import_data = request.get_json()

    if not import_data:
        return jsonify({'error': _('缺少匯入資料')}), 400

    org_code = _resolve_org_code()
    result = PermissionCentralService.import_rbac(
        org_secure_code=org_code,
        is_system_admin=_is_sys_admin(),
        import_data=import_data,
        operator_username=current_user.username
    )

    if 'error' in result:
        return jsonify({'error': result['error']}), 400

    return jsonify(result), 200


@permission_central_bp.route('/restore-defaults', methods=['POST'])
@csrf.exempt
@admin_required
def restore_defaults():
    """
    恢復 RBAC 預設權限（企業管理員專用）。

    讀取出廠預設值，覆蓋該企業系統角色的權限配置。
    """
    org_code = _resolve_org_code()
    if not org_code:
        return jsonify({'error': _('無法確定企業')}), 400

    result = PermissionCentralService.restore_defaults(
        org_secure_code=org_code,
        operator_username=current_user.username
    )

    if 'error' in result:
        return jsonify({'error': result['error']}), 400

    return jsonify(result), 200
