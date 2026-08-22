"""
FormWorkflow Module - Form Themes API
表單風格主題管理 API
"""
from flask import Blueprint, jsonify, request, Response

from app.security.decorators import module_access_required, public_route
from app.platform.auth import require_any_permission
from app.platform.data import get_current_org
from app import db, csrf
from flask_babel import gettext as _

# 建立 API Blueprint
form_themes_bp = Blueprint(
    'form_workflow_form_themes',
    __name__,
    url_prefix='/api/form-workflow/form-themes'
)


# =============================================================================
# GET — 列出主題
# =============================================================================

@form_themes_bp.route('', methods=['GET'])
@module_access_required('form_workflow')
def list_themes():
    """
    列出可用主題

    Query Parameters:
        all: 若為 1，包含停用的主題（管理用）
    """
    from ..models import FwFormTheme

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    show_all = request.args.get('all') == '1'

    query = FwFormTheme.query.filter_by(is_deleted=False)

    if not show_all:
        query = query.filter_by(is_active=True)

    # 系統主題（org_secure_code IS NULL）+ 該企業自訂主題
    query = query.filter(
        db.or_(
            FwFormTheme.org_secure_code.is_(None),
            FwFormTheme.org_secure_code == org.secure_code
        )
    )

    themes = query.order_by(FwFormTheme.sort_order, FwFormTheme.name).all()

    return jsonify({
        'success': True,
        'data': [t.to_dict() for t in themes]
    })


# =============================================================================
# GET — 取得單一主題（含 CSS）
# =============================================================================

@form_themes_bp.route('/<secure_code>', methods=['GET'])
@module_access_required('form_workflow')
def get_theme(secure_code):
    """取得單一主題詳情（含 CSS 內容）"""
    from ..models import FwFormTheme

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    theme = FwFormTheme.query.filter_by(
        secure_code=secure_code,
        is_deleted=False
    ).first()

    if not theme:
        return jsonify({'success': False, 'message': _('主題不存在')}), 404

    if theme.org_secure_code and theme.org_secure_code != org.secure_code:
        return jsonify({'success': False, 'message': _('無權查看此主題')}), 403

    return jsonify({'success': True, 'data': theme.to_dict_with_css()})


# =============================================================================
# POST — 建立主題
# =============================================================================

@form_themes_bp.route('', methods=['POST'])
@csrf.exempt
@module_access_required('form_workflow')
@require_any_permission('form_workflow.admin', 'form_workflow.template.manage', 'form_workflow.workflow.manage')
def create_theme():
    """
    建立新主題

    Body:
        name: 主題識別碼（英文，必填）
        display_name: 顯示名稱（必填）
        description: 描述
        css_content: CSS 內容
    """
    from ..models import FwFormTheme

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    data = request.get_json() or {}

    if not data.get('name'):
        return jsonify({'success': False, 'message': _('主題識別碼為必填')}), 400
    if not data.get('display_name'):
        return jsonify({'success': False, 'message': _('顯示名稱為必填')}), 400

    # 識別碼只允許英文、數字、連字號
    import re
    if not re.match(r'^[a-z][a-z0-9-]*$', data['name']):
        return jsonify({'success': False, 'message': _('識別碼只允許小寫英文、數字、連字號，且以英文開頭')}), 400

    # 檢查名稱是否重複
    dup = FwFormTheme.query.filter_by(
        name=data['name'],
        is_deleted=False
    ).filter(
        db.or_(
            FwFormTheme.org_secure_code.is_(None),
            FwFormTheme.org_secure_code == org.secure_code
        )
    ).first()

    if dup:
        return jsonify({'success': False, 'message': _('主題識別碼「%(name)s」已存在', name=data["name"])}), 400

    try:
        theme = FwFormTheme(
            org_secure_code=org.secure_code,
            name=data['name'],
            display_name=data['display_name'],
            description=data.get('description', ''),
            css_content=data.get('css_content', ''),
            is_system=False,
            sort_order=data.get('sort_order', 50),
        )

        db.session.add(theme)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': _('主題建立成功'),
            'data': theme.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': _('建立失敗: %(error)s', error=str(e))}), 500


# =============================================================================
# PUT — 更新主題
# =============================================================================

@form_themes_bp.route('/<secure_code>', methods=['PUT'])
@csrf.exempt
@module_access_required('form_workflow')
@require_any_permission('form_workflow.admin', 'form_workflow.template.manage', 'form_workflow.workflow.manage')
def update_theme(secure_code):
    """更新主題"""
    from ..models import FwFormTheme

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    theme = FwFormTheme.query.filter_by(
        secure_code=secure_code,
        is_deleted=False
    ).first()

    if not theme:
        return jsonify({'success': False, 'message': _('主題不存在')}), 404

    if theme.org_secure_code and theme.org_secure_code != org.secure_code:
        return jsonify({'success': False, 'message': _('無權修改此主題')}), 403

    data = request.get_json() or {}

    try:
        if 'display_name' in data:
            theme.display_name = data['display_name']
        if 'description' in data:
            theme.description = data['description']
        if 'css_content' in data:
            theme.css_content = data['css_content']
        if 'is_active' in data:
            theme.is_active = data['is_active']
        if 'sort_order' in data:
            theme.sort_order = data['sort_order']

        db.session.commit()

        return jsonify({
            'success': True,
            'message': _('主題更新成功'),
            'data': theme.to_dict()
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': _('更新失敗: %(error)s', error=str(e))}), 500


# =============================================================================
# DELETE — 刪除主題
# =============================================================================

@form_themes_bp.route('/<secure_code>', methods=['DELETE'])
@csrf.exempt
@module_access_required('form_workflow')
@require_any_permission('form_workflow.admin', 'form_workflow.template.manage', 'form_workflow.workflow.manage')
def delete_theme(secure_code):
    """刪除主題（軟刪除）"""
    from ..models import FwFormTheme

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    theme = FwFormTheme.query.filter_by(
        secure_code=secure_code,
        is_deleted=False
    ).first()

    if not theme:
        return jsonify({'success': False, 'message': _('主題不存在')}), 404

    if theme.is_system:
        return jsonify({'success': False, 'message': _('系統內建主題無法刪除')}), 403

    if theme.org_secure_code and theme.org_secure_code != org.secure_code:
        return jsonify({'success': False, 'message': _('無權刪除此主題')}), 403

    try:
        theme.is_deleted = True
        db.session.commit()

        return jsonify({
            'success': True,
            'message': _('主題已刪除')
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': _('刪除失敗: %(error)s', error=str(e))}), 500


# =============================================================================
# GET — CSS Bundle（所有啟用主題的 CSS 合併輸出）
# =============================================================================

@form_themes_bp.route('/bundle.css', methods=['GET'])
@public_route
def css_bundle():
    """
    輸出所有啟用主題的 CSS（合併）

    此端點為公開路由，供 <link> 標籤載入。
    回傳 Content-Type: text/css。
    """
    from ..models import FwFormTheme

    themes = FwFormTheme.query.filter_by(
        is_active=True,
        is_deleted=False
    ).order_by(FwFormTheme.sort_order, FwFormTheme.name).all()

    parts = []
    for t in themes:
        if t.css_content:
            parts.append(f'/* === Theme: {t.name} ({t.display_name}) === */\n{t.css_content}')

    css = '\n\n'.join(parts)

    return Response(css, mimetype='text/css', headers={
        'Cache-Control': 'public, max-age=300',
    })


# =============================================================================
# POST — 上傳 CSS 檔案建立主題
# =============================================================================

@form_themes_bp.route('/upload', methods=['POST'])
@csrf.exempt
@module_access_required('form_workflow')
@require_any_permission('form_workflow.admin', 'form_workflow.template.manage', 'form_workflow.workflow.manage')
def upload_theme():
    """
    上傳 CSS 檔案建立或更新主題

    Form Data:
        file: CSS 檔案
        name: 主題識別碼（新建時必填）
        display_name: 顯示名稱（新建時必填）
        secure_code: 若提供，更新現有主題的 CSS
    """
    from ..models import FwFormTheme

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    if 'file' not in request.files:
        return jsonify({'success': False, 'message': _('未上傳檔案')}), 400

    file = request.files['file']
    if not file.filename or not file.filename.endswith('.css'):
        return jsonify({'success': False, 'message': _('僅接受 .css 檔案')}), 400

    css_content = file.read().decode('utf-8')
    if not css_content.strip():
        return jsonify({'success': False, 'message': _('CSS 檔案內容為空')}), 400

    secure_code = request.form.get('secure_code')

    try:
        if secure_code:
            # 更新現有主題的 CSS
            theme = FwFormTheme.query.filter_by(
                secure_code=secure_code,
                is_deleted=False
            ).first()

            if not theme:
                return jsonify({'success': False, 'message': _('主題不存在')}), 404

            if theme.org_secure_code and theme.org_secure_code != org.secure_code:
                return jsonify({'success': False, 'message': _('無權修改此主題')}), 403

            theme.css_content = css_content
            db.session.commit()

            return jsonify({
                'success': True,
                'message': _('CSS 已更新'),
                'data': theme.to_dict()
            })
        else:
            # 新建主題
            name = request.form.get('name', '')
            display_name = request.form.get('display_name', '')

            if not name or not display_name:
                return jsonify({'success': False, 'message': _('新建主題需提供識別碼和顯示名稱')}), 400

            import re
            if not re.match(r'^[a-z][a-z0-9-]*$', name):
                return jsonify({'success': False, 'message': _('識別碼只允許小寫英文、數字、連字號')}), 400

            theme = FwFormTheme(
                org_secure_code=org.secure_code,
                name=name,
                display_name=display_name,
                css_content=css_content,
                is_system=False,
                sort_order=50,
            )

            db.session.add(theme)
            db.session.commit()

            return jsonify({
                'success': True,
                'message': _('主題上傳成功'),
                'data': theme.to_dict()
            }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': _('處理失敗: %(error)s', error=str(e))}), 500
