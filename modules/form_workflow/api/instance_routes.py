"""
FormWorkflow Module - Instance & Pending Task API Routes
表單實例與待簽核任務 API

提供表單實例查詢、待簽核任務列表與簽核操作。
"""
import secrets
from datetime import datetime
from flask import jsonify, request

from app import csrf, db
from app.security.decorators import module_access_required
from app.platform.auth import current_user, has_permission, require_permission
from app.platform.data import get_current_org

from . import api_bp
from ..services.task_authorizer import can_act_on_task, build_actor
from flask_babel import gettext as _


# =============================================================================
# 表單實例 API
# =============================================================================

@api_bp.route('/instances')
@module_access_required('form_workflow')
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
@module_access_required('form_workflow')
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
@module_access_required('form_workflow')
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

    user_code = current_user.secure_code
    actor = build_actor(user_code, org.secure_code)
    result = []
    for task in tasks:
        # 檢查當前用戶是否為指定簽核人
        if not can_act_on_task(task, user_code, org.secure_code, actor):
            continue

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
@module_access_required('form_workflow')
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

    # 檢查當前用戶是否為指定簽核人
    if not can_act_on_task(task, current_user.secure_code, org.secure_code):
        return jsonify({'success': False, 'error': _('您不是此任務的指定簽核人')}), 403

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
@csrf.exempt
@module_access_required('form_workflow')
@require_permission('form_workflow.form.approve')
def approve_task(secure_code):
    """簽核任務"""
    from ..models import FwNodeExecutionQueue, FwApprovalRecord
    from ..services.workflow_engine import WorkflowEngine

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

    # 檢查當前用戶是否為指定簽核人
    task_result_data = (task.result or {}).get('data', {})
    if not can_act_on_task(task, current_user.secure_code, org.secure_code):
        return jsonify({'success': False, 'error': _('您不是此任務的指定簽核人')}), 403

    data = request.get_json() or {}
    selected_path = data.get('selected_path')
    comment = data.get('comment', '')

    # 驗證簽核意見最少字數
    min_comment_length = task_result_data.get('min_comment_length', 0)
    if min_comment_length > 0 and len(comment.strip()) < min_comment_length:
        return jsonify({'success': False, 'error': _('簽核意見至少需要 %(count)s 字', count=min_comment_length)}), 400

    # 建立簽核記錄
    approval_record = FwApprovalRecord(
        secure_code=secrets.token_urlsafe(16),
        org_secure_code=org.secure_code,
        workflow_instance_secure_code=task.workflow_instance_secure_code,
        form_instance_secure_code=task.form_instance_secure_code,
        node_id=task.node_id,
        node_name=task.node_name,
        node_queue_secure_code=task.secure_code,
        approver_secure_code=current_user.secure_code,
        approver_name=current_user.display_name or current_user.username,
        action='approved',
        comment=comment,
        acted_at=datetime.utcnow(),
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
        'message': _('簽核完成')
    })
