"""
BeakMask OrganizationalUnit API
組織單位 (部門/群組) API
"""
import logging
from datetime import datetime

from flask import Blueprint, request, jsonify
from flask_babel import gettext as _
from flask_login import current_user

from sqlalchemy import func
from ..security.decorators import admin_required, login_required
from ..security.resource_gateway import ResourceGateway
from ..models import OrganizationalUnit, UnitType, Role
from ..services.code_generator import get_code_generator
from ..models.user import User, UserType
from ..models.user_unit_membership import UserUnitMembership, MembershipType, MembershipRole
from .. import db

logger = logging.getLogger(__name__)

units_bp = Blueprint('api_units', __name__, url_prefix='/api/units')


def _get_system_role(org_sc: str, role_code: str) -> Role:
    """取得企業的系統角色 (by code)"""
    return Role.query.filter(
        Role.org_secure_code == org_sc,
        Role.code == role_code,
        Role.is_deleted == False,
    ).first()


def _ensure_role_assignment(org_sc: str, user_sc: str, role_sc: str,
                            unit_sc: str, operator: str):
    """
    確保角色指派存在（建立或恢復軟刪除的記錄）。
    """
    from ..models.associations import UserRoleAssignment

    existing = UserRoleAssignment.query.filter(
        UserRoleAssignment.org_secure_code == org_sc,
        UserRoleAssignment.user_secure_code == user_sc,
        UserRoleAssignment.role_secure_code == role_sc,
        UserRoleAssignment.unit_secure_code == unit_sc,
    ).first()

    if existing:
        if existing.is_deleted:
            existing.is_deleted = False
            existing.deleted_at = None
        return

    assignment = UserRoleAssignment(
        org_secure_code=org_sc,
        user_secure_code=user_sc,
        role_secure_code=role_sc,
        unit_secure_code=unit_sc,
        assigned_by=operator,
    )
    db.session.add(assignment)


def _revoke_role_assignment(org_sc: str, user_sc: str, role_sc: str,
                            unit_sc: str):
    """軟刪除指定角色指派"""
    from ..models.associations import UserRoleAssignment

    assignment = UserRoleAssignment.query.filter(
        UserRoleAssignment.org_secure_code == org_sc,
        UserRoleAssignment.user_secure_code == user_sc,
        UserRoleAssignment.role_secure_code == role_sc,
        UserRoleAssignment.unit_secure_code == unit_sc,
        UserRoleAssignment.is_deleted == False,
    ).first()

    if assignment:
        assignment.is_deleted = True
        assignment.deleted_at = datetime.utcnow()


def _ensure_dept_membership(user, unit, operator_email: str):
    """
    確保部門成員關係與系統角色存在。

    1. 建立或恢復 UserUnitMembership(SOLID)
    2. 指派 DEPT_MEMBER (部門成員基底角色)
    3. 指派 DEPT_EMPLOYEE (部門員工，預設非管理職)
    """
    org_sc = unit.org_secure_code
    user_sc = user.secure_code
    unit_sc = unit.secure_code

    # 1. SOLID 成員關係
    existing = UserUnitMembership.query.filter(
        UserUnitMembership.org_secure_code == org_sc,
        UserUnitMembership.user_secure_code == user_sc,
        UserUnitMembership.unit_secure_code == unit_sc,
        UserUnitMembership.membership_type == MembershipType.SOLID,
    ).first()

    if existing:
        if existing.is_deleted:
            existing.is_deleted = False
            existing.deleted_at = None
    else:
        membership = UserUnitMembership(
            org_secure_code=org_sc,
            user_secure_code=user_sc,
            unit_secure_code=unit_sc,
            membership_type=MembershipType.SOLID,
            role_type=MembershipRole.MEMBER,
        )
        db.session.add(membership)

    # 2. 指派 DEPT_MEMBER (基底角色，所有部門人員都有)
    dept_member = _get_system_role(org_sc, 'DEPT_MEMBER')
    if dept_member:
        _ensure_role_assignment(
            org_sc, user_sc, dept_member.secure_code, unit_sc, operator_email
        )

    # 3. 指派 DEPT_EMPLOYEE (預設非管理職)
    dept_employee = _get_system_role(org_sc, 'DEPT_EMPLOYEE')
    if dept_employee:
        _ensure_role_assignment(
            org_sc, user_sc, dept_employee.secure_code, unit_sc, operator_email
        )


def _remove_dept_membership(user, unit):
    """
    移除部門成員關係與所有部門角色。

    1. 軟刪除 UserUnitMembership(SOLID)
    2. 軟刪除該部門下的所有部門系統角色指派 (DEPT_MEMBER, DEPT_EMPLOYEE, DEPT_MANAGER)
    """
    from ..models.associations import UserRoleAssignment

    org_sc = unit.org_secure_code
    user_sc = user.secure_code
    unit_sc = unit.secure_code

    # 1. 軟刪除 SOLID 成員關係
    membership = UserUnitMembership.query.filter(
        UserUnitMembership.org_secure_code == org_sc,
        UserUnitMembership.user_secure_code == user_sc,
        UserUnitMembership.unit_secure_code == unit_sc,
        UserUnitMembership.membership_type == MembershipType.SOLID,
        UserUnitMembership.is_deleted == False,
    ).first()

    if membership:
        membership.is_deleted = True
        membership.deleted_at = datetime.utcnow()

    # 2. 軟刪除此部門下的所有部門系統角色
    for role_code in ('DEPT_MEMBER', 'DEPT_EMPLOYEE', 'DEPT_MANAGER'):
        role = _get_system_role(org_sc, role_code)
        if role:
            _revoke_role_assignment(org_sc, user_sc, role.secure_code, unit_sc)


def _is_admin(user) -> bool:
    """Check if user is system admin or org admin"""
    return (
        getattr(user, 'is_system_admin', False)
        or getattr(user, 'is_org_admin', False)
    )


def _is_group_leader(user, unit_secure_code: str) -> bool:
    """
    Check if user is MANAGER or DEPUTY of a specific group.
    Admins always pass.
    """
    if _is_admin(user):
        return True
    membership = UserUnitMembership.query.filter(  # nosemgrep: beakplatform-direct-model-query-in-api
        UserUnitMembership.user_secure_code == user.secure_code,
        UserUnitMembership.unit_secure_code == unit_secure_code,
        UserUnitMembership.role_type.in_([MembershipRole.MANAGER, MembershipRole.DEPUTY]),
        UserUnitMembership.is_deleted == False
    ).first()
    return membership is not None


def _get_managed_group_scs(user) -> list:
    """Get list of group secure_codes where user is MANAGER or DEPUTY"""
    memberships = UserUnitMembership.query.filter(  # nosemgrep: beakplatform-direct-model-query-in-api
        UserUnitMembership.user_secure_code == user.secure_code,
        UserUnitMembership.org_secure_code == user.org_secure_code,
        UserUnitMembership.role_type.in_([MembershipRole.MANAGER, MembershipRole.DEPUTY]),
        UserUnitMembership.is_deleted == False
    ).all()
    return [m.unit_secure_code for m in memberships]


def _is_in_external_tree(unit: OrganizationalUnit) -> bool:
    """判斷群組是否屬於 EXTERNAL_VENDORS 子樹（含自身）"""
    cur = unit
    while cur:
        if cur.code == 'EXTERNAL_VENDORS':
            return True
        if not cur.parent_secure_code:
            return False
        cur = OrganizationalUnit.query.filter(
            OrganizationalUnit.secure_code == cur.parent_secure_code,
            OrganizationalUnit.is_deleted == False
        ).first()
    return False


@units_bp.route('/', methods=['GET'])
@admin_required
def list_units():
    """
    取得組織單位列表

    GET /api/units
    Query params:
        - type: DEPARTMENT / GROUP (篩選)
        - parent_id: 父層 secure_code (篩選)
        - tree: true = 返回樹狀結構
    """
    unit_type = request.args.get('type')
    parent_id = request.args.get('parent_id')
    as_tree = request.args.get('tree', 'false').lower() == 'true'

    filters = {'is_deleted': False}
    if unit_type:
        filters['unit_type'] = unit_type
    if parent_id:
        if parent_id == 'root':
            filters['parent_secure_code'] = None
        else:
            filters['parent_secure_code'] = parent_id

    units = ResourceGateway.filter(
        OrganizationalUnit,
        order_by='sort_order',
        require_permission='department:read',
        **filters
    )

    if as_tree:
        # 建立樹狀結構
        root_units = [u for u in units if u.parent_secure_code is None]
        return jsonify({
            'units': [u.to_dict(include_children=True) for u in root_units]
        }), 200

    return jsonify({
        'units': [u.to_dict() for u in units]
    }), 200


@units_bp.route('/<secure_code>', methods=['GET'])
@admin_required
def get_unit(secure_code: str):
    """
    取得單一組織單位

    GET /api/units/<secure_code>
    """
    unit = ResourceGateway.get_by(
        OrganizationalUnit,
        secure_code=secure_code,
        is_deleted=False
    )

    if not unit:
        return jsonify({'error': _('組織單位不存在')}), 404

    return jsonify({
        'unit': unit.to_dict(include_children=True, include_ancestors=True)
    }), 200


@units_bp.route('/', methods=['POST'])
@admin_required
def create_unit():
    """
    建立組織單位

    POST /api/units
    Body: {
        "code": "SALES",
        "name": "業務部",
        "unit_type": "DEPARTMENT",
        "parent_id": null,
        "description": "業務部門"
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': _('請提供單位資料')}), 400

    # name 必填
    if 'name' not in data or not data['name'].strip():
        return jsonify({'error': _('缺少必要欄位: name')}), 400

    name = data['name'].strip()
    code = data.get('code', '').strip()

    # code 空白時自動產生
    if not code:
        generator = get_code_generator()
        def _exists(c):
            return OrganizationalUnit.query.filter(
                func.upper(OrganizationalUnit.code) == c.upper(),
                OrganizationalUnit.org_secure_code == current_user.org_secure_code,
                OrganizationalUnit.is_deleted == False
            ).first() is not None
        try:
            code = generator.generate(name, exists_checker=_exists)
        except ValueError as e:
            return jsonify({'error': _('無法自動產生代碼: %(error)s', error=e)}), 400
    else:
        # 驗證代碼格式：允許英文、數字、底線、連字號
        import re
        if not re.match(r'^[A-Za-z][A-Za-z0-9_-]*$', code):
            return jsonify({'error': _('代碼只能包含英文字母、數字、底線(_)、連字號(-)，且開頭必須是英文')}), 400

    # 驗證長度
    if len(code) > 50:
        return jsonify({'error': _('代碼長度不可超過 50 字元（目前 %(length)s 字元）', length=len(code))}), 400
    if len(code) < 2:
        return jsonify({'error': _('代碼長度至少 2 字元')}), 400
    if len(name) > 255:
        return jsonify({'error': _('名稱長度不可超過 255 字元（目前 %(length)s 字元）', length=len(name))}), 400
    if len(name) < 1:
        return jsonify({'error': _('名稱不可為空')}), 400

    # 檢查代碼是否重複 (case-insensitive)
    existing = OrganizationalUnit.query.filter(
        func.upper(OrganizationalUnit.code) == code.upper(),
        OrganizationalUnit.org_secure_code == current_user.org_secure_code,
        OrganizationalUnit.is_deleted == False
    ).first()
    if existing:
        return jsonify({'error': _('代碼 %(code)s 已存在', code=code)}), 400

    # 檢查父層
    parent = None
    if data.get('parent_id'):
        parent = ResourceGateway.get_by(
            OrganizationalUnit,
            secure_code=data['parent_id'],
            is_deleted=False
        )

        if not parent:
            return jsonify({'error': _('父層單位不存在')}), 400

    try:
        unit = OrganizationalUnit(
            org_secure_code=current_user.org_secure_code,
            unit_type=data.get('unit_type', UnitType.DEPARTMENT),
            code=code,
            name=name,
            description=data.get('description'),
            parent_secure_code=parent.secure_code if parent else None,
            sort_order=data.get('sort_order', 0),
            is_active=True
        )
        unit.update_full_path()
        db.session.add(unit)

        db.session.commit()

        logger.info(f"Unit created: {unit.code} by {current_user.email}")

        return jsonify({
            'message': _('組織單位建立成功'),
            'unit': unit.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to create unit: {e}")
        return jsonify({'error': _('建立組織單位失敗')}), 500


@units_bp.route('/<secure_code>', methods=['PUT'])
@admin_required
def update_unit(secure_code: str):
    """
    更新組織單位

    PUT /api/units/<secure_code>
    """
    unit = ResourceGateway.get_by(
        OrganizationalUnit,
        secure_code=secure_code,
        is_deleted=False
    )

    if not unit:
        return jsonify({'error': _('組織單位不存在')}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': _('請提供更新資料')}), 400

    try:
        old_name = unit.name

        if 'name' in data:
            unit.name = data['name']
        if 'description' in data:
            unit.description = data['description']
        if 'sort_order' in data:
            unit.sort_order = data['sort_order']
        if 'is_active' in data:
            unit.is_active = data['is_active']

        # 更新父層
        if 'parent_id' in data:
            if data['parent_id']:
                # 檢查不能設定自己為父層
                if data['parent_id'] == unit.secure_code:
                    return jsonify({'error': _('不能設定自己為父層')}), 400

                # 檢查不能設定自己的子層為父層
                descendants = unit.get_descendants()
                if any(d.secure_code == data['parent_id'] for d in descendants):
                    return jsonify({'error': _('不能設定子層為父層')}), 400

                parent = ResourceGateway.get_by(
                    OrganizationalUnit,
                    secure_code=data['parent_id'],
                    is_deleted=False
                )

                if not parent:
                    return jsonify({'error': _('父層單位不存在')}), 400

                # 群組不可跨樹系移動（企業 <-> EXTERNAL_VENDORS）
                if unit.unit_type == UnitType.GROUP:
                    src_ext = _is_in_external_tree(unit)
                    tgt_ext = _is_in_external_tree(parent)
                    if src_ext != tgt_ext:
                        return jsonify({'error': _('不可在企業群組與外部廠商群組之間移動')}), 400

                unit.parent_secure_code = parent.secure_code
            else:
                unit.parent_secure_code = None

        # 更新路徑
        unit.update_full_path()

        # 如果名稱變更，更新所有子層路徑
        if unit.name != old_name:
            unit.update_children_paths()

        db.session.commit()

        return jsonify({
            'message': _('組織單位更新成功'),
            'unit': unit.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update unit: {e}")
        return jsonify({'error': _('更新組織單位失敗')}), 500


@units_bp.route('/<secure_code>', methods=['DELETE'])
@admin_required
def delete_unit(secure_code: str):
    """
    刪除組織單位 (軟刪除)

    DELETE /api/units/<secure_code>
    Query params:
        - cascade: true = 一併刪除子單位
        - confirm_members: true = 確認移除成員到未分配
        - check_only: true = 只檢查不刪除，回傳子單位和成員數量
    """
    unit = ResourceGateway.get_by(
        OrganizationalUnit,
        secure_code=secure_code,
        is_deleted=False
    )

    if not unit:
        return jsonify({'error': _('組織單位不存在')}), 404

    # 系統保留單位不可刪除
    if unit.is_system_unit:
        return jsonify({'error': _('此為系統保留單位，不可刪除')}), 403

    cascade = request.args.get('cascade', 'false').lower() == 'true'
    confirm_members = request.args.get('confirm_members', 'false').lower() == 'true'
    check_only = request.args.get('check_only', 'false').lower() == 'true'

    # 統計子單位和成員
    children = [c for c in unit.children if not c.is_deleted]
    children_count = len(children)

    # 統計所有成員（含子單位）
    def count_members(u):
        count = User.query.filter_by(
            primary_unit_secure_code=u.secure_code,
            is_deleted=False
        ).count()
        for child in [c for c in u.children if not c.is_deleted]:
            count += count_members(child)
        return count

    if cascade:
        members_count = count_members(unit)
    else:
        members_count = User.query.filter_by(
            primary_unit_secure_code=unit.secure_code,
            is_deleted=False
        ).count()

    # 只檢查，不刪除
    if check_only:
        return jsonify({
            'children_count': children_count,
            'members_count': members_count
        }), 200

    # 只檢查時不需要確認
    if not check_only:
        # 有子單位但沒有 cascade
        if children_count > 0 and not cascade:
            return jsonify({
                'error': _('此單位有 %(count)s 個子單位', count=children_count),
                'children_count': children_count,
                'need_cascade': True
            }), 400

        # 有成員但沒有確認
        if members_count > 0 and not confirm_members:
            return jsonify({
                'error': _('此單位有 %(count)s 個成員', count=members_count),
                'members_count': members_count,
                'need_confirm_members': True
            }), 400

    try:
        def soft_delete_unit(u):
            # 將成員移到未分配
            members = User.query.filter_by(
                primary_unit_secure_code=u.secure_code,
                is_deleted=False
            ).all()
            for member in members:
                member.primary_unit_secure_code = None

            # 清除主管/副主管/代理人
            u.manager_secure_code = None
            u.deputy_manager_secure_code = None
            u.proxy1_secure_code = None
            u.proxy2_secure_code = None

            u.is_deleted = True
            u.deleted_at = datetime.utcnow()

        if cascade:
            # 遞迴刪除所有子單位（從最深層開始）
            descendants = unit.get_descendants(include_self=True)
            for d in reversed(descendants):
                soft_delete_unit(d)
        else:
            soft_delete_unit(unit)

        db.session.commit()

        msg = _('組織單位已刪除')
        if members_count > 0:
            msg += _('，%(count)s 位成員已移至未分配', count=members_count)

        return jsonify({
            'message': msg
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to delete unit: {e}")
        return jsonify({'error': _('刪除組織單位失敗')}), 500


# =====================================================
# 部門 API (便捷路由)
# =====================================================

@units_bp.route('/departments', methods=['GET'])
@admin_required
def list_departments():
    """取得部門列表"""
    request.args = request.args.copy()
    request.args['type'] = UnitType.DEPARTMENT
    return list_units()


@units_bp.route('/groups', methods=['GET'])
@login_required
def list_groups():
    """
    取得群組列表

    Admin: 回傳全部群組
    Team leader (MANAGER/DEPUTY): 只回傳管理的群組
    """
    as_tree = request.args.get('tree', 'false').lower() == 'true'

    if _is_admin(current_user):
        # Admin: 走原本的 list_units 邏輯
        # check_permission=False: /groups 自帶 admin/團長分流縮限邏輯
        all_groups = ResourceGateway.filter(
            OrganizationalUnit,
            is_deleted=False,
            unit_type=UnitType.GROUP,
            order_by='sort_order',
            check_permission=False,
        )
        if as_tree:
            root_groups = [u for u in all_groups if u.parent_secure_code is None]
            return jsonify({
                'units': [u.to_dict(include_children=True) for u in root_groups]
            }), 200
        return jsonify({
            'units': [u.to_dict() for u in all_groups]
        }), 200

    # Team leader: 只回傳管理的群組
    managed_scs = _get_managed_group_scs(current_user)
    if not managed_scs:
        return jsonify({'units': []}), 200

    # check_permission=False: 團長只回傳自己管理的群組（下方過濾）
    managed_groups = ResourceGateway.filter(
        OrganizationalUnit,
        is_deleted=False,
        unit_type=UnitType.GROUP,
        order_by='sort_order',
        check_permission=False,
    )
    # 只保留管理的群組 (展平為頂層)
    filtered = [u for u in managed_groups if u.secure_code in managed_scs]
    return jsonify({
        'units': [u.to_dict() for u in filtered]
    }), 200


@units_bp.route('/<secure_code>/members', methods=['GET'])
@admin_required
def get_unit_members(secure_code: str):
    """
    取得部門成員列表

    GET /api/units/<secure_code>/members

    返回該部門下所有 primary_unit_secure_code 為此部門的用戶
    """
    from ..models.user import User

    unit = ResourceGateway.get_by(
        OrganizationalUnit,
        secure_code=secure_code,
        is_deleted=False
    )

    if not unit:
        return jsonify({'error': _('組織單位不存在')}), 404

    from ..models.user import UserType

    # 只顯示企業成員帳號 (與 /users/ 頁面一致)
    members = User.query.filter(  # nosemgrep: beakplatform-direct-model-query-in-api
        User.org_secure_code == current_user.org_secure_code,
        User.primary_unit_secure_code == secure_code,
        User.is_deleted == False,
        User.is_active == True,
        User.user_type == UserType.EMPLOYEE
    ).order_by(User.display_name).all()

    return jsonify({
        'members': [
            {
                'id': m.secure_code,
                'display_name': m.display_name,
                'native_name': m.native_name,
                'english_name': m.english_name,
                'employee_id': m.employee_id,
                'email': m.email
            }
            for m in members
        ]
    }), 200


@units_bp.route('/unassigned-users', methods=['GET'])
@admin_required
def get_unassigned_users():
    """
    取得尚未分配部門的用戶列表

    GET /api/units/unassigned-users

    返回 primary_unit_secure_code 為 NULL 的用戶
    """
    from ..models.user import User, UserType

    # 只顯示企業成員帳號 (與 /users/ 頁面一致)
    users = User.query.filter(  # nosemgrep: beakplatform-direct-model-query-in-api
        User.org_secure_code == current_user.org_secure_code,
        User.primary_unit_secure_code == None,
        User.is_deleted == False,
        User.is_active == True,
        User.user_type == UserType.EMPLOYEE
    ).order_by(User.display_name).all()

    return jsonify({
        'users': [
            {
                'id': u.secure_code,
                'display_name': u.display_name,
                'native_name': u.native_name,
                'english_name': u.english_name,
                'employee_id': u.employee_id,
                'email': u.email,
                'username': u.username
            }
            for u in users
        ]
    }), 200


@units_bp.route('/<secure_code>/members', methods=['POST'])
@admin_required
def add_member_to_unit(secure_code: str):
    """
    將用戶加入部門

    POST /api/units/<secure_code>/members
    Body: { "user_id": "user_secure_code" }
    """
    from ..models.user import User

    unit = ResourceGateway.get_by(
        OrganizationalUnit,
        secure_code=secure_code,
        is_deleted=False
    )

    if not unit:
        return jsonify({'error': _('組織單位不存在')}), 404

    data = request.get_json()
    if not data or not data.get('user_id'):
        return jsonify({'error': _('請提供用戶 ID')}), 400

    # 需要動態 data['user_id'] 參數，無法使用 ResourceGateway
    user = User.query.filter(  # nosemgrep: beakplatform-direct-model-query-in-api
        User.secure_code == data['user_id'],
        User.org_secure_code == current_user.org_secure_code,
        User.is_deleted == False
    ).first()

    if not user:
        return jsonify({'error': _('用戶不存在')}), 404

    # PERM-01 層界（PF-145 階段三之二）：部門是雇傭結構，成員僅限 EMPLOYEE。
    # 候選清單 API 本來就只列 EMPLOYEE，這裡把 POST 端也補齊，擋直接打 API 的跨層寫入
    if user.user_type != UserType.EMPLOYEE:
        return jsonify({'error': _('只有企業成員帳號可加入部門')}), 400

    try:
        user.primary_unit_secure_code = secure_code
        _ensure_dept_membership(user, unit, current_user.email)
        db.session.commit()

        logger.info(f"User {user.email} added to unit {unit.code} by {current_user.email}")

        return jsonify({
            'message': _('已將 %(user)s 加入 %(unit)s', user=user.display_name, unit=unit.name),
            'user': {
                'id': user.secure_code,
                'display_name': user.display_name,
                'employee_id': user.employee_id
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to add member to unit: {e}")
        return jsonify({'error': _('加入部門失敗')}), 500


@units_bp.route('/<secure_code>/members/<user_secure_code>', methods=['DELETE'])
@admin_required
def remove_member_from_unit(secure_code: str, user_secure_code: str):
    """
    將用戶從部門移除（設為無部門）

    DELETE /api/units/<secure_code>/members/<user_secure_code>
    """
    from ..models.user import User

    unit = ResourceGateway.get_by(
        OrganizationalUnit,
        secure_code=secure_code,
        is_deleted=False
    )

    if not unit:
        return jsonify({'error': _('組織單位不存在')}), 404

    # 需要多重動態參數比較，無法使用 ResourceGateway
    user = User.query.filter(  # nosemgrep: beakplatform-direct-model-query-in-api
        User.secure_code == user_secure_code,
        User.org_secure_code == current_user.org_secure_code,
        User.primary_unit_secure_code == secure_code,
        User.is_deleted == False
    ).first()

    if not user:
        return jsonify({'error': _('用戶不存在或不屬於此部門')}), 404

    try:
        user.primary_unit_secure_code = None
        _remove_dept_membership(user, unit)
        db.session.commit()

        logger.info(f"User {user.email} removed from unit {unit.code} by {current_user.email}")

        return jsonify({
            'message': _('已將 %(user)s 從 %(unit)s 移除', user=user.display_name, unit=unit.name)
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to remove member from unit: {e}")
        return jsonify({'error': _('移除成員失敗')}), 500


@units_bp.route('/<secure_code>/manager', methods=['POST'])
@admin_required
def set_unit_manager(secure_code: str):
    """
    設定部門主管（拖入主管區）

    POST /api/units/<secure_code>/manager
    Body: { "user_id": "user_secure_code" }

    會：
    1. 將用戶加入部門（如果尚未加入）
    2. 移除原主管的 DEPT_MANAGER 角色（如果有）
    3. 賦予新主管 DEPT_MANAGER 角色
    """
    from ..models.user import User
    from ..models.associations import UserRoleAssignment

    unit = ResourceGateway.get_by(
        OrganizationalUnit,
        secure_code=secure_code,
        is_deleted=False
    )

    if not unit:
        return jsonify({'error': _('組織單位不存在')}), 404

    data = request.get_json()
    if not data or not data.get('user_id'):
        return jsonify({'error': _('請提供用戶 ID')}), 400

    user = User.query.filter(
        User.secure_code == data['user_id'],
        User.org_secure_code == current_user.org_secure_code,
        User.is_deleted == False
    ).first()

    if not user:
        return jsonify({'error': _('用戶不存在')}), 404

    # PERM-01 層界（PF-145 階段三之二）：部門主管僅限 EMPLOYEE
    if user.user_type != UserType.EMPLOYEE:
        return jsonify({'error': _('只有企業成員帳號可設為部門主管')}), 400

    # 取得 DEPT_MANAGER 角色
    dept_manager_role = Role.query.filter(
        Role.org_secure_code == current_user.org_secure_code,
        Role.code == 'DEPT_MANAGER',
        Role.is_deleted == False
    ).first()

    if not dept_manager_role:
        return jsonify({'error': _('部門主管角色不存在，請聯繫系統管理員')}), 500

    org_sc = current_user.org_secure_code
    dept_employee_role = _get_system_role(org_sc, 'DEPT_EMPLOYEE')

    try:
        # 1. 將用戶加入部門（設為主要部門）+ 成員關係與角色
        user.primary_unit_secure_code = secure_code
        _ensure_dept_membership(user, unit, current_user.email)

        # 2. 移除此部門現有主管的角色，並將前主管改回 DEPT_EMPLOYEE
        existing_manager_assignments = UserRoleAssignment.query.filter(
            UserRoleAssignment.org_secure_code == org_sc,
            UserRoleAssignment.role_secure_code == dept_manager_role.secure_code,
            UserRoleAssignment.unit_secure_code == secure_code,
            UserRoleAssignment.is_deleted == False
        ).all()

        for assignment in existing_manager_assignments:
            assignment.is_deleted = True
            assignment.deleted_at = datetime.utcnow()
            # 前主管恢復為部門員工
            if dept_employee_role:
                _ensure_role_assignment(
                    org_sc, assignment.user_secure_code,
                    dept_employee_role.secure_code, secure_code,
                    current_user.email
                )

        # 3. 新主管：移除 DEPT_EMPLOYEE，賦予 DEPT_MANAGER (互斥切換)
        if dept_employee_role:
            _revoke_role_assignment(
                org_sc, user.secure_code,
                dept_employee_role.secure_code, secure_code
            )

        new_assignment = UserRoleAssignment(
            org_secure_code=org_sc,
            user_secure_code=user.secure_code,
            role_secure_code=dept_manager_role.secure_code,
            unit_secure_code=secure_code,
            assigned_by=current_user.email
        )
        db.session.add(new_assignment)
        db.session.commit()

        logger.info(f"User {user.email} set as manager of unit {unit.code} by {current_user.email}")

        return jsonify({
            'message': _('已設定 %(user)s 為 %(unit)s 主管', user=user.display_name, unit=unit.name),
            'user': {
                'id': user.secure_code,
                'display_name': user.display_name,
                'native_name': user.native_name,
                'english_name': user.english_name,
                'employee_id': user.employee_id,
                'email': user.email
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to set unit manager: {e}")
        return jsonify({'error': _('設定主管失敗')}), 500


@units_bp.route('/<secure_code>/manager/<user_secure_code>', methods=['DELETE'])
@admin_required
def remove_unit_manager(secure_code: str, user_secure_code: str):
    """
    移除部門主管角色（從主管區移出）

    DELETE /api/units/<secure_code>/manager/<user_secure_code>

    只移除 DEPT_MANAGER 角色，不移出部門
    """
    from ..models.user import User
    from ..models.associations import UserRoleAssignment

    unit = ResourceGateway.get_by(
        OrganizationalUnit,
        secure_code=secure_code,
        is_deleted=False
    )

    if not unit:
        return jsonify({'error': _('組織單位不存在')}), 404

    user = User.query.filter(
        User.secure_code == user_secure_code,
        User.org_secure_code == current_user.org_secure_code,
        User.is_deleted == False
    ).first()

    if not user:
        return jsonify({'error': _('用戶不存在')}), 404

    # 取得 DEPT_MANAGER 角色
    dept_manager_role = Role.query.filter(
        Role.org_secure_code == current_user.org_secure_code,
        Role.code == 'DEPT_MANAGER',
        Role.is_deleted == False
    ).first()

    if not dept_manager_role:
        return jsonify({'error': _('部門主管角色不存在')}), 500

    org_sc = current_user.org_secure_code

    try:
        # 移除該用戶在此部門的主管角色
        assignment = UserRoleAssignment.query.filter(
            UserRoleAssignment.org_secure_code == org_sc,
            UserRoleAssignment.user_secure_code == user_secure_code,
            UserRoleAssignment.role_secure_code == dept_manager_role.secure_code,
            UserRoleAssignment.unit_secure_code == secure_code,
            UserRoleAssignment.is_deleted == False
        ).first()

        if assignment:
            assignment.is_deleted = True
            assignment.deleted_at = datetime.utcnow()

            # 恢復為部門員工
            dept_employee_role = _get_system_role(org_sc, 'DEPT_EMPLOYEE')
            if dept_employee_role:
                _ensure_role_assignment(
                    org_sc, user_secure_code,
                    dept_employee_role.secure_code, secure_code,
                    current_user.email
                )

            db.session.commit()

        logger.info(f"User {user.email} removed as manager of unit {unit.code} by {current_user.email}")

        return jsonify({
            'message': _('已移除 %(user)s 的 %(unit)s 主管角色', user=user.display_name, unit=unit.name)
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to remove unit manager: {e}")
        return jsonify({'error': _('移除主管角色失敗')}), 500


@units_bp.route('/<secure_code>/manager', methods=['GET'])
@admin_required
def get_unit_manager(secure_code: str):
    """
    取得部門主管

    GET /api/units/<secure_code>/manager
    """
    from ..models.user import User
    from ..models.associations import UserRoleAssignment

    unit = ResourceGateway.get_by(
        OrganizationalUnit,
        secure_code=secure_code,
        is_deleted=False
    )

    if not unit:
        return jsonify({'error': _('組織單位不存在')}), 404

    # 取得 DEPT_MANAGER 角色
    dept_manager_role = Role.query.filter(
        Role.org_secure_code == current_user.org_secure_code,
        Role.code == 'DEPT_MANAGER',
        Role.is_deleted == False
    ).first()

    if not dept_manager_role:
        return jsonify({'manager': None}), 200

    # 查找此部門的主管
    assignment = UserRoleAssignment.query.filter(
        UserRoleAssignment.org_secure_code == current_user.org_secure_code,
        UserRoleAssignment.role_secure_code == dept_manager_role.secure_code,
        UserRoleAssignment.unit_secure_code == secure_code,
        UserRoleAssignment.is_deleted == False
    ).first()

    if not assignment:
        return jsonify({'manager': None}), 200

    user = User.query.filter(
        User.secure_code == assignment.user_secure_code,
        User.is_deleted == False
    ).first()

    if not user:
        return jsonify({'manager': None}), 200

    return jsonify({
        'manager': {
            'id': user.secure_code,
            'display_name': user.display_name,
            'native_name': user.native_name,
            'english_name': user.english_name,
            'employee_id': user.employee_id,
            'email': user.email
        }
    }), 200


@units_bp.route('/<secure_code>/leadership', methods=['GET'])
@admin_required
def get_unit_leadership(secure_code: str):
    """
    取得部門管理層（主管、副主管、代理人1、代理人2）

    GET /api/units/<secure_code>/leadership
    """
    from ..models.user import User
    from ..models.associations import UserRoleAssignment

    unit = ResourceGateway.get_by(
        OrganizationalUnit,
        secure_code=secure_code,
        is_deleted=False
    )

    if not unit:
        return jsonify({'error': _('組織單位不存在')}), 404

    def get_user_by_role(role_code):
        role = Role.query.filter(
            Role.org_secure_code == current_user.org_secure_code,
            Role.code == role_code,
            Role.is_deleted == False
        ).first()
        if not role:
            return None

        assignment = UserRoleAssignment.query.filter(
            UserRoleAssignment.org_secure_code == current_user.org_secure_code,
            UserRoleAssignment.role_secure_code == role.secure_code,
            UserRoleAssignment.unit_secure_code == secure_code,
            UserRoleAssignment.is_deleted == False
        ).first()
        if not assignment:
            return None

        user = User.query.filter(
            User.secure_code == assignment.user_secure_code,
            User.is_deleted == False
        ).first()
        if not user:
            return None

        return {
            'id': user.secure_code,
            'display_name': user.display_name,
            'native_name': user.native_name,
            'english_name': user.english_name,
            'employee_id': user.employee_id,
            'email': user.email
        }

    return jsonify({
        'manager': get_user_by_role('DEPT_MANAGER'),
        'deputy': get_user_by_role('DEPT_DEPUTY'),
        'proxy1': get_user_by_role('DEPT_PROXY1'),
        'proxy2': get_user_by_role('DEPT_PROXY2')
    }), 200


@units_bp.route('/<secure_code>/leadership/<position>', methods=['POST'])
@admin_required
def set_unit_leadership(secure_code: str, position: str):
    """
    設定部門管理層

    POST /api/units/<secure_code>/leadership/<position>
    position: manager / deputy / proxy1 / proxy2
    Body: { "user_id": "user_secure_code" }
    """
    from ..models.user import User
    from ..models.associations import UserRoleAssignment

    role_map = {
        'manager': 'DEPT_MANAGER',
        'deputy': 'DEPT_DEPUTY',
        'proxy1': 'DEPT_PROXY1',
        'proxy2': 'DEPT_PROXY2'
    }

    if position not in role_map:
        return jsonify({'error': _('無效的職位類型')}), 400

    unit = ResourceGateway.get_by(
        OrganizationalUnit,
        secure_code=secure_code,
        is_deleted=False
    )

    if not unit:
        return jsonify({'error': _('組織單位不存在')}), 404

    data = request.get_json()
    if not data or not data.get('user_id'):
        return jsonify({'error': _('請提供用戶 ID')}), 400

    user = User.query.filter(
        User.secure_code == data['user_id'],
        User.org_secure_code == current_user.org_secure_code,
        User.is_deleted == False
    ).first()

    if not user:
        return jsonify({'error': _('用戶不存在')}), 404

    # PERM-01 層界（PF-145 階段三之二）：部門管理職僅限 EMPLOYEE
    if user.user_type != UserType.EMPLOYEE:
        return jsonify({'error': _('只有企業成員帳號可擔任部門管理職')}), 400

    role_code = role_map[position]
    role = Role.query.filter(
        Role.org_secure_code == current_user.org_secure_code,
        Role.code == role_code,
        Role.is_deleted == False
    ).first()

    if not role:
        return jsonify({'error': _('%(position)s 角色不存在，請聯繫系統管理員', position=position)}), 500

    try:
        # 將用戶加入部門（如果尚未加入）
        if not user.primary_unit_secure_code:
            user.primary_unit_secure_code = secure_code

        # 移除此部門現有的此角色（如果有）
        existing = UserRoleAssignment.query.filter(
            UserRoleAssignment.org_secure_code == current_user.org_secure_code,
            UserRoleAssignment.role_secure_code == role.secure_code,
            UserRoleAssignment.unit_secure_code == secure_code,
            UserRoleAssignment.is_deleted == False
        ).all()

        for a in existing:
            a.is_deleted = True
            a.deleted_at = datetime.utcnow()

        # 賦予新角色
        new_assignment = UserRoleAssignment(
            org_secure_code=current_user.org_secure_code,
            user_secure_code=user.secure_code,
            role_secure_code=role.secure_code,
            unit_secure_code=secure_code,
            assigned_by=current_user.email
        )
        db.session.add(new_assignment)
        db.session.commit()

        position_names = {
            'manager': _('主管'),
            'deputy': _('副主管'),
            'proxy1': _('代理人(一)'),
            'proxy2': _('代理人(二)')
        }

        logger.info(f"User {user.email} set as {position} of unit {unit.code} by {current_user.email}")

        return jsonify({
            'message': _('已設定 %(user)s 為 %(unit)s %(position)s', user=user.display_name, unit=unit.name, position=position_names[position]),
            'user': {
                'id': user.secure_code,
                'display_name': user.display_name,
                'native_name': user.native_name,
                'english_name': user.english_name,
                'employee_id': user.employee_id,
                'email': user.email
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to set unit leadership: {e}")
        return jsonify({'error': _('設定失敗')}), 500


@units_bp.route('/<secure_code>/leadership/<position>', methods=['DELETE'])
@admin_required
def remove_unit_leadership(secure_code: str, position: str):
    """
    移除部門管理層

    DELETE /api/units/<secure_code>/leadership/<position>
    position: manager / deputy / proxy1 / proxy2
    """
    from ..models.associations import UserRoleAssignment

    role_map = {
        'manager': 'DEPT_MANAGER',
        'deputy': 'DEPT_DEPUTY',
        'proxy1': 'DEPT_PROXY1',
        'proxy2': 'DEPT_PROXY2'
    }

    if position not in role_map:
        return jsonify({'error': _('無效的職位類型')}), 400

    unit = ResourceGateway.get_by(
        OrganizationalUnit,
        secure_code=secure_code,
        is_deleted=False
    )

    if not unit:
        return jsonify({'error': _('組織單位不存在')}), 404

    role_code = role_map[position]
    role = Role.query.filter(
        Role.org_secure_code == current_user.org_secure_code,
        Role.code == role_code,
        Role.is_deleted == False
    ).first()

    if not role:
        return jsonify({'error': _('%(position)s 角色不存在', position=position)}), 500

    try:
        # 移除此部門的此角色
        existing = UserRoleAssignment.query.filter(
            UserRoleAssignment.org_secure_code == current_user.org_secure_code,
            UserRoleAssignment.role_secure_code == role.secure_code,
            UserRoleAssignment.unit_secure_code == secure_code,
            UserRoleAssignment.is_deleted == False
        ).all()

        for a in existing:
            a.is_deleted = True
            a.deleted_at = datetime.utcnow()

        db.session.commit()

        position_names = {
            'manager': _('主管'),
            'deputy': _('副主管'),
            'proxy1': _('代理人(一)'),
            'proxy2': _('代理人(二)')
        }

        logger.info(f"Removed {position} from unit {unit.code} by {current_user.email}")

        return jsonify({
            'message': _('已移除 %(unit)s %(position)s', unit=unit.name, position=position_names[position])
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to remove unit leadership: {e}")
        return jsonify({'error': _('移除失敗')}), 500


# =====================================================
# 跨部門/社群成員 API
# =====================================================

@units_bp.route('/<secure_code>/cross-members', methods=['GET'])
@login_required
def get_cross_members(secure_code: str):
    """
    取得跨部門/社群成員列表

    GET /api/units/<secure_code>/cross-members
    Query params:
        - type: DOTTED / MEMBER (篩選成員類型)

    Admin 或 團長/副團長 可存取
    """
    if not _is_group_leader(current_user, secure_code):
        return jsonify({'error': _('無權限存取此社群')}), 403

    # _is_group_leader 已做授權，不需 ResourceGateway 二次 permission check
    unit = ResourceGateway.get_by(
        OrganizationalUnit,
        secure_code=secure_code,
        is_deleted=False,
        check_permission=False
    )

    if not unit:
        return jsonify({'error': _('組織單位不存在')}), 404

    membership_type = request.args.get('type')

    # 查詢跨部門成員（過濾已刪除/停用帳號 DATA-01）
    query = UserUnitMembership.query.join(  # nosemgrep: beakplatform-direct-model-query-in-api
        User, UserUnitMembership.user_secure_code == User.secure_code
    ).filter(
        UserUnitMembership.org_secure_code == current_user.org_secure_code,
        UserUnitMembership.unit_secure_code == secure_code,
        UserUnitMembership.is_deleted == False,
        User.is_deleted == False,
        User.is_active == True
    )

    # 只顯示 DOTTED（跨部門）和 MEMBER（社群）成員
    if membership_type:
        query = query.filter(UserUnitMembership.membership_type == membership_type)
    else:
        # 預設顯示 DOTTED 和 MEMBER
        query = query.filter(UserUnitMembership.membership_type.in_([
            MembershipType.DOTTED,
            MembershipType.MEMBER
        ]))

    memberships = query.all()

    return jsonify({
        'cross_members': [m.to_dict() for m in memberships]
    }), 200


@units_bp.route('/<secure_code>/cross-members', methods=['POST'])
@login_required
def add_cross_member(secure_code: str):
    """
    新增跨部門/社群成員

    POST /api/units/<secure_code>/cross-members
    Body: {
        "user_id": "user_secure_code",
        "membership_type": "DOTTED" or "MEMBER",
        "role_type": "MANAGER" / "DEPUTY" / "PROXY1" / "PROXY2" / "MEMBER" (optional),
        "start_date": "2024-01-01" (optional),
        "end_date": "2024-12-31" (optional),
        "notes": "備註" (optional)
    }

    Admin 或 團長/副團長 可存取
    """
    if not _is_group_leader(current_user, secure_code):
        return jsonify({'error': _('無權限管理此社群成員')}), 403

    from datetime import date

    unit = ResourceGateway.get_by(
        OrganizationalUnit,
        secure_code=secure_code,
        is_deleted=False,
        check_permission=False
    )

    if not unit:
        return jsonify({'error': _('組織單位不存在')}), 404

    data = request.get_json()
    if not data or not data.get('user_id'):
        return jsonify({'error': _('請提供用戶 ID')}), 400

    # 驗證用戶
    user = User.query.filter(  # nosemgrep: beakplatform-direct-model-query-in-api
        User.secure_code == data['user_id'],
        User.org_secure_code == current_user.org_secure_code,
        User.is_deleted == False
    ).first()

    if not user:
        return jsonify({'error': _('用戶不存在')}), 404

    # EXTERNAL 用戶不可加入企業樹群組（僅限 GROUP 類型）
    if unit.unit_type == UnitType.GROUP:
        from ..models.user import UserType
        if user.user_type == UserType.EXTERNAL and not _is_in_external_tree(unit):
            return jsonify({'error': _('外部人員不可加入企業群組')}), 400

    # 取得成員類型（部門用 DOTTED，社群用 MEMBER）
    if unit.is_department:
        membership_type = MembershipType.DOTTED
    else:
        membership_type = data.get('membership_type', MembershipType.MEMBER)

    # 驗證成員類型
    if membership_type not in [MembershipType.DOTTED, MembershipType.MEMBER]:
        return jsonify({'error': _('無效的成員類型')}), 400

    # 檢查是否已存在相同關係（包含已刪除的，因為唯一約束不考慮 is_deleted）
    existing = UserUnitMembership.query.filter(  # nosemgrep: beakplatform-direct-model-query-in-api
        UserUnitMembership.org_secure_code == current_user.org_secure_code,
        UserUnitMembership.user_secure_code == data['user_id'],
        UserUnitMembership.unit_secure_code == secure_code,
        UserUnitMembership.membership_type == membership_type
    ).first()

    if existing:
        if not existing.is_deleted:
            return jsonify({'error': _('該用戶已是此單位的成員')}), 400

        # 恢復已刪除的記錄
        try:
            existing.is_deleted = False
            existing.deleted_at = None
            existing.role_type = data.get('role_type', MembershipRole.MEMBER)
            existing.start_date = date.fromisoformat(data['start_date']) if data.get('start_date') else date.today()
            existing.end_date = date.fromisoformat(data['end_date']) if data.get('end_date') else None
            existing.notes = data.get('notes')
            db.session.commit()

            logger.info(
                f"Cross member restored: {user.email} -> {unit.code} "
                f"({membership_type}) by {current_user.email}"
            )

            return jsonify({
                'message': _('已將 %(user)s 加入 %(unit)s', user=user.display_name, unit=unit.name),
                'membership': existing.to_dict()
            }), 201
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to restore cross member: {e}")
            return jsonify({'error': _('新增失敗')}), 500

    try:
        # 處理日期
        start_date = None
        end_date = None
        if data.get('start_date'):
            start_date = date.fromisoformat(data['start_date'])
        if data.get('end_date'):
            end_date = date.fromisoformat(data['end_date'])

        membership = UserUnitMembership(
            org_secure_code=current_user.org_secure_code,
            user_secure_code=data['user_id'],
            unit_secure_code=secure_code,
            membership_type=membership_type,
            role_type=data.get('role_type', MembershipRole.MEMBER),
            start_date=start_date,
            end_date=end_date,
            notes=data.get('notes')
        )
        db.session.add(membership)
        db.session.commit()

        logger.info(
            f"Cross member added: {user.email} -> {unit.code} "
            f"({membership_type}) by {current_user.email}"
        )

        return jsonify({
            'message': _('已將 %(user)s 加入 %(unit)s', user=user.display_name, unit=unit.name),
            'membership': membership.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to add cross member: {e}")
        return jsonify({'error': _('新增失敗')}), 500


@units_bp.route('/<secure_code>/cross-members/<membership_secure_code>', methods=['PUT'])
@login_required
def update_cross_member(secure_code: str, membership_secure_code: str):
    """
    更新跨部門/社群成員關係

    PUT /api/units/<secure_code>/cross-members/<membership_secure_code>
    Body: {
        "role_type": "MANAGER" / "DEPUTY" / "PROXY1" / "PROXY2" / "MEMBER",
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "notes": "備註"
    }

    Admin 或 團長/副團長 可存取
    """
    if not _is_group_leader(current_user, secure_code):
        return jsonify({'error': _('無權限管理此社群成員')}), 403

    from datetime import date

    unit = ResourceGateway.get_by(
        OrganizationalUnit,
        secure_code=secure_code,
        is_deleted=False,
        check_permission=False
    )

    if not unit:
        return jsonify({'error': _('組織單位不存在')}), 404

    membership = UserUnitMembership.query.filter(  # nosemgrep: beakplatform-direct-model-query-in-api
        UserUnitMembership.org_secure_code == current_user.org_secure_code,
        UserUnitMembership.secure_code == membership_secure_code,
        UserUnitMembership.unit_secure_code == secure_code,
        UserUnitMembership.is_deleted == False
    ).first()

    if not membership:
        return jsonify({'error': _('成員關係不存在')}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': _('請提供更新資料')}), 400

    try:
        if 'role_type' in data:
            membership.role_type = data['role_type']
        if 'start_date' in data:
            membership.start_date = date.fromisoformat(data['start_date']) if data['start_date'] else None
        if 'end_date' in data:
            membership.end_date = date.fromisoformat(data['end_date']) if data['end_date'] else None
        if 'notes' in data:
            membership.notes = data['notes']

        db.session.commit()

        logger.info(
            f"Cross membership updated: {membership_secure_code} by {current_user.email}"
        )

        return jsonify({
            'message': _('更新成功'),
            'membership': membership.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update cross member: {e}")
        return jsonify({'error': _('更新失敗')}), 500


@units_bp.route('/<secure_code>/cross-members/<membership_secure_code>', methods=['DELETE'])
@login_required
def remove_cross_member(secure_code: str, membership_secure_code: str):
    """
    移除跨部門/社群成員關係

    DELETE /api/units/<secure_code>/cross-members/<membership_secure_code>

    Admin 或 團長/副團長 可存取
    """
    if not _is_group_leader(current_user, secure_code):
        return jsonify({'error': _('無權限管理此社群成員')}), 403

    unit = ResourceGateway.get_by(
        OrganizationalUnit,
        secure_code=secure_code,
        is_deleted=False,
        check_permission=False
    )

    if not unit:
        return jsonify({'error': _('組織單位不存在')}), 404

    membership = UserUnitMembership.query.filter(  # nosemgrep: beakplatform-direct-model-query-in-api
        UserUnitMembership.org_secure_code == current_user.org_secure_code,
        UserUnitMembership.secure_code == membership_secure_code,
        UserUnitMembership.unit_secure_code == secure_code,
        UserUnitMembership.is_deleted == False
    ).first()

    if not membership:
        return jsonify({'error': _('成員關係不存在')}), 404

    try:
        membership.is_deleted = True
        membership.deleted_at = datetime.utcnow()
        db.session.commit()

        logger.info(
            f"Cross membership removed: {membership_secure_code} by {current_user.email}"
        )

        return jsonify({
            'message': _('已移除成員關係')
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to remove cross member: {e}")
        return jsonify({'error': _('移除失敗')}), 500


@units_bp.route('/cross-members/by-user/<user_secure_code>', methods=['GET'])
@admin_required
def get_user_cross_memberships(user_secure_code: str):
    """
    取得用戶的所有跨部門/社群關係

    GET /api/units/cross-members/by-user/<user_secure_code>

    返回該用戶所有的跨部門/社群成員關係
    """
    # 驗證用戶
    user = User.query.filter(  # nosemgrep: beakplatform-direct-model-query-in-api
        User.secure_code == user_secure_code,
        User.org_secure_code == current_user.org_secure_code,
        User.is_deleted == False
    ).first()

    if not user:
        return jsonify({'error': _('用戶不存在')}), 404

    # 查詢用戶的所有跨部門關係
    memberships = UserUnitMembership.query.filter(  # nosemgrep: beakplatform-direct-model-query-in-api
        UserUnitMembership.org_secure_code == current_user.org_secure_code,
        UserUnitMembership.user_secure_code == user_secure_code,
        UserUnitMembership.is_deleted == False
    ).all()

    return jsonify({
        'user': {
            'id': user.secure_code,
            'display_name': user.display_name,
            'employee_id': user.employee_id
        },
        'memberships': [m.to_dict() for m in memberships]
    }), 200


@units_bp.route('/group-member-candidates', methods=['GET'])
@login_required
def list_group_member_candidates():
    """
    取得社群成員候選人列表 (供團長搜尋用戶以加入社群)

    GET /api/units/group-member-candidates?per_page=1000

    Admin 回傳全部帳號，團長 (MANAGER/DEPUTY) 回傳同企業帳號。
    非 admin 且非任何社群的團長 → 403。
    """
    from ..models.user import UserType

    if not _is_admin(current_user):
        managed_scs = _get_managed_group_scs(current_user)
        if not managed_scs:
            return jsonify({'error': _('無權限')}), 403

    per_page = request.args.get('per_page', 100, type=int)
    per_page = min(per_page, 1000)

    users = User.query.filter(  # nosemgrep: beakplatform-direct-model-query-in-api
        User.org_secure_code == current_user.org_secure_code,
        User.is_deleted == False,
        User.is_active == True,
        User.user_type != UserType.SYSTEM_ADMIN,
    ).order_by(User.display_name).limit(per_page).all()

    return jsonify({
        'users': [
            {
                'id': u.secure_code,
                'display_name': u.display_name,
                'native_name': u.native_name,
                'english_name': u.english_name,
                'employee_id': u.employee_id,
                'email': u.email,
                'user_type': u.user_type,
            }
            for u in users
        ]
    }), 200
