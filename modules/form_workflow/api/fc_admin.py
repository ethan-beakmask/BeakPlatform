"""
表單中心 - 管理操作（強制結束流程、刪除測試表單）
"""
import logging
import secrets
from datetime import datetime

from flask import jsonify
from flask_login import current_user

from app.security.decorators import module_access_required
from app.platform.data import get_current_org
from app import db, csrf

from .form_center import form_center_bp
from flask_babel import gettext as _

logger = logging.getLogger(__name__)


@form_center_bp.route('/force-end/<secure_code>', methods=['POST'])
@csrf.exempt
@module_access_required('form_workflow', False)
def force_end_workflow(secure_code):
    """
    強制結束流程

    權限：發起人 / 企業管理員 / 系統管理員
    條件：流程狀態為 RUNNING
    """
    from ..models import FwFormInstance, FwWorkflowInstance, FwApprovalRecord
    from ..services.workflow_engine import WorkflowEngine

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    # 查詢表單實例
    form_instance = FwFormInstance.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not form_instance:
        return jsonify({'success': False, 'error': _('找不到指定的表單')}), 404

    # 查詢流程實例
    workflow_instance = FwWorkflowInstance.query.filter_by(
        secure_code=form_instance.workflow_instance_secure_code,
        org_secure_code=org.secure_code
    ).first()

    if not workflow_instance:
        return jsonify({'success': False, 'error': _('找不到關聯的流程')}), 404

    # 權限檢查：發起人 or 管理員
    is_applicant = form_instance.applicant_secure_code == current_user.secure_code
    is_admin = getattr(current_user, 'is_org_admin', False)
    if not is_applicant and not is_admin:
        return jsonify({'success': False, 'error': _('無權限執行此操作')}), 403

    # 狀態檢查
    if workflow_instance.status != 'RUNNING':
        return jsonify({'success': False, 'error': _('流程狀態為 %(status)s，無法強制結束', status=workflow_instance.status)}), 400

    try:
        # 取消所有未完成節點
        WorkflowEngine.cancel_pending_nodes(workflow_instance.secure_code)

        # 完成工作流（狀態設為 CANCELLED）
        operator_name = current_user.display_name or current_user.username
        WorkflowEngine.complete_workflow(
            workflow_instance.secure_code,
            status='CANCELLED',
            end_message=f'由 {operator_name} 強制結束'
        )

        # 建立簽核記錄
        approval_record = FwApprovalRecord(
            secure_code=secrets.token_urlsafe(16),
            org_secure_code=org.secure_code,
            workflow_instance_secure_code=workflow_instance.secure_code,
            form_instance_secure_code=form_instance.secure_code,
            node_id='FORCE_END',
            node_name='強制結束',
            approver_secure_code=current_user.secure_code,
            approver_name=operator_name,
            action='FORCE_END',
            comment=f'由 {operator_name} 強制結束流程',
            acted_at=datetime.utcnow(),
        )
        db.session.add(approval_record)
        db.session.commit()

        logger.info(f'流程 {workflow_instance.execution_code} 已被 {operator_name} 強制結束')

        return jsonify({
            'success': True,
            'message': _('流程已強制結束')
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f'強制結束流程失敗: {e}')
        return jsonify({'success': False, 'error': _('操作失敗: %(error)s', error=str(e))}), 500


@form_center_bp.route('/my-test-forms', methods=['DELETE'])
@csrf.exempt
@module_access_required('form_workflow', False)
def delete_my_test_forms():
    """
    批量 soft delete 當前用戶的測試表單（歷史終態）

    權限：具 form_workflow.design.tryout（試行設計稿）
    條件：is_test=True, 終態, 本人發起, 未刪除
    """
    from ..models import FwFormInstance, FwWorkflowInstance

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    # 權限：具 design.tryout 才可操作
    from app.platform.auth import has_permission
    can_tryout = has_permission('form_workflow.design.tryout')
    if not can_tryout:
        return jsonify({'success': False, 'error': _('無權限執行此操作')}), 403

    # FwWorkflowInstance 終態：COMPLETED/ERROR/CANCELLED/REJECTED
    # 用 JOIN 確保流程已結束
    wf_terminal = ('COMPLETED', 'ERROR', 'CANCELLED', 'REJECTED')

    # 查詢符合條件的測試表單
    # 注意：早期表單 is_test 未正確標記，以 serial_number 前綴 TEST- 為準
    test_instances = FwFormInstance.query.join(
        FwWorkflowInstance,
        FwFormInstance.workflow_instance_secure_code == FwWorkflowInstance.secure_code
    ).filter(
        FwFormInstance.org_secure_code == org.secure_code,
        FwFormInstance.applicant_secure_code == current_user.secure_code,
        FwFormInstance.serial_number.like('TEST-%'),
        FwFormInstance.is_deleted == False,
        FwWorkflowInstance.status.in_(wf_terminal)
    ).all()

    if not test_instances:
        return jsonify({'success': True, 'deleted_count': 0, 'message': _('沒有可刪除的測試表單')})

    try:
        deleted_count = 0
        for fi in test_instances:
            fi.is_deleted = True
            deleted_count += 1

            # 同步 soft delete 關聯的 workflow instance
            if fi.workflow_instance_secure_code:
                wi = FwWorkflowInstance.query.filter_by(
                    secure_code=fi.workflow_instance_secure_code,
                    org_secure_code=org.secure_code
                ).first()
                if wi:
                    wi.is_deleted = True

        db.session.commit()

        operator_name = current_user.display_name or current_user.username
        logger.info(f'{operator_name} 批量刪除了 {deleted_count} 筆測試表單')

        return jsonify({
            'success': True,
            'deleted_count': deleted_count,
            'message': _('已刪除 %(count)s 筆測試表單', count=deleted_count)
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f'批量刪除測試表單失敗: {e}')
        return jsonify({'success': False, 'error': _('操作失敗: %(error)s', error=str(e))}), 500
