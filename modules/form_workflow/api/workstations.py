"""
FormWorkflow Module - Workstations API
工作站管理 API
"""
from flask import Blueprint, jsonify, request
from flask_login import current_user

from app.security.decorators import module_access_required
from app.platform.auth import require_permission
from app.platform.data import get_current_org
from app import db, csrf

workstations_bp = Blueprint(
    'form_workflow_workstations',
    __name__,
    url_prefix='/api/form-workflow/workstations'
)


def _get_user_name():
    return getattr(current_user, 'display_name', '') or getattr(current_user, 'native_name', '') or ''


# =============================================================================
# GET -- 列出工作站
# =============================================================================

@workstations_bp.route('', methods=['GET'])
@module_access_required('form_workflow')
def list_workstations():
    """
    列出工作站

    Query Parameters:
        all: 1 = 含停用（管理用），否則只顯示啟用的
    """
    from ..models import FwWorkstation

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    show_all = request.args.get('all') == '1'

    query = FwWorkstation.query.filter_by(
        org_secure_code=org.secure_code,
        is_deleted=False
    )
    if not show_all:
        query = query.filter_by(is_active=True)

    workstations = query.order_by(FwWorkstation.display_order, FwWorkstation.created_at).all()

    return jsonify({
        'success': True,
        'data': [ws.to_dict() for ws in workstations]
    })


# =============================================================================
# GET -- 取得單一工作站
# =============================================================================

@workstations_bp.route('/<secure_code>', methods=['GET'])
@module_access_required('form_workflow')
def get_workstation(secure_code):
    """取得工作站詳情"""
    from ..models import FwWorkstation, FwWorkstationPermission

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    ws = FwWorkstation.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()
    if not ws:
        return jsonify({'success': False, 'message': '工作站不存在'}), 404

    # 附帶權限列表
    permissions = FwWorkstationPermission.query.filter_by(
        workstation_secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).order_by(FwWorkstationPermission.grant_type, FwWorkstationPermission.created_at).all()

    data = ws.to_dict()
    data['permissions'] = [p.to_dict() for p in permissions]

    return jsonify({
        'success': True,
        'data': data
    })


# =============================================================================
# GET -- 依 code 取得工作站（前端 route 用）
# =============================================================================

@workstations_bp.route('/by-code/<code>', methods=['GET'])
@module_access_required('form_workflow')
def get_workstation_by_code(code):
    """依代碼取得工作站設定（表單中心前端載入用）"""
    from ..models import FwWorkstation

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    ws = FwWorkstation.query.filter_by(
        code=code.upper(),
        org_secure_code=org.secure_code,
        is_active=True,
        is_deleted=False
    ).first()
    if not ws:
        return jsonify({'success': False, 'message': '工作站不存在或未啟用'}), 404

    return jsonify({
        'success': True,
        'data': ws.to_dict()
    })


# =============================================================================
# POST -- 建立工作站
# =============================================================================

@workstations_bp.route('', methods=['POST'])
@csrf.exempt
@module_access_required('form_workflow')
@require_permission('form_workflow.admin')
def create_workstation():
    """
    建立工作站

    Body:
        code: 工作站代碼（大寫英文+底線）
        name: 顯示名稱
        description: 說明
        icon: 圖示 class
        filter_rules: 篩選規則 JSON
        ui_config: UI 配置 JSON
        display_order: 排序
    """
    from ..models import FwWorkstation

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    data = request.get_json() or {}
    code = (data.get('code') or '').strip().upper()
    name = (data.get('name') or '').strip()

    if not code:
        return jsonify({'success': False, 'message': 'code 為必填'}), 400
    if not name:
        return jsonify({'success': False, 'message': 'name 為必填'}), 400

    # 檢查 code 唯一
    existing = FwWorkstation.query.filter_by(
        code=code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()
    if existing:
        return jsonify({'success': False, 'message': f'工作站代碼 {code} 已存在'}), 400

    user_name = _get_user_name()
    user_sc = getattr(current_user, 'secure_code', '')

    ws = FwWorkstation(
        org_secure_code=org.secure_code,
        code=code,
        name=name,
        description=(data.get('description') or '').strip(),
        icon=(data.get('icon') or '').strip(),
        filter_rules=data.get('filter_rules') or {},
        ui_config=data.get('ui_config') or {},
        display_order=int(data.get('display_order', 0)),
        created_by_secure_code=user_sc,
        created_by_name=user_name,
        updated_by_secure_code=user_sc,
        updated_by_name=user_name,
    )

    db.session.add(ws)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': '工作站已建立',
        'data': ws.to_dict()
    }), 201


# =============================================================================
# PUT -- 更新工作站
# =============================================================================

@workstations_bp.route('/<secure_code>', methods=['PUT'])
@csrf.exempt
@module_access_required('form_workflow')
@require_permission('form_workflow.admin')
def update_workstation(secure_code):
    """更新工作站設定"""
    from ..models import FwWorkstation

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    ws = FwWorkstation.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()
    if not ws:
        return jsonify({'success': False, 'message': '工作站不存在'}), 404

    data = request.get_json() or {}

    # code 變更需檢查唯一
    if 'code' in data:
        new_code = (data['code'] or '').strip().upper()
        if new_code and new_code != ws.code:
            existing = FwWorkstation.query.filter_by(
                code=new_code,
                org_secure_code=org.secure_code,
                is_deleted=False
            ).first()
            if existing:
                return jsonify({'success': False, 'message': f'工作站代碼 {new_code} 已存在'}), 400
            ws.code = new_code

    if 'name' in data:
        ws.name = (data['name'] or '').strip()
    if 'description' in data:
        ws.description = (data['description'] or '').strip()
    if 'icon' in data:
        ws.icon = (data['icon'] or '').strip()
    if 'filter_rules' in data:
        ws.filter_rules = data['filter_rules'] or {}
    if 'ui_config' in data:
        ws.ui_config = data['ui_config'] or {}
    if 'is_active' in data:
        ws.is_active = bool(data['is_active'])
    if 'display_order' in data:
        ws.display_order = int(data.get('display_order', 0))

    ws.updated_by_secure_code = getattr(current_user, 'secure_code', '')
    ws.updated_by_name = _get_user_name()

    db.session.commit()

    return jsonify({
        'success': True,
        'message': '工作站已更新',
        'data': ws.to_dict()
    })


# =============================================================================
# DELETE -- 刪除工作站（軟刪除）
# =============================================================================

@workstations_bp.route('/<secure_code>', methods=['DELETE'])
@csrf.exempt
@module_access_required('form_workflow')
@require_permission('form_workflow.admin')
def delete_workstation(secure_code):
    """刪除工作站"""
    from ..models import FwWorkstation, FwWorkstationPermission

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    ws = FwWorkstation.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()
    if not ws:
        return jsonify({'success': False, 'message': '工作站不存在'}), 404

    ws.is_deleted = True

    # 同步軟刪除權限
    FwWorkstationPermission.query.filter_by(
        workstation_secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).update({'is_deleted': True})

    db.session.commit()

    return jsonify({
        'success': True,
        'message': '工作站已刪除'
    })


# =============================================================================
# POST -- 新增工作站權限
# =============================================================================

@workstations_bp.route('/<ws_secure_code>/permissions', methods=['POST'])
@csrf.exempt
@module_access_required('form_workflow')
@require_permission('form_workflow.admin')
def create_ws_permission(ws_secure_code):
    """
    新增工作站存取權限

    Body:
        grant_type: department / group / user
        grant_target: 目標 secure_code
        grant_target_name: 顯示名稱
        include_children: boolean
    """
    from ..models import FwWorkstation, FwWorkstationPermission

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    ws = FwWorkstation.query.filter_by(
        secure_code=ws_secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()
    if not ws:
        return jsonify({'success': False, 'message': '工作站不存在'}), 404

    data = request.get_json() or {}
    grant_type = data.get('grant_type', '')
    grant_target = data.get('grant_target', '')
    grant_target_name = data.get('grant_target_name', '')

    if grant_type not in ('department', 'group', 'user'):
        return jsonify({'success': False, 'message': 'grant_type 必須為 department / group / user'}), 400
    if not grant_target:
        return jsonify({'success': False, 'message': 'grant_target 為必填'}), 400

    # 檢查重複
    existing = FwWorkstationPermission.query.filter_by(
        workstation_secure_code=ws_secure_code,
        org_secure_code=org.secure_code,
        grant_type=grant_type,
        grant_target=grant_target,
        is_deleted=False
    ).first()
    if existing:
        return jsonify({'success': False, 'message': '此規則已存在'}), 400

    include_children = bool(data.get('include_children', False)) if grant_type in ('department', 'group') else False

    perm = FwWorkstationPermission(
        org_secure_code=org.secure_code,
        workstation_secure_code=ws_secure_code,
        grant_type=grant_type,
        grant_target=grant_target,
        grant_target_name=grant_target_name,
        include_children=include_children,
        created_by_name=_get_user_name(),
    )

    db.session.add(perm)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': '權限已新增',
        'data': perm.to_dict()
    }), 201


# =============================================================================
# DELETE -- 刪除工作站權限
# =============================================================================

@workstations_bp.route('/permissions/<secure_code>', methods=['DELETE'])
@csrf.exempt
@module_access_required('form_workflow')
@require_permission('form_workflow.admin')
def delete_ws_permission(secure_code):
    """刪除工作站權限規則"""
    from ..models import FwWorkstationPermission

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    perm = FwWorkstationPermission.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()
    if not perm:
        return jsonify({'success': False, 'message': '規則不存在'}), 404

    perm.is_deleted = True
    db.session.commit()

    return jsonify({
        'success': True,
        'message': '權限已刪除'
    })
