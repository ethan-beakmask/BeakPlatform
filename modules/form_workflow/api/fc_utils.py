"""
表單中心 - 輔助功能（當前用戶、組織樹、欄位設定、欄位權限處理）
"""
import copy
from collections import Counter
from datetime import datetime

from flask import jsonify, request, g
from flask_login import current_user

from app.security.decorators import module_access_required
from app.platform.data import get_current_org
from app import db, csrf

from .form_center import form_center_bp
from flask_babel import gettext as _


# =============================================================================
# 欄位權限處理（供其他模組使用）
# =============================================================================

def _apply_field_permissions_to_schema(schema, role_permissions):
    """
    根據欄位權限修改 form.io schema

    role_permissions: {"field_key": "hidden"|"readonly"|"editable", ...}
    未配置的欄位預設為 readonly

    Returns: (modified_schema, has_editable)
    """
    schema = copy.deepcopy(schema)
    has_editable = False

    def process_components(components):
        nonlocal has_editable
        result = []
        for comp in components:
            comp = dict(comp)

            # 處理容器元件 (panel, columns, fieldset, tabs, well 等)
            if 'components' in comp:
                comp['components'] = process_components(comp['components'])
                result.append(comp)
                continue

            # 處理 columns 元件
            if 'columns' in comp:
                for col in comp.get('columns', []):
                    if 'components' in col:
                        col['components'] = process_components(col['components'])
                result.append(comp)
                continue

            key = comp.get('key')
            if not key:
                result.append(comp)
                continue

            perm = role_permissions.get(key, 'readonly')

            if perm == 'hidden':
                # 跳過此欄位 (不加入結果)
                continue
            elif perm == 'editable':
                comp['disabled'] = False
                has_editable = True
                result.append(comp)
            else:
                # readonly (預設)
                comp['disabled'] = True
                result.append(comp)

        return result

    if schema.get('components'):
        schema['components'] = process_components(schema['components'])

    return schema, has_editable


# =============================================================================
# UserPicker 支援 API
# =============================================================================

@form_center_bp.route('/current-user')
@module_access_required('form_workflow', False)
def get_current_user_info():
    """
    取得當前登入者基本資訊（供 UserPicker 預設值）

    GET /api/form-center/current-user
    Returns: { secure_code, display_name, dept_name }
    """
    dept_name = ''
    if current_user.primary_unit:
        dept_name = current_user.primary_unit.name or ''

    return jsonify({
        'success': True,
        'data': {
            'secure_code': current_user.secure_code,
            'username': current_user.username,
            'display_name': current_user.display_name or current_user.native_name or current_user.username,
            'dept_name': dept_name,
        }
    })


@form_center_bp.route('/org-tree')
@module_access_required('form_workflow', False)
def get_org_tree():
    """
    取得簡化版部門+人員樹（供 UserPicker 選人用）

    GET /api/form-center/org-tree
    Returns: BaekTree 格式的部門人員樹
    """
    from app.models import OrganizationalUnit, UnitType
    from app.models.user import User, UserType
    from app.security.resource_gateway import ResourceGateway

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    # PF-145：外部廠商一律拿空樹。
    # UserPicker 的可選對象只有企業成員（下面的 users 查詢就只取 EMPLOYEE/ORG_ADMIN），
    # 廠商拿到這棵樹沒有用途，卻會外洩完整部門結構與全部內部帳號——
    # 過去連 username 都給，那是帳號列舉與「觸發登入鎖定把人鎖出系統」的現成素材。
    # 這支端點的閘門是模組合約（表單中心對廠商刻意開放），所以擋不能靠 decorator，
    # 只能在這裡依身分裁剪回傳範圍。
    if current_user.is_external:
        return jsonify({'success': True, 'data': []})

    org_sc = current_user.org_secure_code

    # 取得所有啟用部門
    # check_permission=False: 員工填單選簽核人需要組織樹，閘門為模組合約
    departments = ResourceGateway.filter(
        OrganizationalUnit,
        is_deleted=False,
        unit_type=UnitType.DEPARTMENT,
        order_by='sort_order',
        check_permission=False,
    )

    # 取得所有啟用的企業成員帳號
    users = User.query.filter(  # nosemgrep: beakplatform-direct-model-query-in-api
        User.org_secure_code == org_sc,
        User.is_deleted == False,
        User.is_active == True,
        User.user_type.in_([UserType.EMPLOYEE, UserType.ORG_ADMIN]),
    ).order_by(User.display_name).all()

    # 建立 dept_sc -> users 映射
    dept_users = {}
    unassigned_users = []
    for u in users:
        if u.primary_unit_secure_code:
            dept_users.setdefault(u.primary_unit_secure_code, []).append(u)
        else:
            unassigned_users.append(u)

    # PF-145：label 與 data 都不再帶 username（登入帳號名，外洩即帳號列舉素材）。
    # 原本一律顯示「顯示名 (username)」，現在只有真的重名時才加區隔資訊：
    #   第一順位 部門名     —— 最直覺，同部門又同名的機率極低
    #   第二順位 員工編號   —— 組織內唯一（見 users.employee_id 欄位註解）
    # 兩者都取不到就不加後綴。**不要拿暱稱（native_name）或 username 來墊**：
    # 前者可免填、後者正是這次要停止外流的東西。
    # 已知落差：兩帳號制（PERMISSION_MODEL.md §5.1）的管理員帳號沒有 employee_id，
    # 所以同名的成員帳號會拿到「(編號)」而管理員帳號沒有後綴——仍分得出來，
    # 但要靠推理。要更明確就得幫管理員帳號補編號。
    # display_name 是 nullable=False，fallback 鏈的 native_name/username 實務上不會走到。
    _name_counts = Counter(
        (u.display_name or u.native_name or u.username) for u in users)

    def _user_node(u):
        dn = u.display_name or u.native_name or u.username
        dept_name = u.primary_unit.name if u.primary_unit else ''
        label = dn
        if _name_counts[dn] > 1:
            hint = dept_name or (u.employee_id or '')
            # hint 與顯示名相同時加了也沒有資訊量
            if hint and hint != dn:
                label = f'{dn} ({hint})'
        return {
            'id': u.secure_code,
            'label': label,
            'data': {
                'type': 'person',
                'secure_code': u.secure_code,
                'display_name': dn,
                'dept_name': dept_name,
            },
        }

    # 建立 dept_sc -> dept 映射
    dept_map = {d.secure_code: d for d in departments}

    def _build_dept_node(dept):
        children = []
        # 加入人員
        for u in dept_users.get(dept.secure_code, []):
            children.append(_user_node(u))
        # 加入子部門
        for d in departments:
            if d.parent_secure_code == dept.secure_code:
                children.append(_build_dept_node(d))
        return {
            'id': f'dept_{dept.secure_code}',
            'label': dept.name,
            'expanded': True,
            'data': {'type': 'dept'},
            'children': children,
        }

    # 根節點
    root_children = []
    root_depts = [d for d in departments if d.parent_secure_code is None]
    for d in root_depts:
        root_children.append(_build_dept_node(d))

    # 未分配人員
    if unassigned_users:
        unassigned_children = [_user_node(u) for u in unassigned_users]
        root_children.append({
            'id': 'dept_unassigned',
            'label': '未分配部門',
            'expanded': True,
            'data': {'type': 'dept'},
            'children': unassigned_children,
        })

    tree = [{
        'id': 'root',
        'label': org.display_name or org.name,
        'expanded': True,
        'data': {'type': 'root'},
        'children': root_children,
    }]

    return jsonify({'success': True, 'data': tree})


# =============================================================================
# 欄位顯示設定 API
# =============================================================================

# 欄位定義（column_key -> 預設值）
FC_COLUMN_DEFAULTS = {
    'serial_number':  {'width': 140, 'hidden': False},
    'form_name':      {'width': 120, 'hidden': False},
    'subject':        {'width': None, 'hidden': False},
    'applicant':      {'width': 100, 'hidden': False},
    'category':       {'width': 80, 'hidden': False},
    'current_node':   {'width': 140, 'hidden': False},
    'wait_time':      {'width': 150, 'hidden': False},
    'submit_time':    {'width': 130, 'hidden': False},
    'signed_elapsed': {'width': 130, 'hidden': False},
    'end_time':       {'width': 130, 'hidden': False},
    'status':         {'width': 70, 'hidden': False},
    'duration':       {'width': 100, 'hidden': False},
    'actions':        {'width': 110, 'hidden': False},
}


@form_center_bp.route('/column-config')
@module_access_required('form_workflow', False)
def get_column_config():
    """
    取得當前用戶語系的欄位顯示設定

    查詢順序：用戶語系 -> '*' 通用 -> 程式預設值
    """
    from ..models import FwColumnDisplayConfig

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    user_locale = getattr(g, 'locale', 'zh-TW') or 'zh-TW'

    # 查詢：先找精確語系，再��通用
    config_row = FwColumnDisplayConfig.query.filter_by(
        org_secure_code=org.secure_code,
        locale=user_locale,
        is_deleted=False
    ).first()

    if not config_row:
        config_row = FwColumnDisplayConfig.query.filter_by(
            org_secure_code=org.secure_code,
            locale='*',
            is_deleted=False
        ).first()

    if config_row:
        # 用儲存的設定合併預設值（確保新增欄位有預設）
        merged = {}
        for key, defaults in FC_COLUMN_DEFAULTS.items():
            saved = (config_row.config or {}).get(key, {})
            merged[key] = {
                'width': saved.get('width', defaults['width']),
                'hidden': saved.get('hidden', defaults['hidden']),
            }
        return jsonify({
            'success': True,
            'data': {'locale': config_row.locale, 'config': merged}
        })

    # 無設定，回傳預設值
    return jsonify({
        'success': True,
        'data': {'locale': None, 'config': FC_COLUMN_DEFAULTS}
    })


@form_center_bp.route('/column-config/all')
@module_access_required('form_workflow')
def list_column_configs():
    """取得企業所有語系的欄位設定（管理員用）"""
    from ..models import FwColumnDisplayConfig

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    configs = FwColumnDisplayConfig.query.filter_by(
        org_secure_code=org.secure_code,
        is_deleted=False
    ).order_by(FwColumnDisplayConfig.locale).all()

    return jsonify({
        'success': True,
        'data': {
            'configs': [c.to_dict() for c in configs],
            'defaults': FC_COLUMN_DEFAULTS,
        }
    })


@form_center_bp.route('/column-config', methods=['PUT'])
@csrf.exempt
@module_access_required('form_workflow')
def save_column_config():
    """儲存欄位顯示設定（管理員用）"""
    from ..models import FwColumnDisplayConfig

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    data = request.get_json()
    locale = data.get('locale', '*')
    config = data.get('config', {})

    # 驗證 config 格式
    valid_keys = set(FC_COLUMN_DEFAULTS.keys())
    cleaned = {}
    for key, val in config.items():
        if key not in valid_keys:
            continue
        cleaned[key] = {
            'width': val.get('width') if isinstance(val.get('width'), (int, float)) else FC_COLUMN_DEFAULTS[key]['width'],
            'hidden': bool(val.get('hidden', False)),
        }
    # subject 和 actions 強制不隱藏
    if 'subject' in cleaned:
        cleaned['subject']['hidden'] = False
        cleaned['subject']['width'] = None
    if 'actions' in cleaned:
        cleaned['actions']['hidden'] = False

    config_row = FwColumnDisplayConfig.query.filter_by(
        org_secure_code=org.secure_code,
        locale=locale,
        is_deleted=False
    ).first()

    if config_row:
        config_row.config = cleaned
        config_row.updated_at = datetime.utcnow()
    else:
        config_row = FwColumnDisplayConfig(
            org_secure_code=org.secure_code,
            locale=locale,
            config=cleaned
        )
        db.session.add(config_row)

    db.session.commit()

    return jsonify({
        'success': True,
        'message': _('語系 %(locale)s 的欄位設定已儲存', locale=locale),
        'data': config_row.to_dict()
    })
