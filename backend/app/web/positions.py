"""
BeakMask Employee Position Management Web Routes
員工職位管理網頁路由

員工職位記錄：
- 員工的職稱指派
- 所屬部門
- 直屬主管關係 (最重要！決定簽核流程)
"""
from datetime import datetime, date
from flask import Blueprint, render_template, abort, request, flash, redirect, url_for
from flask_login import current_user

from ..security.decorators import admin_required
from ..security.resource_gateway import ResourceGateway
from ..models.employee_position import EmployeePosition, PositionType
from ..models.job_title import JobTitle
from ..models.organizational_unit import OrganizationalUnit
from ..models.user import User
from .. import db

positions_bp = Blueprint('positions', __name__)


@positions_bp.route('/')
@admin_required
def list_positions():
    """職位列表頁面"""
    result = ResourceGateway.list(
        EmployeePosition,
        page=1,
        per_page=100,
        order_by='-created_at'
    )

    return render_template(
        'pages/positions/list.html',
        positions=result['items'],
        pagination=result
    )


@positions_bp.route('/<secure_code>')
@admin_required
def view_position(secure_code: str):
    """查看職位詳情"""
    try:
        position = ResourceGateway.get(EmployeePosition, secure_code)
    except Exception:
        abort(404)

    return render_template('pages/positions/view.html', position=position)


@positions_bp.route('/create', methods=['GET', 'POST'])
@admin_required
def create_position():
    """建立職位頁面"""
    # 取得選項
    users = ResourceGateway.filter(
        User,
        is_deleted=False,
        is_active=True,
        order_by='display_name'
    )

    job_titles = ResourceGateway.filter(
        JobTitle,
        is_deleted=False,
        is_active=True,
        order_by='sort_order'
    )

    units = ResourceGateway.filter(
        OrganizationalUnit,
        is_deleted=False,
        is_active=True,
        order_by='sort_order'
    )

    position_types = [
        (PositionType.PRIMARY, '主要職位'),
        (PositionType.CONCURRENT, '兼任'),
        (PositionType.ACTING, '代理'),
        (PositionType.TEMPORARY, '臨時'),
    ]

    if request.method == 'POST':
        user_secure_code = request.form.get('user_secure_code', '').strip()
        job_title_secure_code = request.form.get('job_title_secure_code', '').strip()
        unit_secure_code = request.form.get('unit_secure_code', '').strip()
        position_type = request.form.get('position_type', PositionType.PRIMARY)
        is_unit_head = request.form.get('is_unit_head') == 'true'
        direct_manager_secure_code = request.form.get('direct_manager_secure_code', '').strip() or None
        effective_from_str = request.form.get('effective_from', '').strip()
        effective_until_str = request.form.get('effective_until', '').strip()
        remarks = request.form.get('remarks', '').strip() or None

        errors = []

        if not user_secure_code:
            errors.append('請選擇員工')
        if not job_title_secure_code:
            errors.append('請選擇職稱')
        if not unit_secure_code:
            errors.append('請選擇部門')

        effective_from = date.today()
        if effective_from_str:
            try:
                effective_from = datetime.strptime(effective_from_str, '%Y-%m-%d').date()
            except ValueError:
                errors.append('生效日期格式錯誤')

        effective_until = None
        if effective_until_str:
            try:
                effective_until = datetime.strptime(effective_until_str, '%Y-%m-%d').date()
            except ValueError:
                errors.append('失效日期格式錯誤')

        if errors:
            for err in errors:
                flash(err, 'error')
        else:
            try:
                position = EmployeePosition(
                    org_secure_code=current_user.org_secure_code,
                    user_secure_code=user_secure_code,
                    job_title_secure_code=job_title_secure_code,
                    unit_secure_code=unit_secure_code,
                    position_type=position_type,
                    is_unit_head=is_unit_head,
                    direct_manager_secure_code=direct_manager_secure_code,
                    effective_from=effective_from,
                    effective_until=effective_until,
                    remarks=remarks,
                    assigned_by=current_user.display_name,
                    is_active=True
                )
                db.session.add(position)
                db.session.commit()

                flash('已建立職位指派', 'success')
                return redirect(url_for('positions.list_positions'))
            except Exception as e:
                db.session.rollback()
                flash(f'建立失敗: {str(e)}', 'error')

    return render_template(
        'pages/positions/create.html',
        users=users,
        job_titles=job_titles,
        units=units,
        position_types=position_types
    )


@positions_bp.route('/<secure_code>/edit', methods=['GET', 'POST'])
@admin_required
def edit_position(secure_code: str):
    """編輯職位頁面"""
    try:
        position = ResourceGateway.get(EmployeePosition, secure_code)
    except Exception:
        abort(404)

    users = ResourceGateway.filter(
        User,
        is_deleted=False,
        is_active=True,
        order_by='display_name'
    )

    job_titles = ResourceGateway.filter(
        JobTitle,
        is_deleted=False,
        is_active=True,
        order_by='sort_order'
    )

    units = ResourceGateway.filter(
        OrganizationalUnit,
        is_deleted=False,
        is_active=True,
        order_by='sort_order'
    )

    position_types = [
        (PositionType.PRIMARY, '主要職位'),
        (PositionType.CONCURRENT, '兼任'),
        (PositionType.ACTING, '代理'),
        (PositionType.TEMPORARY, '臨時'),
    ]

    if request.method == 'POST':
        job_title_secure_code = request.form.get('job_title_secure_code', '').strip()
        unit_secure_code = request.form.get('unit_secure_code', '').strip()
        position_type = request.form.get('position_type', PositionType.PRIMARY)
        is_unit_head = request.form.get('is_unit_head') == 'true'
        direct_manager_secure_code = request.form.get('direct_manager_secure_code', '').strip() or None
        effective_from_str = request.form.get('effective_from', '').strip()
        effective_until_str = request.form.get('effective_until', '').strip()
        remarks = request.form.get('remarks', '').strip() or None
        is_active = request.form.get('is_active') == 'true'

        errors = []

        effective_from = position.effective_from
        if effective_from_str:
            try:
                effective_from = datetime.strptime(effective_from_str, '%Y-%m-%d').date()
            except ValueError:
                errors.append('生效日期格式錯誤')

        effective_until = None
        if effective_until_str:
            try:
                effective_until = datetime.strptime(effective_until_str, '%Y-%m-%d').date()
            except ValueError:
                errors.append('失效日期格式錯誤')

        if errors:
            for err in errors:
                flash(err, 'error')
        else:
            try:
                position.job_title_secure_code = job_title_secure_code
                position.unit_secure_code = unit_secure_code
                position.position_type = position_type
                position.is_unit_head = is_unit_head
                position.direct_manager_secure_code = direct_manager_secure_code
                position.effective_from = effective_from
                position.effective_until = effective_until
                position.remarks = remarks
                position.is_active = is_active

                db.session.commit()
                flash('已更新職位', 'success')
                return redirect(url_for('positions.view_position', secure_code=secure_code))
            except Exception as e:
                db.session.rollback()
                flash(f'更新失敗: {str(e)}', 'error')

    return render_template(
        'pages/positions/edit.html',
        position=position,
        users=users,
        job_titles=job_titles,
        units=units,
        position_types=position_types
    )


@positions_bp.route('/<secure_code>/delete', methods=['POST'])
@admin_required
def delete_position(secure_code: str):
    """刪除職位"""
    try:
        position = ResourceGateway.get(EmployeePosition, secure_code)
    except Exception:
        abort(404)

    try:
        position.is_deleted = True
        position.deleted_at = datetime.utcnow()
        db.session.commit()
        flash('已刪除職位指派', 'success')
        return redirect(url_for('positions.list_positions'))
    except Exception as e:
        db.session.rollback()
        flash(f'刪除失敗: {str(e)}', 'error')
        return redirect(url_for('positions.edit_position', secure_code=secure_code))
