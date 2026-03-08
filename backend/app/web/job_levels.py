"""
BeakMask Job Level Management Web Routes
職等管理網頁路由

URL 安全設計：
1. 使用 secure_code 而非自增 ID
2. 所有頁面經過權限檢查
3. 不可透過 URL 參數猜測存取其他資源
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from flask import Blueprint, render_template, abort, request, flash, redirect, url_for, jsonify
from flask_login import current_user

from sqlalchemy import func
from ..security.decorators import admin_required
from ..security.resource_gateway import ResourceGateway
from ..models.job_level import JobLevel
from ..models.job_family import JobFamily
from ..models.job_title import JobTitle
from ..services.code_generator import get_code_generator
from .. import db

job_levels_bp = Blueprint('job_levels', __name__)


def _wants_json():
    """判斷請求是否期望 JSON 回應（AJAX 請求）"""
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json


def _level_to_dict(level):
    """將 JobLevel 物件轉為 dict"""
    return {
        'secure_code': level.secure_code,
        'code': level.code,
        'name': level.name,
        'name_en': level.name_en or '',
        'level_order': level.level_order,
        'is_manager_level': level.is_manager_level,
        'management_scope': level.management_scope or '',
        'description': level.description or '',
        'is_active': level.is_active,
        'is_system_default': level.is_system_default
    }


@job_levels_bp.route('/')
@admin_required
def list_job_levels():
    """職等列表頁面"""
    result = ResourceGateway.list(
        JobLevel,
        page=1,
        per_page=100,  # 職等通常不多，全部顯示
        order_by='-level_order'  # 由高到低排序
    )

    levels_json = [_level_to_dict(l) for l in result['items']]

    return render_template(
        'pages/job_levels/list.html',
        job_levels=result['items'],
        levels_json=levels_json,
        pagination=result
    )


@job_levels_bp.route('/<secure_code>')
@admin_required
def view_job_level(secure_code: str):
    """查看職等詳情"""
    try:
        job_level = ResourceGateway.get(JobLevel, secure_code)
    except Exception:
        abort(404)

    return render_template('pages/job_levels/view.html', job_level=job_level)


@job_levels_bp.route('/create', methods=['GET', 'POST'])
@admin_required
def create_job_level():
    """建立職等"""
    if request.method == 'POST':
        is_ajax = _wants_json()

        code = request.form.get('code', '').strip()
        name = request.form.get('name', '').strip()
        name_en = request.form.get('name_en', '').strip() or None
        level_order_str = request.form.get('level_order', '').strip()
        approval_limit_str = request.form.get('approval_limit', '').strip()
        is_manager_level = request.form.get('is_manager_level') == 'true'
        management_scope = request.form.get('management_scope', '').strip() or None
        description = request.form.get('description', '').strip() or None

        errors = []

        if not name:
            errors.append('職等名稱為必填')
        if not level_order_str:
            errors.append('職等序號為必填')

        # 驗證 level_order
        level_order = None
        if level_order_str:
            try:
                level_order = int(level_order_str)
                if level_order < 0 or level_order > 9999:
                    errors.append('職等序號須在 0-9999 之間')
            except ValueError:
                errors.append('職等序號須為整數')

        # 驗證 approval_limit
        approval_limit = None
        if approval_limit_str:
            try:
                approval_limit = Decimal(approval_limit_str)
                if approval_limit < 0:
                    errors.append('簽核金額上限不可為負數')
            except InvalidOperation:
                errors.append('簽核金額上限格式錯誤')

        # code 空白時自動產生
        if not code and name:
            generator = get_code_generator()
            def _exists(c):
                return JobLevel.query.filter(
                    func.upper(JobLevel.code) == c.upper(),
                    JobLevel.org_secure_code == current_user.org_secure_code,
                    JobLevel.is_deleted == False
                ).first() is not None
            try:
                code = generator.generate(name, exists_checker=_exists)
            except ValueError:
                errors.append('無法自動產生代碼，請手動輸入')

        if errors:
            if is_ajax:
                return jsonify({'success': False, 'errors': errors}), 400
            for err in errors:
                flash(err, 'error')
        else:
            # 檢查代碼是否已存在 (case-insensitive)
            existing = JobLevel.query.filter(
                func.upper(JobLevel.code) == code.upper(),
                JobLevel.org_secure_code == current_user.org_secure_code,
                JobLevel.is_deleted == False
            ).first()

            if existing:
                msg = f'職等代碼 {code} 已存在'
                if is_ajax:
                    return jsonify({'success': False, 'errors': [msg]}), 400
                flash(msg, 'error')
            else:
                try:
                    job_level = JobLevel(
                        org_secure_code=current_user.org_secure_code,
                        code=code,
                        name=name,
                        name_en=name_en,
                        level_order=level_order,
                        approval_limit=approval_limit,
                        is_manager_level=is_manager_level,
                        management_scope=management_scope,
                        description=description,
                        is_active=True
                    )
                    db.session.add(job_level)
                    db.session.commit()

                    if is_ajax:
                        return jsonify({
                            'success': True,
                            'message': f'已建立職等 {name}',
                            'data': _level_to_dict(job_level)
                        })

                    flash(f'已建立職等 {name}', 'success')
                    return redirect(url_for('job_levels.list_job_levels'))
                except Exception as e:
                    db.session.rollback()
                    msg = f'建立失敗: {str(e)}'
                    if is_ajax:
                        return jsonify({'success': False, 'errors': [msg]}), 500
                    flash(msg, 'error')

    return render_template('pages/job_levels/create.html')


@job_levels_bp.route('/<secure_code>/edit', methods=['GET', 'POST'])
@admin_required
def edit_job_level(secure_code: str):
    """編輯職等"""
    try:
        job_level = ResourceGateway.get(JobLevel, secure_code)
    except Exception:
        if _wants_json():
            return jsonify({'success': False, 'errors': ['職等不存在']}), 404
        abort(404)

    if request.method == 'POST':
        is_ajax = _wants_json()

        name = request.form.get('name', '').strip()
        name_en = request.form.get('name_en', '').strip() or None
        level_order_str = request.form.get('level_order', '').strip()
        approval_limit_str = request.form.get('approval_limit', '').strip()
        is_manager_level = request.form.get('is_manager_level') == 'true'
        management_scope = request.form.get('management_scope', '').strip() or None
        description = request.form.get('description', '').strip() or None
        is_active = request.form.get('is_active') == 'true'

        errors = []

        if not name:
            errors.append('職等名稱為必填')
        if not level_order_str:
            errors.append('職等序號為必填')

        # 驗證 level_order
        level_order = None
        if level_order_str:
            try:
                level_order = int(level_order_str)
                if level_order < 0 or level_order > 9999:
                    errors.append('職等序號須在 0-9999 之間')
            except ValueError:
                errors.append('職等序號須為整數')

        # 驗證 approval_limit
        approval_limit = None
        if approval_limit_str:
            try:
                approval_limit = Decimal(approval_limit_str)
                if approval_limit < 0:
                    errors.append('簽核金額上限不可為負數')
            except InvalidOperation:
                errors.append('簽核金額上限格式錯誤')

        if errors:
            if is_ajax:
                return jsonify({'success': False, 'errors': errors}), 400
            for err in errors:
                flash(err, 'error')
        else:
            try:
                job_level.name = name
                job_level.name_en = name_en
                job_level.level_order = level_order
                job_level.approval_limit = approval_limit
                job_level.is_manager_level = is_manager_level
                job_level.management_scope = management_scope
                job_level.description = description
                job_level.is_active = is_active

                db.session.commit()

                if is_ajax:
                    return jsonify({
                        'success': True,
                        'message': '已更新職等',
                        'data': _level_to_dict(job_level)
                    })

                flash('已更新職等', 'success')
                return redirect(url_for('job_levels.view_job_level', secure_code=secure_code))
            except Exception as e:
                db.session.rollback()
                msg = f'更新失敗: {str(e)}'
                if is_ajax:
                    return jsonify({'success': False, 'errors': [msg]}), 500
                flash(msg, 'error')

    return render_template('pages/job_levels/edit.html', job_level=job_level)


@job_levels_bp.route('/<secure_code>/delete', methods=['POST'])
@admin_required
def delete_job_level(secure_code: str):
    """刪除職等"""
    is_ajax = _wants_json()

    try:
        job_level = ResourceGateway.get(JobLevel, secure_code)
    except Exception:
        if is_ajax:
            return jsonify({'success': False, 'errors': ['職等不存在']}), 404
        abort(404)

    # 系統預設不可刪除
    if job_level.is_system_default:
        msg = '系統預設職等不可刪除'
        if is_ajax:
            return jsonify({'success': False, 'errors': [msg]}), 400
        flash(msg, 'error')
        return redirect(url_for('job_levels.edit_job_level', secure_code=secure_code))

    # 檢查是否有職稱使用此職等
    if job_level.job_titles:
        active_titles = [t for t in job_level.job_titles if not t.is_deleted]
        if active_titles:
            msg = f'此職等有 {len(active_titles)} 個職稱使用中，請先移除關聯'
            if is_ajax:
                return jsonify({'success': False, 'errors': [msg]}), 400
            flash(msg, 'error')
            return redirect(url_for('job_levels.edit_job_level', secure_code=secure_code))

    try:
        level_name = job_level.name
        job_level.is_deleted = True
        job_level.deleted_at = datetime.utcnow()
        db.session.commit()

        if is_ajax:
            return jsonify({'success': True, 'message': f'已刪除職等 {level_name}'})

        flash(f'已刪除職等 {level_name}', 'success')
        return redirect(url_for('job_levels.list_job_levels'))
    except Exception as e:
        db.session.rollback()
        msg = f'刪除失敗: {str(e)}'
        if is_ajax:
            return jsonify({'success': False, 'errors': [msg]}), 500
        flash(msg, 'error')
        return redirect(url_for('job_levels.edit_job_level', secure_code=secure_code))


@job_levels_bp.route('/matrix')
@admin_required
def job_matrix():
    """職級職稱矩陣視圖"""
    # 取得所有職等 (由高到低)
    levels = ResourceGateway.filter(
        JobLevel,
        is_deleted=False,
        is_active=True,
        order_by='-level_order'
    )

    # 取得所有職系
    families = ResourceGateway.filter(
        JobFamily,
        is_deleted=False,
        is_active=True,
        order_by='sort_order'
    )

    # 找出所有「父層級」的 secure_code（有子節點的職系）
    parent_codes = {f.parent_secure_code for f in families if f.parent_secure_code}

    # 過濾：只保留葉節點（沒有子節點的職系）
    display_families = [f for f in families if f.secure_code not in parent_codes]

    # 取得所有職稱
    titles = ResourceGateway.filter(
        JobTitle,
        is_deleted=False,
        is_active=True
    )

    # 建立矩陣資料 {level_code: {family_code: [titles]}}
    matrix = {}
    for level in levels:
        matrix[level.secure_code] = {f.secure_code: [] for f in display_families}

    for title in titles:
        level_key = title.job_level_secure_code
        family_key = title.job_family_secure_code
        if level_key in matrix and family_key in matrix[level_key]:
            matrix[level_key][family_key].append(title)

    return render_template(
        'pages/job_levels/matrix.html',
        levels=levels,
        families=display_families,
        matrix=matrix
    )


@job_levels_bp.route('/matrix/update-title', methods=['POST'])
@admin_required
def update_title_position():
    """
    更新職稱的職等和職系 (矩陣拖拉用)

    Request JSON:
    {
        "title_secure_code": "xxx",
        "new_level_secure_code": "xxx",
        "new_family_secure_code": "xxx"
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': '無效的請求'}), 400

    title_code = data.get('title_secure_code')
    new_level_code = data.get('new_level_secure_code')
    new_family_code = data.get('new_family_secure_code')

    if not title_code:
        return jsonify({'success': False, 'error': '缺少職稱代碼'}), 400

    # 驗證職稱存在且屬於當前企業
    title = ResourceGateway.get_by(
        JobTitle,
        secure_code=title_code,
        is_deleted=False
    )

    if not title:
        return jsonify({'success': False, 'error': '職稱不存在'}), 404

    # 驗證新職等存在
    if new_level_code:
        new_level = ResourceGateway.get_by(
            JobLevel,
            secure_code=new_level_code,
            is_deleted=False
        )
        if not new_level:
            return jsonify({'success': False, 'error': '職等不存在'}), 404
        title.job_level_secure_code = new_level_code

        # 依據目標職等的管理職屬性，自動同步 is_supervisor
        title.is_supervisor = new_level.is_manager_level

    # 驗證新職系存在
    if new_family_code:
        new_family = ResourceGateway.get_by(
            JobFamily,
            secure_code=new_family_code,
            is_deleted=False
        )
        if not new_family:
            return jsonify({'success': False, 'error': '職系不存在'}), 404
        title.job_family_secure_code = new_family_code

    try:
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'已更新 {title.name}',
            'title': {
                'secure_code': title.secure_code,
                'name': title.name,
                'is_supervisor': title.is_supervisor,
                'job_level_secure_code': title.job_level_secure_code,
                'job_family_secure_code': title.job_family_secure_code
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
