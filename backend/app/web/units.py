"""
BeakPlatform Organizational Units Web Routes
組織單位 (部門/群組) 網頁路由
"""
from flask import Blueprint, render_template, abort, request, flash, redirect, url_for
from flask_login import current_user

from ..security.decorators import admin_required
from ..security.resource_gateway import ResourceGateway
from ..models import OrganizationalUnit, UnitType, Role, RoleType, ScopeType
from .. import db

units_bp = Blueprint('units', __name__)


@units_bp.route('/')
@admin_required
def list_units():
    """組織單位列表頁面"""
    unit_type = request.args.get('type', 'all')

    filters = {'is_deleted': False}
    if unit_type == 'department':
        filters['unit_type'] = UnitType.DEPARTMENT
    elif unit_type == 'group':
        filters['unit_type'] = UnitType.GROUP

    result = ResourceGateway.list(
        OrganizationalUnit,
        order_by='sort_order',
        per_page=100,
        **filters
    )
    units = result['items']

    # 建立樹狀結構
    root_units = [u for u in units if u.parent_secure_code is None]

    return render_template(
        'pages/units/list.html',
        units=units,
        root_units=root_units,
        current_type=unit_type,
        UnitType=UnitType
    )


@units_bp.route('/departments')
@admin_required
def list_departments():
    """部門列表 (便捷路由)"""
    return redirect(url_for('units.list_units', type='department'))


@units_bp.route('/groups')
@admin_required
def list_groups():
    """群組列表 (便捷路由)"""
    return redirect(url_for('units.list_units', type='group'))


@units_bp.route('/<secure_code>')
@admin_required
def view_unit(secure_code: str):
    """查看組織單位詳情"""
    unit = ResourceGateway.get(OrganizationalUnit, secure_code, raise_on_not_found=False)
    if not unit:
        abort(404)
    return render_template(
        'pages/units/view.html',
        unit=unit,
        UnitType=UnitType
    )


@units_bp.route('/create', methods=['GET', 'POST'])
@admin_required
def create_unit():
    """建立組織單位頁面"""
    unit_type = request.args.get('type', UnitType.DEPARTMENT)
    if request.method == 'POST':
        unit_type = request.form.get('unit_type', UnitType.DEPARTMENT)

    # 取得可用的父層單位
    result = ResourceGateway.list(
        OrganizationalUnit,
        is_deleted=False,
        unit_type=unit_type,
        order_by='full_path',
        per_page=100
    )
    parent_units = result['items']

    if request.method == 'POST':
        code = request.form.get('code', '').strip().upper()
        name = request.form.get('name', '').strip()
        parent_id = request.form.get('parent_id', '').strip() or None
        description = request.form.get('description', '').strip() or None
        sort_order = int(request.form.get('sort_order', 0) or 0)

        if not code or not name:
            flash('代碼和名稱為必填', 'error')
        else:
            # 檢查代碼是否重複
            existing = OrganizationalUnit.query.filter(
                OrganizationalUnit.org_secure_code == current_user.org_secure_code,
                OrganizationalUnit.code == code,
                OrganizationalUnit.is_deleted == False
            ).first()

            if existing:
                flash(f'代碼 {code} 已存在', 'error')
            else:
                try:
                    unit = OrganizationalUnit(
                        org_secure_code=current_user.org_secure_code,
                        unit_type=unit_type,
                        code=code,
                        name=name,
                        description=description,
                        parent_secure_code=parent_id,
                        sort_order=sort_order,
                        is_active=True
                    )
                    unit.update_full_path()
                    db.session.add(unit)

                    # 建立成員角色
                    role_code = f'{code}_MEMBER'
                    scope = ScopeType.DEPARTMENT if unit_type == UnitType.DEPARTMENT else ScopeType.GROUP
                    member_role = Role(
                        org_secure_code=current_user.org_secure_code,
                        role_type=RoleType.ROLE,
                        scope_type=scope,
                        code=role_code,
                        name=f'{name} 成員',
                        description=f'{name} 的成員角色',
                        is_manager=False,
                        is_system_role=False,
                        is_active=True
                    )
                    member_role.update_full_path()
                    db.session.add(member_role)
                    db.session.flush()

                    unit.member_role_secure_code = member_role.secure_code
                    db.session.commit()

                    flash(f'已建立 {name}', 'success')
                    return redirect(url_for('units.list_units'))
                except Exception as e:
                    db.session.rollback()
                    flash(f'建立失敗: {str(e)}', 'error')

    return render_template(
        'pages/units/create.html',
        unit_type=unit_type,
        parent_units=parent_units,
        UnitType=UnitType
    )


@units_bp.route('/<secure_code>/edit', methods=['GET', 'POST'])
@admin_required
def edit_unit(secure_code: str):
    """編輯組織單位頁面"""
    unit = ResourceGateway.get(OrganizationalUnit, secure_code, raise_on_not_found=False)
    if not unit:
        abort(404)

    # 取得可用的父層單位 (排除自己和子單位)
    result = ResourceGateway.list(
        OrganizationalUnit,
        is_deleted=False,
        unit_type=unit.unit_type,
        order_by='full_path',
        per_page=100
    )
    all_units = result['items']

    # 取得子單位的 secure_codes
    descendant_codes = {d.secure_code for d in unit.get_descendants()}
    descendant_codes.add(unit.secure_code)  # 包含自己

    parent_units = [u for u in all_units if u.secure_code not in descendant_codes]

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        parent_id = request.form.get('parent_id', '').strip() or None
        description = request.form.get('description', '').strip() or None
        sort_order = int(request.form.get('sort_order', 0) or 0)
        is_active = request.form.get('is_active') == '1'

        if not name:
            flash('名稱為必填', 'error')
        else:
            try:
                old_name = unit.name
                unit.name = name
                unit.parent_secure_code = parent_id
                unit.description = description
                unit.sort_order = sort_order
                unit.is_active = is_active
                unit.update_full_path()

                if unit.name != old_name:
                    unit.update_children_paths()

                db.session.commit()
                flash(f'已更新 {name}', 'success')
                return redirect(url_for('units.view_unit', secure_code=secure_code))
            except Exception as e:
                db.session.rollback()
                flash(f'更新失敗: {str(e)}', 'error')

    return render_template(
        'pages/units/edit.html',
        unit=unit,
        parent_units=parent_units,
        UnitType=UnitType
    )


@units_bp.route('/<secure_code>/delete', methods=['POST'])
@admin_required
def delete_unit(secure_code: str):
    """刪除組織單位"""
    from datetime import datetime

    unit = ResourceGateway.get(OrganizationalUnit, secure_code, raise_on_not_found=False)
    if not unit:
        abort(404)

    # 檢查是否有子單位
    children = [c for c in unit.children if not c.is_deleted]
    if children:
        flash('此單位有子單位，請先刪除子單位', 'error')
        return redirect(url_for('units.edit_unit', secure_code=secure_code))

    try:
        unit.is_deleted = True
        unit.deleted_at = datetime.utcnow()
        db.session.commit()
        flash(f'已刪除 {unit.name}', 'success')
        return redirect(url_for('units.list_units'))
    except Exception as e:
        db.session.rollback()
        flash(f'刪除失敗: {str(e)}', 'error')
        return redirect(url_for('units.edit_unit', secure_code=secure_code))
