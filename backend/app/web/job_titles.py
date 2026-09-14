"""
BeakMask Job Title Management Web Routes
職稱管理網頁路由

職稱 = 職等 + 職系 的具體組合
例如：經理 = L500 經理級 + 管理職
"""
from datetime import datetime
from flask import Blueprint, render_template, abort, request, flash, redirect, url_for, jsonify
from flask_babel import gettext as _
from flask_login import current_user

from sqlalchemy import func
from ..security.resource_gateway import ResourceGateway
from ..models.job_title import JobTitle
from ..models.job_level import JobLevel
from ..models.job_family import JobFamily
from ..services.code_generator import get_code_generator
from .. import db

job_titles_bp = Blueprint('job_titles', __name__)


def _wants_json():
    """判斷請求是否期望 JSON 回應（AJAX 請求）"""
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json


def _title_to_tree_node(title):
    """將 JobTitle ORM 物件轉為 BeakTrellis 樹節點"""
    level_text = ''
    if title.job_level:
        level_text = f'{title.job_level.code} {title.job_level.name}'
    return {
        'id': title.secure_code,
        'label': title.name,
        'data': {
            '_isTitle': True,
            'secure_code': title.secure_code,
            'code': title.code,
            'name': title.name,
            'name_en': title.name_en or '',
            'short_name': title.short_name or '',
            'job_level_secure_code': title.job_level_secure_code,
            'job_family_secure_code': title.job_family_secure_code,
            'job_level_text': level_text,
            'is_supervisor': title.is_supervisor,
            'is_active': title.is_active,
            'is_system_default': title.is_system_default,
            'description': title.description or '',
            'sort_order': title.sort_order
        },
        'children': []
    }


def _family_tree_node(family, children_nodes):
    """將 JobFamily 包裝為群組節點（不可編輯）"""
    return {
        'id': 'family_' + family.secure_code,
        'label': family.name,
        'expanded': True,
        'data': {
            '_isFamily': True,
            'code': family.code,
            'name_en': family.name_en or '',
            'family_type': family.family_type,
        },
        'children': children_nodes
    }


@job_titles_bp.route('/')
def list_job_titles():
    """職稱列表頁面 - BeakTrellis 樹狀格線"""
    # 取得所有啟用職系（建樹用）
    all_families = ResourceGateway.filter(
        JobFamily,
        is_deleted=False,
        is_active=True,
        order_by='sort_order'
    )

    # 取得所有職稱（含停用，不含已刪除）
    all_titles = ResourceGateway.filter(
        JobTitle,
        is_deleted=False,
        order_by='sort_order'
    )

    # 取得所有啟用職等（Modal 下拉選單用）
    all_levels = ResourceGateway.filter(
        JobLevel,
        is_deleted=False,
        is_active=True,
        order_by='-level_order'
    )

    # ---- 建構樹狀結構 ----
    family_map = {f.secure_code: f for f in all_families}
    root_families = [f for f in all_families if not f.parent_secure_code]
    sub_by_parent = {}
    for f in all_families:
        if f.parent_secure_code:
            sub_by_parent.setdefault(f.parent_secure_code, []).append(f)

    # 職稱按職系分組
    titles_by_family = {}
    unassigned = []
    for t in all_titles:
        if t.job_family_secure_code in family_map:
            titles_by_family.setdefault(t.job_family_secure_code, []).append(t)
        else:
            unassigned.append(t)

    tree_data = []
    for root in root_families:
        subs = sub_by_parent.get(root.secure_code, [])
        if subs:
            # 根職系有子職系：子職系各自掛職稱
            sub_nodes = []
            for sub in subs:
                sub_titles = titles_by_family.get(sub.secure_code, [])
                sub_nodes.append(_family_tree_node(sub, [_title_to_tree_node(t) for t in sub_titles]))
            tree_data.append(_family_tree_node(root, sub_nodes))
        else:
            # 根職系本身就是葉節點：職稱直接掛底下
            root_titles = titles_by_family.get(root.secure_code, [])
            tree_data.append(_family_tree_node(root, [_title_to_tree_node(t) for t in root_titles]))

    if unassigned:
        tree_data.append({
            'id': 'family_unassigned',
            'label': '未分類',
            'expanded': True,
            'data': {'_isFamily': True, 'code': '-', 'name_en': '', 'family_type': ''},
            'children': [_title_to_tree_node(t) for t in unassigned]
        })

    # ---- 下拉選單選項 ----
    # 職系：只有葉節點可選
    parent_codes = {f.parent_secure_code for f in all_families if f.parent_secure_code}
    leaf_families = [f for f in all_families if f.secure_code not in parent_codes]
    family_options = [
        {'secure_code': f.secure_code, 'name': f.name, 'code': f.code}
        for f in leaf_families
    ]

    level_options = [
        {'secure_code': l.secure_code, 'name': l.name, 'code': l.code, 'level_order': l.level_order}
        for l in all_levels
    ]

    return render_template(
        'pages/job_titles/list.html',
        tree_data_json=tree_data,
        family_options_json=family_options,
        level_options_json=level_options,
        total_count=len(all_titles)
    )


@job_titles_bp.route('/<secure_code>')
def view_job_title(secure_code: str):
    """查看職稱詳情"""
    try:
        job_title = ResourceGateway.get(JobTitle, secure_code)
    except Exception:
        abort(404)

    return render_template('pages/job_titles/view.html', job_title=job_title)


@job_titles_bp.route('/create', methods=['GET', 'POST'])
def create_job_title():
    """建立職稱（支援 AJAX JSON 回應）"""
    job_levels = ResourceGateway.filter(
        JobLevel, is_deleted=False, is_active=True, order_by='-level_order'
    )
    job_families = ResourceGateway.filter(
        JobFamily, is_deleted=False, is_active=True, order_by='sort_order'
    )

    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        name = request.form.get('name', '').strip()
        name_en = request.form.get('name_en', '').strip() or None
        short_name = request.form.get('short_name', '').strip() or None
        job_level_secure_code = request.form.get('job_level_secure_code', '').strip()
        job_family_secure_code = request.form.get('job_family_secure_code', '').strip()
        is_supervisor = request.form.get('is_supervisor') == 'true'
        description = request.form.get('description', '').strip() or None
        sort_order_str = request.form.get('sort_order', '0').strip()

        errors = []

        if not name:
            errors.append(_('職稱名稱為必填'))
        if not job_level_secure_code:
            errors.append(_('請選擇職等'))
        if not job_family_secure_code:
            errors.append(_('請選擇職系'))

        # code 空白時自動產生
        if not code and name:
            generator = get_code_generator()
            def _exists(c):
                return JobTitle.query.filter(
                    func.upper(JobTitle.code) == c.upper(),
                    JobTitle.org_secure_code == current_user.org_secure_code,
                    JobTitle.is_deleted == False
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
            existing = JobTitle.query.filter(
                func.upper(JobTitle.code) == code.upper(),
                JobTitle.org_secure_code == current_user.org_secure_code,
                JobTitle.is_deleted == False
            ).first()

            if existing:
                msg = _('職稱代碼 %(code)s 已存在', code=code)
                if _wants_json():
                    return jsonify({'success': False, 'errors': [msg]}), 400
                flash(msg, 'error')
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

                    if _wants_json():
                        return jsonify({'success': True, 'message': _('已建立職稱 %(name)s', name=name)})
                    flash(_('已建立職稱 %(name)s', name=name), 'success')
                    return redirect(url_for('job_titles.list_job_titles'))
                except Exception as e:
                    db.session.rollback()
                    if _wants_json():
                        return jsonify({'success': False, 'errors': [_('建立失敗: %(error)s', error=str(e))]}), 500
                    flash(_('建立失敗: %(error)s', error=str(e)), 'error')

    return render_template(
        'pages/job_titles/create.html',
        job_levels=job_levels,
        job_families=job_families
    )


@job_titles_bp.route('/<secure_code>/edit', methods=['GET', 'POST'])
def edit_job_title(secure_code: str):
    """編輯職稱（支援 AJAX JSON 回應）"""
    try:
        job_title = ResourceGateway.get(JobTitle, secure_code)
    except Exception:
        if _wants_json():
            return jsonify({'success': False, 'errors': [_('職稱不存在')]}), 404
        abort(404)

    job_levels = ResourceGateway.filter(
        JobLevel, is_deleted=False, is_active=True, order_by='-level_order'
    )
    job_families = ResourceGateway.filter(
        JobFamily, is_deleted=False, is_active=True, order_by='sort_order'
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
            errors.append(_('職稱名稱為必填'))
        if not job_level_secure_code:
            errors.append(_('請選擇職等'))
        if not job_family_secure_code:
            errors.append(_('請選擇職系'))

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
                if _wants_json():
                    return jsonify({'success': True, 'message': _('已更新職稱')})
                flash(_('已更新職稱'), 'success')
                return redirect(url_for('job_titles.view_job_title', secure_code=secure_code))
            except Exception as e:
                db.session.rollback()
                if _wants_json():
                    return jsonify({'success': False, 'errors': [_('更新失敗: %(error)s', error=str(e))]}), 500
                flash(_('更新失敗: %(error)s', error=str(e)), 'error')

    return render_template(
        'pages/job_titles/edit.html',
        job_title=job_title,
        job_levels=job_levels,
        job_families=job_families
    )


@job_titles_bp.route('/<secure_code>/delete', methods=['POST'])
def delete_job_title(secure_code: str):
    """刪除職稱（支援 AJAX JSON 回應）"""
    try:
        job_title = ResourceGateway.get(JobTitle, secure_code)
    except Exception:
        if _wants_json():
            return jsonify({'success': False, 'errors': [_('職稱不存在')]}), 404
        abort(404)

    if job_title.is_system_default:
        msg = _('系統預設職稱不可刪除')
        if _wants_json():
            return jsonify({'success': False, 'errors': [msg]}), 400
        flash(msg, 'error')
        return redirect(url_for('job_titles.edit_job_title', secure_code=secure_code))

    # 檢查是否有企業成員使用此職稱
    if job_title.employees:
        active_employees = [e for e in job_title.employees if not e.is_deleted]
        if active_employees:
            msg = _('此職稱有 %(count)s 位企業成員使用中，請先移除關聯', count=len(active_employees))
            if _wants_json():
                return jsonify({'success': False, 'errors': [msg]}), 400
            flash(msg, 'error')
            return redirect(url_for('job_titles.edit_job_title', secure_code=secure_code))

    try:
        job_title.is_deleted = True
        job_title.deleted_at = datetime.utcnow()
        db.session.commit()

        msg = _('已刪除職稱 %(name)s', name=job_title.name)
        if _wants_json():
            return jsonify({'success': True, 'message': msg})
        flash(msg, 'success')
        return redirect(url_for('job_titles.list_job_titles'))
    except Exception as e:
        db.session.rollback()
        if _wants_json():
            return jsonify({'success': False, 'errors': [_('刪除失敗: %(error)s', error=str(e))]}), 500
        flash(_('刪除失敗: %(error)s', error=str(e)), 'error')
        return redirect(url_for('job_titles.edit_job_title', secure_code=secure_code))
