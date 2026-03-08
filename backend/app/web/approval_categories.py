"""
BeakMask Approval Category Management Web Routes
核決權限類別管理網頁路由

路徑：/job-approval-categories/*
權限：admin_required (企業管理員)
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import current_user

from ..security.decorators import admin_required
from ..security.resource_gateway import ResourceGateway
from ..models import ApprovalCategory, JobLevelApprovalLimit, JobLevel, JobFamily, JobTitle
from .. import db

approval_categories_bp = Blueprint('approval_categories', __name__)


def _wants_json():
    """判斷請求是否期望 JSON 回應（AJAX 請求）"""
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json


@approval_categories_bp.route('/')
@admin_required
def list_categories():
    """核決權限類別列表（含核決金額矩陣）"""
    # 左面板表格：顯示所有類別（含停用）
    all_categories = ResourceGateway.filter(
        ApprovalCategory,
        is_deleted=False,
        order_by='sort_order'
    )

    # 核決金額矩陣：只顯示啟用的
    active_categories = [c for c in all_categories if c.is_active]

    # 取得所有職等
    job_levels = ResourceGateway.filter(
        JobLevel,
        is_deleted=False,
        is_active=True,
        order_by='-level_order'
    )

    # 取得所有核決上限
    all_limits = ResourceGateway.filter(
        JobLevelApprovalLimit,
        is_deleted=False
    )

    # 建立矩陣: limits_matrix[level_code][category_code] = amount
    limits_matrix = {}
    for level in job_levels:
        limits_matrix[level.secure_code] = {}
        for cat in active_categories:
            limits_matrix[level.secure_code][cat.secure_code] = 0

    for lim in all_limits:
        if lim.job_level_secure_code in limits_matrix:
            if lim.category_secure_code in limits_matrix[lim.job_level_secure_code]:
                limits_matrix[lim.job_level_secure_code][lim.category_secure_code] = int(lim.approval_limit) if lim.approval_limit else 0

    # 準備 JSON 資料給前端 Alpine.js
    categories_json = [{
        'secure_code': c.secure_code,
        'code': c.code,
        'name': c.name,
        'name_en': c.name_en or '',
        'currency': c.currency,
        'description': c.description or '',
        'sort_order': c.sort_order,
        'is_active': c.is_active,
        'is_system_default': c.is_system_default
    } for c in all_categories]

    # 準備 BeakTrellis 矩陣資料
    matrix_tree = []
    for level in job_levels:
        node_data = {
            'code': level.code,
            'name': level.name,
            'is_manager_level': level.is_manager_level,
        }
        for cat in active_categories:
            node_data[cat.secure_code] = limits_matrix[level.secure_code][cat.secure_code]
        matrix_tree.append({
            'id': level.secure_code,
            'label': f'{level.code} {level.name}',
            'data': node_data,
            'children': []
        })

    matrix_columns = [{
        'id': cat.secure_code,
        'label': f'{cat.name}({cat.currency})',
    } for cat in active_categories]

    return render_template(
        'pages/approval_categories/list.html',
        categories=active_categories,
        all_categories=all_categories,
        categories_json=categories_json,
        job_levels=job_levels,
        limits_matrix=limits_matrix,
        matrix_tree_json=matrix_tree,
        matrix_columns_json=matrix_columns
    )


@approval_categories_bp.route('/create', methods=['GET', 'POST'])
@admin_required
def create_category():
    """建立核決權限類別"""
    if request.method == 'POST':
        code = request.form.get('code', '').strip().upper()
        name = request.form.get('name', '').strip()
        name_en = request.form.get('name_en', '').strip() or None
        description = request.form.get('description', '').strip() or None
        currency = request.form.get('currency', 'TWD').strip()
        sort_order_str = request.form.get('sort_order', '0').strip()

        errors = []
        if not code:
            errors.append('類別代碼為必填')
        if not name:
            errors.append('類別名稱為必填')

        sort_order = 0
        if sort_order_str:
            try:
                sort_order = int(sort_order_str)
            except ValueError:
                errors.append('排序須為整數')

        if errors:
            if _wants_json():
                return jsonify({'success': False, 'errors': errors}), 400
            for err in errors:
                flash(err, 'error')
        else:
            # 檢查代碼是否已存在
            existing = ResourceGateway.exists(
                ApprovalCategory,
                code=code,
                is_deleted=False
            )
            if existing:
                msg = f'類別代碼 {code} 已存在'
                if _wants_json():
                    return jsonify({'success': False, 'errors': [msg]}), 409
                flash(msg, 'error')
            else:
                try:
                    category = ApprovalCategory(
                        org_secure_code=current_user.org_secure_code,
                        code=code,
                        name=name,
                        name_en=name_en,
                        description=description,
                        currency=currency,
                        sort_order=sort_order,
                        is_active=True
                    )
                    db.session.add(category)
                    db.session.commit()

                    if _wants_json():
                        return jsonify({
                            'success': True,
                            'message': f'已建立類別 {name}',
                            'category': {
                                'secure_code': category.secure_code,
                                'code': category.code,
                                'name': category.name,
                                'name_en': category.name_en or '',
                                'currency': category.currency,
                                'description': category.description or '',
                                'sort_order': category.sort_order,
                                'is_active': category.is_active,
                                'is_system_default': category.is_system_default
                            }
                        })

                    flash(f'已建立類別 {name}', 'success')
                    return redirect(url_for('approval_categories.list_categories'))
                except Exception as e:
                    db.session.rollback()
                    msg = f'建立失敗: {str(e)}'
                    if _wants_json():
                        return jsonify({'success': False, 'errors': [msg]}), 500
                    flash(msg, 'error')

    if _wants_json():
        return jsonify({'success': False, 'errors': ['無效的請求']}), 400

    return render_template('pages/approval_categories/create.html')


@approval_categories_bp.route('/<secure_code>/edit', methods=['GET', 'POST'])
@admin_required
def edit_category(secure_code: str):
    """編輯核決權限類別"""
    category = ResourceGateway.get_by(
        ApprovalCategory,
        secure_code=secure_code,
        is_deleted=False
    )
    if not category:
        if _wants_json():
            return jsonify({'success': False, 'errors': ['類別不存在']}), 404
        flash('類別不存在', 'error')
        return redirect(url_for('approval_categories.list_categories'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        name_en = request.form.get('name_en', '').strip() or None
        description = request.form.get('description', '').strip() or None
        currency = request.form.get('currency', 'TWD').strip()
        sort_order_str = request.form.get('sort_order', '0').strip()
        is_active = request.form.get('is_active') == 'true'

        errors = []
        if not name:
            errors.append('類別名稱為必填')

        sort_order = 0
        if sort_order_str:
            try:
                sort_order = int(sort_order_str)
            except ValueError:
                errors.append('排序須為整數')

        if errors:
            if _wants_json():
                return jsonify({'success': False, 'errors': errors}), 400
            for err in errors:
                flash(err, 'error')
        else:
            try:
                category.name = name
                category.name_en = name_en
                category.description = description
                category.currency = currency
                category.sort_order = sort_order
                category.is_active = is_active
                db.session.commit()

                if _wants_json():
                    return jsonify({
                        'success': True,
                        'message': '已更新類別',
                        'category': {
                            'secure_code': category.secure_code,
                            'code': category.code,
                            'name': category.name,
                            'name_en': category.name_en or '',
                            'currency': category.currency,
                            'description': category.description or '',
                            'sort_order': category.sort_order,
                            'is_active': category.is_active,
                            'is_system_default': category.is_system_default
                        }
                    })

                flash('已更新類別', 'success')
                return redirect(url_for('approval_categories.list_categories'))
            except Exception as e:
                db.session.rollback()
                msg = f'更新失敗: {str(e)}'
                if _wants_json():
                    return jsonify({'success': False, 'errors': [msg]}), 500
                flash(msg, 'error')

    if _wants_json():
        return jsonify({
            'success': True,
            'category': {
                'secure_code': category.secure_code,
                'code': category.code,
                'name': category.name,
                'name_en': category.name_en or '',
                'currency': category.currency,
                'description': category.description or '',
                'sort_order': category.sort_order,
                'is_active': category.is_active,
                'is_system_default': category.is_system_default
            }
        })

    return render_template(
        'pages/approval_categories/edit.html',
        category=category
    )


@approval_categories_bp.route('/<secure_code>/delete', methods=['POST'])
@admin_required
def delete_category(secure_code: str):
    """刪除核決權限類別"""
    category = ResourceGateway.get_by(
        ApprovalCategory,
        secure_code=secure_code,
        is_deleted=False
    )
    if not category:
        if _wants_json():
            return jsonify({'success': False, 'errors': ['類別不存在']}), 404
        flash('類別不存在', 'error')
        return redirect(url_for('approval_categories.list_categories'))

    if category.is_system_default:
        if _wants_json():
            return jsonify({'success': False, 'errors': ['系統預設類別不可刪除']}), 403
        flash('系統預設類別不可刪除', 'error')
        return redirect(url_for('approval_categories.list_categories'))

    try:
        category.is_deleted = True
        category.deleted_at = datetime.utcnow()
        db.session.commit()

        if _wants_json():
            return jsonify({'success': True, 'message': f'已刪除類別 {category.name}'})

        flash(f'已刪除類別 {category.name}', 'success')
    except Exception as e:
        db.session.rollback()
        msg = f'刪除失敗: {str(e)}'
        if _wants_json():
            return jsonify({'success': False, 'errors': [msg]}), 500
        flash(msg, 'error')

    return redirect(url_for('approval_categories.list_categories'))


@approval_categories_bp.route('/<secure_code>/limits')
@admin_required
def category_limits(secure_code: str):
    """查看/設定此類別各職等的核決上限（含職級職稱矩陣）"""
    category = ResourceGateway.get_by(
        ApprovalCategory,
        secure_code=secure_code,
        is_deleted=False
    )
    if not category:
        flash('類別不存在', 'error')
        return redirect(url_for('approval_categories.list_categories'))

    # 取得所有職等（依 level_order 降序）
    job_levels = ResourceGateway.filter(
        JobLevel,
        is_deleted=False,
        is_active=True,
        order_by='-level_order'
    )

    # 取得所有職系
    job_families = ResourceGateway.filter(
        JobFamily,
        is_deleted=False,
        is_active=True,
        order_by='sort_order'
    )

    # 取得所有職稱
    job_titles = ResourceGateway.filter(
        JobTitle,
        is_deleted=False,
        is_active=True,
        order_by='sort_order'
    )

    # 建立職稱矩陣: matrix[level_code][family_code] = [titles]
    matrix = {}
    for level in job_levels:
        matrix[level.secure_code] = {}
        for family in job_families:
            matrix[level.secure_code][family.secure_code] = []

    for title in job_titles:
        level_key = title.job_level_secure_code
        family_key = title.job_family_secure_code
        if level_key in matrix and family_key in matrix.get(level_key, {}):
            matrix[level_key][family_key].append(title)

    # 取得此類別的所有上限設定
    limits = ResourceGateway.filter(
        JobLevelApprovalLimit,
        category_secure_code=secure_code,
        is_deleted=False
    )

    # 建立 dict 方便查詢
    limits_map = {lim.job_level_secure_code: lim for lim in limits}

    return render_template(
        'pages/approval_categories/limits.html',
        category=category,
        job_levels=job_levels,
        job_families=job_families,
        matrix=matrix,
        limits_map=limits_map
    )


@approval_categories_bp.route('/<secure_code>/limits', methods=['POST'])
@admin_required
def save_category_limits(secure_code: str):
    """儲存此類別各職等的核決上限"""
    category = ResourceGateway.get_by(
        ApprovalCategory,
        secure_code=secure_code,
        is_deleted=False
    )
    if not category:
        return jsonify({'success': False, 'error': '類別不存在'}), 404

    data = request.get_json()
    if not data or 'limits' not in data:
        return jsonify({'success': False, 'error': '無效的請求'}), 400

    try:
        for item in data['limits']:
            level_code = item.get('job_level_secure_code')
            limit_str = item.get('approval_limit')

            # 解析金額（不允許無上限，空值/null 轉為 0）
            try:
                if limit_str is None or limit_str == '':
                    limit_value = Decimal('0')
                else:
                    limit_value = Decimal(str(limit_str))
                    if limit_value < 0:
                        limit_value = Decimal('0')
            except (InvalidOperation, ValueError):
                limit_value = Decimal('0')

            # 查詢或建立
            existing = ResourceGateway.get_by(
                JobLevelApprovalLimit,
                job_level_secure_code=level_code,
                category_secure_code=secure_code,
                is_deleted=False
            )

            if existing:
                existing.approval_limit = limit_value
            else:
                new_limit = JobLevelApprovalLimit(
                    org_secure_code=current_user.org_secure_code,
                    job_level_secure_code=level_code,
                    category_secure_code=secure_code,
                    approval_limit=limit_value
                )
                db.session.add(new_limit)

        db.session.commit()
        return jsonify({'success': True, 'message': '已儲存核決上限'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
