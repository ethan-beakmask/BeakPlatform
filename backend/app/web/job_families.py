"""
BeakMask Job Family Management Web Routes
職系管理網頁路由

職系代表職涯發展軌道：
- 管理職 (MANAGER): 帶人主管軌道
- 專業職 (PROFESSIONAL): 不帶人的專業軌道
  - 業務職、客服職、行政職、工程技術職
"""
from datetime import datetime
from flask import Blueprint, render_template, abort, request, flash, redirect, url_for, jsonify
from flask_babel import gettext as _
from flask_login import current_user

from sqlalchemy import func
from ..security.resource_gateway import ResourceGateway
from ..models.job_family import JobFamily, JobFamilyType
from ..services.code_generator import get_code_generator
from .. import db

job_families_bp = Blueprint('job_families', __name__)


def _wants_json():
    """判斷請求是否期望 JSON 回應（AJAX 請求）"""
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json


@job_families_bp.route('/')
def list_job_families():
    """職系列表頁面（BeakTrellis 樹狀格線）"""
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

    # 準備樹狀 JSON 資料給 BeakTrellis
    tree_data = []
    for root in root_families:
        node = {
            'id': root.secure_code,
            'label': root.name,
            'expanded': True,
            'data': {
                'secure_code': root.secure_code,
                'code': root.code,
                'name': root.name,
                'name_en': root.name_en or '',
                'family_type': root.family_type,
                'sort_order': root.sort_order,
                'is_active': root.is_active,
                'is_system_default': root.is_system_default,
                'parent_secure_code': '',
                'description': root.description or ''
            },
            'children': []
        }
        for sub in root.sub_families:
            child = {
                'id': sub.secure_code,
                'label': sub.name,
                'data': {
                    'secure_code': sub.secure_code,
                    'code': sub.code,
                    'name': sub.name,
                    'name_en': sub.name_en or '',
                    'family_type': sub.family_type,
                    'sort_order': sub.sort_order,
                    'is_active': sub.is_active,
                    'is_system_default': sub.is_system_default,
                    'parent_secure_code': root.secure_code,
                    'description': sub.description or ''
                },
                'children': []
            }
            node['children'].append(child)
        tree_data.append(node)

    # parent options 給建立/編輯 modal 用
    parent_options = [
        {'secure_code': r.secure_code, 'name': r.name, 'code': r.code}
        for r in root_families
    ]

    return render_template(
        'pages/job_families/list.html',
        job_families=root_families,
        all_families=families,
        tree_data_json=tree_data,
        parent_options_json=parent_options,
        family_types_json=[
            {'value': 'MANAGER', 'label': '管理職 (People Manager)'},
            {'value': 'PROFESSIONAL', 'label': '專業職 (Individual Contributor)'}
        ]
    )


@job_families_bp.route('/<secure_code>')
def view_job_family(secure_code: str):
    """查看職系詳情"""
    try:
        job_family = ResourceGateway.get(JobFamily, secure_code)
    except Exception:
        abort(404)

    return render_template('pages/job_families/view.html', job_family=job_family)


@job_families_bp.route('/create', methods=['GET', 'POST'])
def create_job_family():
    """建立職系（支援 AJAX JSON 回應）"""
    # 取得可作為父職系的選項 (只有根職系可作為父)
    parent_options = ResourceGateway.filter(
        JobFamily,
        is_deleted=False,
        parent_secure_code=None,
        order_by='sort_order'
    )

    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        name = request.form.get('name', '').strip()
        name_en = request.form.get('name_en', '').strip() or None
        family_type = request.form.get('family_type', JobFamilyType.PROFESSIONAL)
        parent_secure_code = request.form.get('parent_secure_code', '').strip() or None
        description = request.form.get('description', '').strip() or None
        sort_order_str = request.form.get('sort_order', '0').strip()

        errors = []

        if not name:
            errors.append(_('職系名稱為必填'))
        if family_type not in [JobFamilyType.MANAGER, JobFamilyType.PROFESSIONAL]:
            errors.append(_('職系類型無效'))

        # code 空白時自動產生
        if not code and name:
            generator = get_code_generator()
            def _exists(c):
                return JobFamily.query.filter(
                    func.upper(JobFamily.code) == c.upper(),
                    JobFamily.org_secure_code == current_user.org_secure_code,
                    JobFamily.is_deleted == False
                ).first() is not None
            try:
                code = generator.generate(name, exists_checker=_exists)
            except ValueError:
                errors.append(_('無法自動產生代碼，請手動輸入'))

        sort_order = 0
        try:
            sort_order = int(sort_order_str)
        except ValueError:
            errors.append(_('排序順序須為整數'))

        if errors:
            if _wants_json():
                return jsonify({'success': False, 'errors': errors}), 400
            for err in errors:
                flash(err, 'error')
        else:
            # 檢查代碼是否已存在 (case-insensitive)
            existing = JobFamily.query.filter(
                func.upper(JobFamily.code) == code.upper(),
                JobFamily.org_secure_code == current_user.org_secure_code,
                JobFamily.is_deleted == False
            ).first()

            if existing:
                if _wants_json():
                    return jsonify({'success': False, 'errors': [_('職系代碼 %(code)s 已存在', code=code)]}), 400
                flash(_('職系代碼 %(code)s 已存在', code=code), 'error')
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

                    if _wants_json():
                        return jsonify({'success': True, 'message': _('已建立職系 %(name)s', name=name)})
                    flash(_('已建立職系 %(name)s', name=name), 'success')
                    return redirect(url_for('job_families.list_job_families'))
                except Exception as e:
                    db.session.rollback()
                    if _wants_json():
                        return jsonify({'success': False, 'errors': [_('建立失敗: %(error)s', error=str(e))]}), 500
                    flash(_('建立失敗: %(error)s', error=str(e)), 'error')

    return render_template(
        'pages/job_families/create.html',
        parent_options=parent_options,
        family_types=[
            (JobFamilyType.MANAGER, '管理職 (People Manager)'),
            (JobFamilyType.PROFESSIONAL, '專業職 (Individual Contributor)')
        ]
    )


@job_families_bp.route('/<secure_code>/edit', methods=['GET', 'POST'])
def edit_job_family(secure_code: str):
    """編輯職系（支援 AJAX JSON 回應）"""
    try:
        job_family = ResourceGateway.get(JobFamily, secure_code)
    except Exception:
        if _wants_json():
            return jsonify({'success': False, 'errors': [_('職系不存在')]}), 404
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
            errors.append(_('職系名稱為必填'))

        sort_order = 0
        try:
            sort_order = int(sort_order_str)
        except ValueError:
            errors.append(_('排序順序須為整數'))

        # 不能設自己為父
        if parent_secure_code == secure_code:
            errors.append(_('不能將自己設為父職系'))

        if errors:
            if _wants_json():
                return jsonify({'success': False, 'errors': errors}), 400
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
                if _wants_json():
                    return jsonify({'success': True, 'message': _('已更新職系')})
                flash(_('已更新職系'), 'success')
                return redirect(url_for('job_families.view_job_family', secure_code=secure_code))
            except Exception as e:
                db.session.rollback()
                if _wants_json():
                    return jsonify({'success': False, 'errors': [_('更新失敗: %(error)s', error=str(e))]}), 500
                flash(_('更新失敗: %(error)s', error=str(e)), 'error')

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
def delete_job_family(secure_code: str):
    """刪除職系（支援 AJAX JSON 回應）"""
    try:
        job_family = ResourceGateway.get(JobFamily, secure_code)
    except Exception:
        if _wants_json():
            return jsonify({'success': False, 'errors': [_('職系不存在')]}), 404
        abort(404)

    # 系統預設不可刪除
    if job_family.is_system_default:
        if _wants_json():
            return jsonify({'success': False, 'errors': [_('系統預設職系不可刪除')]}), 400
        flash(_('系統預設職系不可刪除'), 'error')
        return redirect(url_for('job_families.edit_job_family', secure_code=secure_code))

    # 檢查是否有子職系
    children = ResourceGateway.count(
        JobFamily,
        parent_secure_code=secure_code,
        is_deleted=False
    )
    if children > 0:
        msg = _('此職系有 %(count)s 個子職系，請先刪除子職系', count=children)
        if _wants_json():
            return jsonify({'success': False, 'errors': [msg]}), 400
        flash(msg, 'error')
        return redirect(url_for('job_families.edit_job_family', secure_code=secure_code))

    # 檢查是否有職稱使用此職系
    cascade_delete = request.form.get('cascade_delete') == 'true'
    active_titles = [t for t in job_family.job_titles if not t.is_deleted] if job_family.job_titles else []

    if active_titles and not cascade_delete:
        msg = _('此職系有 %(count)s 個職稱使用中，需連同職稱一併刪除', count=len(active_titles))
        if _wants_json():
            return jsonify({
                'success': False,
                'errors': [msg],
                'confirm_cascade': True,
                'title_count': len(active_titles)
            }), 409
        flash(msg, 'warning')
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
            msg = _('已刪除職系 %(name)s 及 %(count)s 個職稱', name=job_family.name, count=len(active_titles))
        else:
            msg = _('已刪除職系 %(name)s', name=job_family.name)

        if _wants_json():
            return jsonify({'success': True, 'message': msg})
        flash(msg, 'success')
        return redirect(url_for('job_families.list_job_families'))
    except Exception as e:
        db.session.rollback()
        if _wants_json():
            return jsonify({'success': False, 'errors': [_('刪除失敗: %(error)s', error=str(e))]}), 500
        flash(_('刪除失敗: %(error)s', error=str(e)), 'error')
        return redirect(url_for('job_families.edit_job_family', secure_code=secure_code))
