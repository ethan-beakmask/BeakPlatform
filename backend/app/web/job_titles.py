"""
BeakPlatform Job Title Management Web Routes
職稱管理網頁路由

職稱 = 職等 + 職系 的具體組合
例如：經理 = L500 經理級 + 管理職
"""
from datetime import datetime
from flask import Blueprint, render_template, abort, request, flash, redirect, url_for
from flask_login import current_user

from ..security.decorators import admin_required
from ..security.resource_gateway import ResourceGateway
from ..models.job_title import JobTitle
from ..models.job_level import JobLevel
from ..models.job_family import JobFamily
from .. import db

job_titles_bp = Blueprint('job_titles', __name__)


@job_titles_bp.route('/')
@admin_required
def list_job_titles():
    """職稱列表頁面 - 按職系分組顯示"""
    # 取得所有職系 (用於分組)
    job_families = ResourceGateway.filter(
        JobFamily,
        is_deleted=False,
        is_active=True,
        order_by='sort_order'
    )

    # 找出所有「父層級」的 secure_code（有子節點的職系）
    parent_codes = {f.parent_secure_code for f in job_families if f.parent_secure_code}

    # 過濾：只保留葉節點（沒有子節點的職系）
    display_families = [f for f in job_families if f.secure_code not in parent_codes]

    # 取得所有職稱
    job_titles = ResourceGateway.filter(
        JobTitle,
        is_deleted=False,
        order_by='sort_order'
    )

    # 按職系分組
    titles_by_family = {f.secure_code: [] for f in display_families}
    # 加入「未分類」
    titles_by_family['__unassigned__'] = []

    for title in job_titles:
        family_code = title.job_family_secure_code
        if family_code in titles_by_family:
            titles_by_family[family_code].append(title)
        else:
            titles_by_family['__unassigned__'].append(title)

    return render_template(
        'pages/job_titles/list.html',
        job_families=display_families,
        titles_by_family=titles_by_family,
        total_count=len(job_titles)
    )


@job_titles_bp.route('/<secure_code>')
@admin_required
def view_job_title(secure_code: str):
    """查看職稱詳情"""
    try:
        job_title = ResourceGateway.get(JobTitle, secure_code)
    except Exception:
        abort(404)

    return render_template('pages/job_titles/view.html', job_title=job_title)


@job_titles_bp.route('/create', methods=['GET', 'POST'])
@admin_required
def create_job_title():
    """建立職稱頁面"""
    # 取得職等和職系選項
    job_levels = ResourceGateway.filter(
        JobLevel,
        is_deleted=False,
        is_active=True,
        order_by='-level_order'
    )

    job_families = ResourceGateway.filter(
        JobFamily,
        is_deleted=False,
        is_active=True,
        order_by='sort_order'
    )

    if request.method == 'POST':
        code = request.form.get('code', '').strip().upper()
        name = request.form.get('name', '').strip()
        name_en = request.form.get('name_en', '').strip() or None
        short_name = request.form.get('short_name', '').strip() or None
        job_level_secure_code = request.form.get('job_level_secure_code', '').strip()
        job_family_secure_code = request.form.get('job_family_secure_code', '').strip()
        is_supervisor = request.form.get('is_supervisor') == 'true'
        description = request.form.get('description', '').strip() or None
        sort_order_str = request.form.get('sort_order', '0').strip()

        errors = []

        if not code:
            errors.append('職稱代碼為必填')
        if not name:
            errors.append('職稱名稱為必填')
        if not job_level_secure_code:
            errors.append('請選擇職等')
        if not job_family_secure_code:
            errors.append('請選擇職系')

        sort_order = 0
        try:
            sort_order = int(sort_order_str)
        except ValueError:
            errors.append('排序順序須為整數')

        if errors:
            for err in errors:
                flash(err, 'error')
        else:
            # 檢查代碼是否已存在
            existing = ResourceGateway.exists(
                JobTitle,
                code=code,
                is_deleted=False
            )

            if existing:
                flash(f'職稱代碼 {code} 已存在', 'error')
            else:
                try:
                    job_title = JobTitle(
                        org_secure_code=current_user.org_secure_code,
                        code=code,
                        name=name,
                        name_en=name_en,
                        short_name=short_name,
                        job_level_secure_code=job_level_secure_code,
                        job_family_secure_code=job_family_secure_code,
                        is_supervisor=is_supervisor,
                        description=description,
                        sort_order=sort_order,
                        is_active=True
                    )
                    db.session.add(job_title)
                    db.session.commit()

                    flash(f'已建立職稱 {name}', 'success')
                    return redirect(url_for('job_titles.list_job_titles'))
                except Exception as e:
                    db.session.rollback()
                    flash(f'建立失敗: {str(e)}', 'error')

    return render_template(
        'pages/job_titles/create.html',
        job_levels=job_levels,
        job_families=job_families
    )


@job_titles_bp.route('/<secure_code>/edit', methods=['GET', 'POST'])
@admin_required
def edit_job_title(secure_code: str):
    """編輯職稱頁面"""
    try:
        job_title = ResourceGateway.get(JobTitle, secure_code)
    except Exception:
        abort(404)

    job_levels = ResourceGateway.filter(
        JobLevel,
        is_deleted=False,
        is_active=True,
        order_by='-level_order'
    )

    job_families = ResourceGateway.filter(
        JobFamily,
        is_deleted=False,
        is_active=True,
        order_by='sort_order'
    )

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        name_en = request.form.get('name_en', '').strip() or None
        short_name = request.form.get('short_name', '').strip() or None
        job_level_secure_code = request.form.get('job_level_secure_code', '').strip()
        job_family_secure_code = request.form.get('job_family_secure_code', '').strip()
        is_supervisor = request.form.get('is_supervisor') == 'true'
        description = request.form.get('description', '').strip() or None
        sort_order_str = request.form.get('sort_order', '0').strip()
        is_active = request.form.get('is_active') == 'true'

        errors = []

        if not name:
            errors.append('職稱名稱為必填')
        if not job_level_secure_code:
            errors.append('請選擇職等')
        if not job_family_secure_code:
            errors.append('請選擇職系')

        sort_order = 0
        try:
            sort_order = int(sort_order_str)
        except ValueError:
            errors.append('排序順序須為整數')

        if errors:
            for err in errors:
                flash(err, 'error')
        else:
            try:
                job_title.name = name
                job_title.name_en = name_en
                job_title.short_name = short_name
                job_title.job_level_secure_code = job_level_secure_code
                job_title.job_family_secure_code = job_family_secure_code
                job_title.is_supervisor = is_supervisor
                job_title.description = description
                job_title.sort_order = sort_order
                job_title.is_active = is_active

                db.session.commit()
                flash('已更新職稱', 'success')
                return redirect(url_for('job_titles.view_job_title', secure_code=secure_code))
            except Exception as e:
                db.session.rollback()
                flash(f'更新失敗: {str(e)}', 'error')

    return render_template(
        'pages/job_titles/edit.html',
        job_title=job_title,
        job_levels=job_levels,
        job_families=job_families
    )


@job_titles_bp.route('/<secure_code>/delete', methods=['POST'])
@admin_required
def delete_job_title(secure_code: str):
    """刪除職稱"""
    try:
        job_title = ResourceGateway.get(JobTitle, secure_code)
    except Exception:
        abort(404)

    if job_title.is_system_default:
        flash('系統預設職稱不可刪除', 'error')
        return redirect(url_for('job_titles.edit_job_title', secure_code=secure_code))

    # 檢查是否有員工使用此職稱
    if job_title.employees:
        active_employees = [e for e in job_title.employees if not e.is_deleted]
        if active_employees:
            flash(f'此職稱有 {len(active_employees)} 位員工使用中，請先移除關聯', 'error')
            return redirect(url_for('job_titles.edit_job_title', secure_code=secure_code))

    try:
        job_title.is_deleted = True
        job_title.deleted_at = datetime.utcnow()
        db.session.commit()
        flash(f'已刪除職稱 {job_title.name}', 'success')
        return redirect(url_for('job_titles.list_job_titles'))
    except Exception as e:
        db.session.rollback()
        flash(f'刪除失敗: {str(e)}', 'error')
        return redirect(url_for('job_titles.edit_job_title', secure_code=secure_code))
