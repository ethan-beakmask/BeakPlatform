"""
FormWorkflow Module - API Routes
表單流程模組 API

提供表單和工作流的 RESTful API。
"""
from flask import Blueprint, jsonify, request

from app.security.decorators import public_route
from app.platform.auth import (
    current_user,
    has_permission,
    require_permission,
    get_user_permissions,
)
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
# 表單模板 API
# =============================================================================

@api_bp.route('/templates')
@require_permission('form_workflow.template.view')
def list_templates():
    """取得表單模板列表"""
    from ..models import FwFormTemplate
    from app import db

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    templates = FwFormTemplate.query.filter_by(
        org_secure_code=org.secure_code,
        is_deleted=False,
        is_active=True
    ).order_by(FwFormTemplate.updated_at.desc()).all()

    return jsonify({
        'success': True,
        'data': {
            'templates': [t.to_dict(include_schema=False) for t in templates]
        }
    })


@api_bp.route('/templates/<secure_code>')
@require_permission('form_workflow.template.view')
def get_template(secure_code):
    """取得單一表單模板"""
    from ..models import FwFormTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    template = FwFormTemplate.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not template:
        return jsonify({'success': False, 'error': 'Template not found'}), 404

    return jsonify({
        'success': True,
        'data': template.to_dict(include_schema=True)
    })


# =============================================================================
# 工作流模板 API
# =============================================================================

@api_bp.route('/workflows')
@require_permission('form_workflow.workflow.view')
def list_workflows():
    """取得工作流模板列表"""
    from ..models import FwWorkflowTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    workflows = FwWorkflowTemplate.query.filter_by(
        org_secure_code=org.secure_code,
        is_deleted=False,
        is_active=True
    ).order_by(FwWorkflowTemplate.updated_at.desc()).all()

    return jsonify({
        'success': True,
        'data': {
            'workflows': [w.to_dict(include_graph=False) for w in workflows]
        }
    })


@api_bp.route('/workflows/<secure_code>')
@require_permission('form_workflow.workflow.view')
def get_workflow(secure_code):
    """取得單一工作流模板"""
    from ..models import FwWorkflowTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    workflow = FwWorkflowTemplate.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not workflow:
        return jsonify({'success': False, 'error': 'Workflow not found'}), 404

    return jsonify({
        'success': True,
        'data': workflow.to_dict(include_graph=True)
    })


# =============================================================================
# 表單實例 API
# =============================================================================

@api_bp.route('/instances')
@require_permission('form_workflow.form.view')
def list_instances():
    """取得表單實例列表（自己的）"""
    from ..models import FwFormInstance

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    # 只查看自己的表單，除非有 view_all 權限
    query = FwFormInstance.query.filter_by(
        org_secure_code=org.secure_code,
        is_deleted=False
    )

    if not has_permission('form_workflow.form.view_all'):
        query = query.filter_by(applicant_secure_code=current_user.secure_code)

    instances = query.order_by(FwFormInstance.created_at.desc()).limit(100).all()

    return jsonify({
        'success': True,
        'data': {
            'instances': [i.to_dict(include_form_data=False) for i in instances]
        }
    })


@api_bp.route('/instances/<secure_code>')
@require_permission('form_workflow.form.view')
def get_instance(secure_code):
    """取得單一表單實例"""
    from ..models import FwFormInstance

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    instance = FwFormInstance.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not instance:
        return jsonify({'success': False, 'error': 'Instance not found'}), 404

    # 檢查權限：只能查看自己的表單，除非有 view_all 權限
    if (instance.applicant_secure_code != current_user.secure_code and
        not has_permission('form_workflow.form.view_all')):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    return jsonify({
        'success': True,
        'data': instance.to_dict(include_form_data=True)
    })


# =============================================================================
# 統計 API
# =============================================================================

@api_bp.route('/stats')
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
