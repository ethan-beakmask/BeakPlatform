"""
FormWorkflow Module - API Routes
表單流程模組 API

提供表單和工作流的 RESTful API。
路由按業務分群拆至子模組：
- template_routes: 表單模板 CRUD 與批次操作 (9 routes)
- workflow_routes: 工作流模板 CRUD、樹系查詢與批次操作 (12 routes)
- instance_routes: 表單實例與待簽核任務 (5 routes)
"""
from flask import Blueprint, jsonify

from app.security.decorators import public_route, module_access_required
from app.platform.auth import require_permission
from app.platform.data import get_current_org

# 建立 API Blueprint
api_bp = Blueprint(
    'form_workflow_api',
    __name__,
    url_prefix='/api/form-workflow'
)


# =============================================================================
# 模組資訊
# =============================================================================

@api_bp.route('/info')
@public_route
def module_info():
    """取得模組資訊（公開）"""
    from .. import MODULE_INFO
    return jsonify({
        'success': True,
        'data': {
            'name': MODULE_INFO['name'],
            'display_name': MODULE_INFO['display_name'],
            'version': MODULE_INFO['version'],
            'description': MODULE_INFO['description'],
        }
    })


@api_bp.route('/permissions')
@public_route
def module_permissions():
    """取得模組權限列表（公開）"""
    from app.platform.auth import get_module_permissions
    perms = get_module_permissions('form_workflow')
    return jsonify({
        'success': True,
        'data': {'permissions': perms}
    })


# =============================================================================
# 統計 API
# =============================================================================

@api_bp.route('/stats')
@module_access_required('form_workflow')
@require_permission('form_workflow.template.view')
def get_stats():
    """取得模組統計資訊"""
    from ..models import FwFormTemplate, FwWorkflowTemplate, FwFormInstance

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    org_code = org.secure_code

    template_count = FwFormTemplate.query.filter_by(
        org_secure_code=org_code, is_deleted=False
    ).count()

    workflow_count = FwWorkflowTemplate.query.filter_by(
        org_secure_code=org_code, is_deleted=False
    ).count()

    instance_count = FwFormInstance.query.filter_by(
        org_secure_code=org_code, is_deleted=False
    ).count()

    pending_count = FwFormInstance.query.filter_by(
        org_secure_code=org_code, is_deleted=False, status='PENDING'
    ).count()

    return jsonify({
        'success': True,
        'data': {
            'form_templates': template_count,
            'workflow_templates': workflow_count,
            'form_instances': instance_count,
            'pending_instances': pending_count,
        }
    })


# =============================================================================
# 載入子路由模組（註冊 route 至 api_bp）
# =============================================================================
from . import template_routes   # noqa: E402, F401
from . import workflow_routes   # noqa: E402, F401
from . import instance_routes   # noqa: E402, F401
from . import ai_usage          # noqa: E402, F401


# =============================================================================
# 額外的 Blueprint（用於與 A6 前端相容）
# =============================================================================

# 導入 workflows API Blueprint
from .workflows import workflows_bp

# 導入 forms API Blueprint
from .forms import forms_bp

# 導入 mappings API Blueprint
from .mappings import mappings_bp

# 導入 form_center API Blueprint
from .form_center import form_center_bp

# 導入 categories API Blueprint
from .categories import categories_bp

# 導入 backgrounds API Blueprint
from .backgrounds import backgrounds_bp

# 導入 form_themes API Blueprint
from .form_themes import form_themes_bp

# 導入 mapping_permissions API Blueprint
from .mapping_permissions import mapping_permissions_bp

# 導入外部發動閘道 API Blueprint（平台 API Key HMAC 認證）
from .external_trigger import external_trigger_bp

# 導出所有 Blueprint（供模組載入器使用）
# field_specs_bp 已移至 spec_formulate 模組
additional_blueprints = [workflows_bp, forms_bp, mappings_bp, form_center_bp, categories_bp, backgrounds_bp, form_themes_bp, mapping_permissions_bp, external_trigger_bp]
