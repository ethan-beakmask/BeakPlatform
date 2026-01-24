"""
FormWorkflow Module - API Routes
表單流程模組 API

提供表單和工作流的 RESTful API。
"""
import secrets
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

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    query = FwFormTemplate.query.filter_by(
        org_secure_code=org.secure_code,
        is_deleted=False
    )

    # 搜尋
    q = request.args.get('q', '').strip()
    if q:
        query = query.filter(
            FwFormTemplate.name.ilike(f'%{q}%') |
            FwFormTemplate.code.ilike(f'%{q}%')
        )

    templates = query.order_by(FwFormTemplate.updated_at.desc()).all()

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


@api_bp.route('/templates', methods=['POST'])
@require_permission('form_workflow.template.create')
def create_template():
    """建立表單模板"""
    from ..models import FwFormTemplate
    from app import db

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    data = request.get_json() or {}
    name = data.get('name', '').strip()

    if not name:
        return jsonify({'success': False, 'error': 'Name is required'}), 400

    # 自動產生 code
    code = data.get('code', '').strip().upper()
    if not code:
        code = f'FT{secrets.token_hex(4).upper()}'

    # 檢查 code 是否重複
    existing = FwFormTemplate.query.filter_by(
        code=code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()
    if existing:
        return jsonify({'success': False, 'error': f'Code {code} already exists'}), 400

    template = FwFormTemplate(
        secure_code=secrets.token_urlsafe(16),
        org_secure_code=org.secure_code,
        name=name,
        code=code,
        description=data.get('description', ''),
        schema=data.get('schema', {}),
        is_active=data.get('is_active', True),
        created_by=current_user.secure_code
    )

    db.session.add(template)
    db.session.commit()

    return jsonify({
        'success': True,
        'data': template.to_dict(include_schema=True),
        'message': '表單模板已建立'
    })


@api_bp.route('/templates/<secure_code>', methods=['PUT'])
@require_permission('form_workflow.template.edit')
def update_template(secure_code):
    """更新表單模板"""
    from ..models import FwFormTemplate
    from app import db

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

    data = request.get_json() or {}

    if 'name' in data:
        template.name = data['name'].strip()
    if 'description' in data:
        template.description = data['description']
    if 'schema' in data:
        template.schema = data['schema']
    if 'is_active' in data:
        template.is_active = data['is_active']

    template.updated_by = current_user.secure_code
    db.session.commit()

    return jsonify({
        'success': True,
        'data': template.to_dict(include_schema=True),
        'message': '表單模板已更新'
    })


@api_bp.route('/templates/<secure_code>', methods=['DELETE'])
@require_permission('form_workflow.template.delete')
def delete_template(secure_code):
    """刪除表單模板（軟刪除）"""
    from ..models import FwFormTemplate
    from app import db

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

    template.is_deleted = True
    template.updated_by = current_user.secure_code
    db.session.commit()

    return jsonify({
        'success': True,
        'message': '表單模板已刪除'
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

    query = FwWorkflowTemplate.query.filter_by(
        org_secure_code=org.secure_code,
        is_deleted=False
    )

    # 搜尋
    q = request.args.get('q', '').strip()
    if q:
        query = query.filter(
            FwWorkflowTemplate.name.ilike(f'%{q}%') |
            FwWorkflowTemplate.code.ilike(f'%{q}%')
        )

    workflows = query.order_by(FwWorkflowTemplate.updated_at.desc()).all()

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


@api_bp.route('/workflows', methods=['POST'])
@require_permission('form_workflow.workflow.create')
def create_workflow():
    """建立工作流模板"""
    from ..models import FwWorkflowTemplate
    from app import db

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    data = request.get_json() or {}
    name = data.get('name', '').strip()

    if not name:
        return jsonify({'success': False, 'error': 'Name is required'}), 400

    # 自動產生 code
    code = data.get('code', '').strip().upper()
    if not code:
        code = f'WF{secrets.token_hex(4).upper()}'

    # 檢查 code 是否重複
    existing = FwWorkflowTemplate.query.filter_by(
        code=code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()
    if existing:
        return jsonify({'success': False, 'error': f'Code {code} already exists'}), 400

    workflow = FwWorkflowTemplate(
        secure_code=secrets.token_urlsafe(16),
        org_secure_code=org.secure_code,
        name=name,
        code=code,
        description=data.get('description', ''),
        graph=data.get('graph', {'nodes': [], 'edges': []}),
        is_active=data.get('is_active', True),
        created_by=current_user.secure_code
    )

    db.session.add(workflow)
    db.session.commit()

    return jsonify({
        'success': True,
        'data': workflow.to_dict(include_graph=True),
        'message': '工作流模板已建立'
    })


@api_bp.route('/workflows/<secure_code>', methods=['PUT'])
@require_permission('form_workflow.workflow.edit')
def update_workflow(secure_code):
    """更新工作流模板"""
    from ..models import FwWorkflowTemplate
    from app import db

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

    data = request.get_json() or {}

    if 'name' in data:
        workflow.name = data['name'].strip()
    if 'description' in data:
        workflow.description = data['description']
    if 'graph' in data:
        workflow.graph = data['graph']
    if 'is_active' in data:
        workflow.is_active = data['is_active']

    workflow.updated_by = current_user.secure_code
    db.session.commit()

    return jsonify({
        'success': True,
        'data': workflow.to_dict(include_graph=True),
        'message': '工作流模板已更新'
    })


@api_bp.route('/workflows/<secure_code>', methods=['DELETE'])
@require_permission('form_workflow.workflow.delete')
def delete_workflow(secure_code):
    """刪除工作流模板（軟刪除）"""
    from ..models import FwWorkflowTemplate
    from app import db

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

    workflow.is_deleted = True
    workflow.updated_by = current_user.secure_code
    db.session.commit()

    return jsonify({
        'success': True,
        'message': '工作流模板已刪除'
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

    # 狀態篩選
    status = request.args.get('status')
    if status:
        query = query.filter_by(status=status)

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
# 待簽核任務 API
# =============================================================================

@api_bp.route('/pending-tasks')
@require_permission('form_workflow.form.approve')
def list_pending_tasks():
    """取得當前用戶的待簽核任務"""
    from ..models import FwNodeExecutionQueue, FwFormInstance

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    # 查詢等待簽核的節點（WAITING 狀態且類型為 Approve）
    tasks = FwNodeExecutionQueue.query.filter(
        FwNodeExecutionQueue.org_secure_code == org.secure_code,
        FwNodeExecutionQueue.status == 'WAITING',
        FwNodeExecutionQueue.node_type.in_(['Approve', 'FormAdapter'])
    ).order_by(FwNodeExecutionQueue.scheduled_at.asc()).all()

    result = []
    for task in tasks:
        # 取得關聯的表單實例資訊
        form_instance = FwFormInstance.query.filter_by(
            secure_code=task.form_instance_secure_code
        ).first() if task.form_instance_secure_code else None

        result.append({
            'queue_secure_code': task.secure_code,
            'node_id': task.node_id,
            'node_type': task.node_type,
            'node_name': task.node_name,
            'form_name': form_instance.form_name if form_instance else None,
            'serial_number': form_instance.serial_number if form_instance else None,
            'applicant_name': form_instance.applicant_name if form_instance else None,
            'submitted_at': task.scheduled_at.isoformat() if task.scheduled_at else None,
        })

    return jsonify({
        'success': True,
        'data': {
            'tasks': result
        }
    })


@api_bp.route('/pending-tasks/<secure_code>')
@require_permission('form_workflow.form.approve')
def get_pending_task(secure_code):
    """取得待簽核任務詳情"""
    from ..models import FwNodeExecutionQueue, FwFormInstance

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    task = FwNodeExecutionQueue.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code
    ).first()

    if not task:
        return jsonify({'success': False, 'error': 'Task not found'}), 404

    # 取得關聯的表單實例
    form_instance = FwFormInstance.query.filter_by(
        secure_code=task.form_instance_secure_code
    ).first() if task.form_instance_secure_code else None

    # 取得可用的路徑（從節點配置）
    node_config = task.node_config or {}
    available_paths = node_config.get('paths', [])

    return jsonify({
        'success': True,
        'data': {
            'queue_secure_code': task.secure_code,
            'node_id': task.node_id,
            'node_type': task.node_type,
            'node_name': task.node_name,
            'node_config': node_config,
            'form_data': form_instance.form_data if form_instance else {},
            'form_name': form_instance.form_name if form_instance else None,
            'serial_number': form_instance.serial_number if form_instance else None,
            'available_paths': available_paths,
        }
    })


@api_bp.route('/pending-tasks/<secure_code>/approve', methods=['POST'])
@require_permission('form_workflow.form.approve')
def approve_task(secure_code):
    """簽核任務"""
    from ..models import FwNodeExecutionQueue, FwApprovalRecord
    from ..services.workflow_engine import WorkflowEngine
    from app import db

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    task = FwNodeExecutionQueue.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        status='WAITING'
    ).first()

    if not task:
        return jsonify({'success': False, 'error': 'Task not found or already processed'}), 404

    data = request.get_json() or {}
    selected_path = data.get('selected_path')
    comment = data.get('comment', '')

    # 建立簽核記錄
    approval_record = FwApprovalRecord(
        secure_code=secrets.token_urlsafe(16),
        org_secure_code=org.secure_code,
        workflow_instance_secure_code=task.workflow_instance_secure_code,
        form_instance_secure_code=task.form_instance_secure_code,
        node_id=task.node_id,
        approver_secure_code=current_user.secure_code,
        approver_name=current_user.display_name or current_user.username,
        decision='approved',
        selected_path=selected_path,
        comment=comment
    )
    db.session.add(approval_record)

    # 更新任務狀態
    task.status = 'SUCCESS'
    task.result = {
        'decision': 'approved',
        'selected_path': selected_path,
        'comment': comment,
        'approver': current_user.secure_code
    }

    db.session.commit()

    # 觸發工作流推進
    try:
        engine = WorkflowEngine()
        engine.advance_workflow(task.workflow_instance_secure_code, task.node_id, selected_path)
    except Exception as e:
        # 記錄錯誤但不回滾簽核
        import logging
        logging.error(f'Workflow advance error: {e}')

    return jsonify({
        'success': True,
        'message': '簽核完成'
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
