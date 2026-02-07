"""
BeakPlatform Job Family Management Web Routes
職系管理網頁路由

職系代表職涯發展軌道：
- 管理職 (MANAGER): 帶人主管軌道
- 專業職 (PROFESSIONAL): 不帶人的專業軌道
  - 業務職、客服職、行政職、工程技術職
"""
from datetime import datetime
from flask import Blueprint, render_template, abort, request, flash, redirect, url_for
from flask_login import current_user

from ..security.decorators import admin_required
from ..security.resource_gateway import ResourceGateway
from ..models.job_family import JobFamily, JobFamilyType
from .. import db

job_families_bp = Blueprint('job_families', __name__)


@job_families_bp.route('/')
@admin_required
def list_job_families():
    """職系列表頁面"""
    result = ResourceGateway.list(
        JobFamily,
        page=1,
        per_page=100,
        order_by='sort_order',
        is_deleted=False
    )

    # 建立樹狀結構
    families = result['items']
    root_families = [f for f in families if not f.parent_secure_code]

    # 為每個根職系找子職系
    for root in root_families:
        root.sub_families = [f for f in families if f.parent_secure_code == root.secure_code]

    return render_template(
        'pages/job_families/list.html',
        job_families=root_families,
        all_families=families
    )


@job_families_bp.route('/<secure_code>')
@admin_required
def view_job_family(secure_code: str):
    """查看職系詳情"""
    try:
        job_family = ResourceGateway.get(JobFamily, secure_code)
    except Exception:
        abort(404)

    return render_template('pages/job_families/view.html', job_family=job_family)


@job_families_bp.route('/create', methods=['GET', 'POST'])
@admin_required
def create_job_family():
    """建立職系頁面"""
    # 取得可作為父職系的選項 (只有根職系可作為父)
    parent_options = ResourceGateway.filter(
        JobFamily,
        is_deleted=False,
        parent_secure_code=None,
        order_by='sort_order'
    )

    if request.method == 'POST':
        code = request.form.get('code', '').strip().upper()
        name = request.form.get('name', '').strip()
        name_en = request.form.get('name_en', '').strip() or None
        family_type = request.form.get('family_type', JobFamilyType.PROFESSIONAL)
        parent_secure_code = request.form.get('parent_secure_code', '').strip() or None
        description = request.form.get('description', '').strip() or None
        sort_order_str = request.form.get('sort_order', '0').strip()

        errors = []

        if not code:
            errors.append('職系代碼為必填')
        if not name:
            errors.append('職系名稱為必填')
        if family_type not in [JobFamilyType.MANAGER, JobFamilyType.PROFESSIONAL]:
            errors.append('職系類型無效')

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
                JobFamily,
                code=code,
                is_deleted=False
            )

            if existing:
                flash(f'職系代碼 {code} 已存在', 'error')
            else:
                try:
                    job_family = JobFamily(
                        org_secure_code=current_user.org_secure_code,
                        code=code,
                        name=name,
                        name_en=name_en,
                        family_type=family_type,
                        parent_secure_code=parent_secure_code,
                        description=description,
                        sort_order=sort_order,
                        is_active=True
                    )
                    db.session.add(job_family)
                    db.session.commit()

                    flash(f'已建立職系 {name}', 'success')
                    return redirect(url_for('job_families.list_job_families'))
                except Exception as e:
                    db.session.rollback()
                    flash(f'建立失敗: {str(e)}', 'error')

    return render_template(
        'pages/job_families/create.html',
        parent_options=parent_options,
        family_types=[
            (JobFamilyType.MANAGER, '管理職 (People Manager)'),
            (JobFamilyType.PROFESSIONAL, '專業職 (Individual Contributor)')
        ]
    )


@job_families_bp.route('/<secure_code>/edit', methods=['GET', 'POST'])
@admin_required
def edit_job_family(secure_code: str):
    """編輯職系頁面"""
    try:
        job_family = ResourceGateway.get(JobFamily, secure_code)
    except Exception:
        abort(404)

    # 取得可作為父職系的選項 (排除自己)
    all_root_families = ResourceGateway.filter(
        JobFamily,
        is_deleted=False,
        parent_secure_code=None,
        order_by='sort_order'
    )
    parent_options = [f for f in all_root_families if f.secure_code != secure_code]

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        name_en = request.form.get('name_en', '').strip() or None
        family_type = request.form.get('family_type', JobFamilyType.PROFESSIONAL)
        parent_secure_code = request.form.get('parent_secure_code', '').strip() or None
        description = request.form.get('description', '').strip() or None
        sort_order_str = request.form.get('sort_order', '0').strip()
        is_active = request.form.get('is_active') == 'true'

        errors = []

        if not name:
            errors.append('職系名稱為必填')

        sort_order = 0
        try:
            sort_order = int(sort_order_str)
        except ValueError:
            errors.append('排序順序須為整數')

        # 不能設自己為父
        if parent_secure_code == secure_code:
            errors.append('不能將自己設為父職系')

        if errors:
            for err in errors:
                flash(err, 'error')
        else:
            try:
                job_family.name = name
                job_family.name_en = name_en
                job_family.family_type = family_type
                job_family.parent_secure_code = parent_secure_code
                job_family.description = description
                job_family.sort_order = sort_order
                job_family.is_active = is_active

                db.session.commit()
                flash('已更新職系', 'success')
                return redirect(url_for('job_families.view_job_family', secure_code=secure_code))
            except Exception as e:
                db.session.rollback()
                flash(f'更新失敗: {str(e)}', 'error')

    return render_template(
        'pages/job_families/edit.html',
        job_family=job_family,
        parent_options=parent_options,
        family_types=[
            (JobFamilyType.MANAGER, '管理職 (People Manager)'),
            (JobFamilyType.PROFESSIONAL, '專業職 (Individual Contributor)')
        ]
    )


@job_families_bp.route('/<secure_code>/delete', methods=['POST'])
@admin_required
def delete_job_family(secure_code: str):
    """刪除職系"""
    try:
        job_family = ResourceGateway.get(JobFamily, secure_code)
    except Exception:
        abort(404)

    # 系統預設不可刪除
    if job_family.is_system_default:
        flash('系統預設職系不可刪除', 'error')
        return redirect(url_for('job_families.edit_job_family', secure_code=secure_code))

    # 檢查是否有子職系
    children = ResourceGateway.count(
        JobFamily,
        parent_secure_code=secure_code,
        is_deleted=False
    )
    if children > 0:
        flash(f'此職系有 {children} 個子職系，請先刪除子職系', 'error')
        return redirect(url_for('job_families.edit_job_family', secure_code=secure_code))

    # 檢查是否有職稱使用此職系
    cascade_delete = request.form.get('cascade_delete') == 'true'
    active_titles = [t for t in job_family.job_titles if not t.is_deleted] if job_family.job_titles else []

    if active_titles and not cascade_delete:
        # 尚未確認連動刪除，顯示確認訊息
        flash(f'此職系有 {len(active_titles)} 個職稱使用中，請確認是否連同職稱一併刪除', 'warning')
        return redirect(url_for('job_families.edit_job_family', secure_code=secure_code, confirm_cascade=len(active_titles)))

    try:
        # 連動刪除職稱
        if active_titles and cascade_delete:
            for title in active_titles:
                title.is_deleted = True
                title.deleted_at = datetime.utcnow()

        job_family.is_deleted = True
        job_family.deleted_at = datetime.utcnow()
        db.session.commit()

        if active_titles and cascade_delete:
            flash(f'已刪除職系 {job_family.name} 及 {len(active_titles)} 個職稱', 'success')
        else:
            flash(f'已刪除職系 {job_family.name}', 'success')
        return redirect(url_for('job_families.list_job_families'))
    except Exception as e:
        db.session.rollback()
        flash(f'刪除失敗: {str(e)}', 'error')
        return redirect(url_for('job_families.edit_job_family', secure_code=secure_code))
