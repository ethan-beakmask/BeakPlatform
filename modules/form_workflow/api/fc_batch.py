"""
表單中心 - 批次簽核
"""
import logging
import secrets
from datetime import datetime

from flask import jsonify, request
from flask_login import current_user

from app.security.decorators import module_access_required
from app.platform.data import get_current_org
from app import db, csrf

from .form_center import form_center_bp
from ..services.task_authorizer import can_act_on_task, build_actor
from flask_babel import gettext as _

logger = logging.getLogger(__name__)


@form_center_bp.route('/pending-tasks/batch-approve', methods=['POST'])
@csrf.exempt
@module_access_required('form_workflow', False)
def batch_approve_tasks():
    """
    批次簽核多筆待簽核任務

    前提：所有選取項目必須具有相同的 published_secure_code + node_id，
    確保簽核選項（edge/自定義決策）完全一致。
    批次模式不支援表單欄位編輯。
    """
    from ..models import FwNodeExecutionQueue, FwApprovalRecord
    from ..services.workflow_engine import WorkflowEngine

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    data = request.get_json() or {}
    queue_secure_codes = data.get('queue_secure_codes', [])
    decision = data.get('decision', 'approved')
    selected_path = data.get('selected_path')
    selected_edges = data.get('selected_edges')
    selected_option_value = data.get('selected_option_value')
    comment = data.get('comment', '')

    if not queue_secure_codes or not isinstance(queue_secure_codes, list):
        return jsonify({'success': False, 'error': _('未選取任何待簽核項目')}), 400

    if len(queue_secure_codes) > 100:
        return jsonify({'success': False, 'error': _('單次批次簽核上限 100 筆')}), 400

    user_code = current_user.secure_code
    actor = build_actor(user_code, org.secure_code)
    results = []        # 每筆處理結果
    success_count = 0
    fail_count = 0

    # 逐筆處理，每筆獨立 transaction 避免單筆失敗阻斷全部
    for qsc in queue_secure_codes:
        try:
            task = FwNodeExecutionQueue.query.filter_by(
                secure_code=qsc,
                org_secure_code=org.secure_code,
                status='WAITING'
            ).with_for_update().first()

            if not task:
                results.append({'queue_secure_code': qsc, 'success': False, 'error': _('找不到任務或已處理')})
                fail_count += 1
                continue

            # 檢查是否為指定簽核人
            task_result_data = (task.result or {}).get('data', {})
            if not can_act_on_task(task, user_code, org.secure_code, actor):
                results.append({'queue_secure_code': qsc, 'success': False, 'error': _('非指定簽核人')})
                fail_count += 1
                db.session.rollback()
                continue

            # 檢查是否被他人鎖定
            if task.is_locked and task.locked_by != user_code:
                results.append({'queue_secure_code': qsc, 'success': False, 'error': _('正由他人簽核中')})
                fail_count += 1
                db.session.rollback()
                continue

            # 防重複簽核
            existing = FwApprovalRecord.query.filter_by(
                workflow_instance_secure_code=task.workflow_instance_secure_code,
                node_queue_secure_code=task.secure_code,
                approver_secure_code=user_code
            ).filter(FwApprovalRecord.action.in_(['approved', 'rejected'])).first()

            if existing:
                results.append({'queue_secure_code': qsc, 'success': False, 'error': _('已簽核過此節點')})
                fail_count += 1
                db.session.rollback()
                continue

            # 驗證簽核意見最少字數
            min_comment_length = task_result_data.get('min_comment_length', 0)
            if min_comment_length > 0 and len(comment.strip()) < min_comment_length:
                results.append({'queue_secure_code': qsc, 'success': False,
                                'error': _('簽核意見至少需要 %(count)s 字', count=min_comment_length)})
                fail_count += 1
                db.session.rollback()
                continue

            use_custom_decisions = task_result_data.get('use_custom_decisions', False)
            output_variable = task_result_data.get('output_variable', '')

            # 建立簽核記錄
            approval_record = FwApprovalRecord(
                secure_code=secrets.token_urlsafe(16),
                org_secure_code=org.secure_code,
                workflow_instance_secure_code=task.workflow_instance_secure_code,
                form_instance_secure_code=task.form_instance_secure_code,
                node_id=task.node_id,
                node_name=task.node_name,
                node_queue_secure_code=task.secure_code,
                approver_secure_code=user_code,
                approver_name=current_user.display_name or current_user.username,
                action=decision,
                comment=comment,
                acted_at=datetime.utcnow(),
            )
            db.session.add(approval_record)

            # 寫入傳出變數
            if output_variable and selected_option_value is not None:
                from ..services.variable_service import VariableService
                VariableService.set_flow_var(
                    task.workflow_instance_secure_code,
                    output_variable,
                    selected_option_value,
                    org.secure_code,
                    task.node_id
                )

            # 更新任務狀態 + 釋放鎖定
            task.status = 'SUCCESS' if decision == 'approved' else 'REJECTED'
            task.completed_at = datetime.utcnow()
            task.result = {
                'decision': decision,
                'selected_path': selected_path,
                'selected_edges': selected_edges,
                'selected_option_value': selected_option_value,
                'comment': comment,
                'approver': user_code
            }
            task.release_lock()

            db.session.commit()

            # 觸發工作流推進（commit 後才推進）
            if decision == 'approved':
                try:
                    if use_custom_decisions and selected_edges:
                        for edge_id in selected_edges:
                            WorkflowEngine.advance_workflow(
                                task.workflow_instance_secure_code,
                                task.node_id,
                                edge_id
                            )
                    elif selected_path:
                        WorkflowEngine.advance_workflow(
                            task.workflow_instance_secure_code,
                            task.node_id,
                            selected_path
                        )
                    else:
                        WorkflowEngine.advance_workflow(
                            task.workflow_instance_secure_code,
                            task.node_id,
                            None
                        )
                except Exception as e:
                    logger.error(f'Batch approve - workflow advance error for {qsc}: {e}')
            elif decision == 'rejected' and use_custom_decisions:
                try:
                    WorkflowEngine.complete_workflow(
                        task.workflow_instance_secure_code,
                        status='REJECTED'
                    )
                except Exception as e:
                    logger.error(f'Batch approve - workflow complete (rejected) error for {qsc}: {e}')

            results.append({'queue_secure_code': qsc, 'success': True})
            success_count += 1

        except Exception as e:
            db.session.rollback()
            logger.error(f'Batch approve error for {qsc}: {e}')
            results.append({'queue_secure_code': qsc, 'success': False, 'error': str(e)})
            fail_count += 1

    return jsonify({
        'success': True,
        'message': _('批次簽核完成：成功 %(success_count)s 筆，失敗 %(fail_count)s 筆', success_count=success_count, fail_count=fail_count),
        'success_count': success_count,
        'fail_count': fail_count,
        'results': results
    })
