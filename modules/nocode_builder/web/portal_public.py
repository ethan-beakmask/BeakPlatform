"""
NoCode Builder - Public Portal Route
公開子系統入口路由

/public/portal/<path_id> -- 透過 lookup 表解析 path_id，導向公開 portal 頁面
不需登入，使用 @public_route 標記
"""
import logging

from flask import Blueprint, render_template, abort

from app.security.decorators import public_route
from app.security.resource_gateway import ResourceGateway

logger = logging.getLogger(__name__)

public_portal_bp = Blueprint(
    'nocode_public_portal',
    __name__,
    url_prefix='/public/portal',
    template_folder='../templates',
)


@public_portal_bp.route('/<path_id>')
@public_route
def portal_entry(path_id):
    """
    公開 Portal 入口

    1. 透過 path_id 查 lookup_items (PUBLIC_PORTAL_PATHS)
    2. path_id 不存在或 inactive → 404
    3. 找到對應子系統 → render 佔位頁面
    """
    from ..services.portal_path_service import get_by_path_id
    from ..models.sub_system import DcSubSystem

    item = get_by_path_id(path_id)
    if not item or not item.is_active:
        abort(404)

    sub_system_sc = item.value_str
    if not sub_system_sc:
        abort(404)

    # 查子系統基本資訊 (不經 ResourceGateway 租戶過濾，因為是公開路由無 tenant context)
    ss = DcSubSystem.query.filter_by(
        secure_code=sub_system_sc,
        is_deleted=False,
    ).first()
    if not ss or ss.status != 'published':
        abort(404)

    return render_template(
        'modules/nocode_builder/portal_public.html',
        sub_system_name=ss.name,
        sub_system_description=ss.description or '',
        sub_system_icon=ss.icon or '',
        path_id=path_id,
    )
