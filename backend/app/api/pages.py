"""
BeakMask Pages API
頁面管理 API
"""
from flask import Blueprint, jsonify, request
from flask_login import current_user

from ..security.decorators import login_required, admin_required
from ..security.resource_gateway import ResourceGateway
from ..services.page_permission_service import PagePermissionService
from ..models.page import Page
from .. import db

pages_bp = Blueprint('api_pages', __name__)


@pages_bp.route('', methods=['GET'])
@login_required
def list_pages():
    """
    列出用戶可存取的頁面

    Query params:
        module: str - 模組 secure_code (過濾)
        include_inactive: bool (管理員可用)
        all: bool - 是否列出所有頁面 (管理員可用)

    Returns:
        {items: [...], total: int}
    """
    module_secure_code = request.args.get('module')
    include_inactive = request.args.get('include_inactive', 'false') == 'true'
    list_all = request.args.get('all', 'false') == 'true'

    # 管理員可查看所有頁面
    if list_all and (current_user.is_org_admin or current_user.is_system_admin):
        filters = {'is_deleted': False}
        if not include_inactive:
            filters['is_active'] = True
        if module_secure_code:
            filters['module_secure_code'] = module_secure_code

        pages = ResourceGateway.filter(Page, order_by='url_path', **filters)
    else:
        # 一般用戶只能看到可存取的頁面
        pages = PagePermissionService.get_user_accessible_pages(
            current_user,
            module_secure_code=module_secure_code
        )

    return jsonify({
        'items': [p.to_dict() for p in pages],
        'total': len(pages)
    })


@pages_bp.route('/<secure_code>', methods=['GET'])
@login_required
def get_page(secure_code: str):
    """
    取得頁面詳情

    Returns:
        Page dict with access info
    """
    page = ResourceGateway.get(Page, secure_code)

    # 檢查存取權限
    access = PagePermissionService.check_page_access(current_user, secure_code)

    result = page.to_dict()
    result['access'] = access

    return jsonify(result)


@pages_bp.route('', methods=['POST'])
@admin_required
def create_page():
    """
    新增頁面

    Body:
        code: str (required)
        title: str (required)
        url_path: str (required)
        module_secure_code: str
        description: str
        page_type: str (list, detail, form, dashboard, custom)
        flask_route: str
        template: str
        required_access: str (public, authenticated, org_admin, system_admin)
        settings: dict

    Returns:
        Page dict
    """
    data = request.get_json()

    # 驗證必要欄位
    required_fields = ['code', 'title', 'url_path']
    for field in required_fields:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400

    # 檢查代碼是否已存在
    if ResourceGateway.exists(Page, code=data['code'], is_deleted=False):
        return jsonify({'error': f'Page with code "{data["code"]}" already exists'}), 400

    # 檢查 URL 是否已存在
    if ResourceGateway.exists(Page, url_path=data['url_path'], is_deleted=False):
        return jsonify({'error': f'Page with URL "{data["url_path"]}" already exists'}), 400

    # 建立頁面
    import json
    page = Page(
        org_secure_code=current_user.org_secure_code,
        code=data['code'],
        title=data['title'],
        url_path=data['url_path'],
        module_secure_code=data.get('module_secure_code'),
        description=data.get('description'),
        page_type=data.get('page_type', 'custom'),
        flask_route=data.get('flask_route'),
        template=data.get('template'),
        required_access=data.get('required_access', 'authenticated'),
        settings=json.dumps(data.get('settings')) if data.get('settings') else None,
        is_active=True,
    )

    db.session.add(page)
    db.session.commit()

    return jsonify(page.to_dict()), 201


@pages_bp.route('/<secure_code>', methods=['PUT'])
@admin_required
def update_page(secure_code: str):
    """
    更新頁面

    Body:
        title: str
        description: str
        page_type: str
        flask_route: str
        template: str
        required_access: str
        is_active: bool
        settings: dict

    Returns:
        Updated Page dict
    """
    page = ResourceGateway.get(Page, secure_code)
    data = request.get_json()

    # 允許更新的欄位
    allowed_fields = [
        'title', 'description', 'page_type',
        'flask_route', 'template', 'required_access',
        'is_active'
    ]

    for field in allowed_fields:
        if field in data:
            setattr(page, field, data[field])

    # 特殊處理 settings (JSON)
    if 'settings' in data:
        import json
        page.settings = json.dumps(data['settings']) if data['settings'] else None

    db.session.commit()

    return jsonify(page.to_dict())


@pages_bp.route('/<secure_code>', methods=['DELETE'])
@admin_required
def delete_page(secure_code: str):
    """
    刪除頁面

    Query params:
        hard: bool - 是否硬刪除 (default: false)

    Returns:
        204 No Content
    """
    page = ResourceGateway.get(Page, secure_code)
    hard_delete = request.args.get('hard', 'false') == 'true'

    if hard_delete:
        db.session.delete(page)
    else:
        from datetime import datetime
        page.is_deleted = True
        page.deleted_at = datetime.utcnow()

    db.session.commit()

    return '', 204


@pages_bp.route('/<secure_code>/access', methods=['GET'])
@login_required
def check_page_access(secure_code: str):
    """
    檢查當前用戶對頁面的存取權限

    Returns:
        {access: 'full' | 'read_only' | 'denied'}
    """
    access = PagePermissionService.check_page_access(current_user, secure_code)
    return jsonify({'access': access})


@pages_bp.route('/by-url', methods=['GET'])
@login_required
def get_page_by_url():
    """
    根據 URL 路徑取得頁面

    Query params:
        url: str (required)

    Returns:
        Page dict with access info
    """
    url_path = request.args.get('url')

    if not url_path:
        return jsonify({'error': 'url parameter is required'}), 400

    page = ResourceGateway.get_by(Page, url_path=url_path, is_deleted=False)

    if not page:
        return jsonify({'error': 'Page not found'}), 404

    # 檢查存取權限
    access = PagePermissionService.check_page_access(current_user, page.secure_code)

    result = page.to_dict()
    result['access'] = access

    return jsonify(result)
