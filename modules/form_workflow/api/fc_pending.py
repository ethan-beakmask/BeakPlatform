"""
表單中心 - 待簽核任務 + 鎖定/解鎖 + 單筆簽核
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
from .fc_utils import _apply_field_permissions_to_schema
from flask_babel import gettext as _

logger = logging.getLogger(__name__)


@form_center_bp.route('/pending-tasks')
@module_access_required('form_workflow', False)
def list_pending_tasks():
    """取得我的待簽核任務"""
    from ..models import FwNodeExecutionQueue, FwFormInstance, FwFormTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    # 查詢等待簽核的節點
    tasks = FwNodeExecutionQueue.query.filter(
        FwNodeExecutionQueue.org_secure_code == org.secure_code,
        FwNodeExecutionQueue.status == 'WAITING',
        FwNodeExecutionQueue.node_type.in_(['Approve', 'FormAdapter', 'FORMADAPTER'])
    ).order_by(FwNodeExecutionQueue.scheduled_at.asc()).all()

    user_code = current_user.secure_code

    # 先過濾出指派給當前用戶的任務
    my_tasks = []
    form_sc_set = set()
    for task in tasks:
        task_result_data = (task.result or {}).get('data', {})
        assignee_type = task_result_data.get('assignee_type')
        assignees = task_result_data.get('assignees', [])
        if assignee_type and user_code not in assignees:
            continue
        my_tasks.append(task)
        if task.form_instance_secure_code:
            form_sc_set.add(task.form_instance_secure_code)

    # 批次查 FwFormInstance
    fi_map = {}
    if form_sc_set:
        fi_list = FwFormInstance.query.filter(
            FwFormInstance.secure_code.in_(list(form_sc_set))
        ).all()
        fi_map = {fi.secure_code: fi for fi in fi_list}

    # 批次查 FwFormTemplate 取 category (透過 form_template_id)
    ft_ids = set()
    for fi in fi_map.values():
        if fi.form_template_id:
            ft_ids.add(fi.form_template_id)
    ft_cat_map = {}
    ft_cat_sc_map = {}
    if ft_ids:
        ft_list = FwFormTemplate.query.filter(
            FwFormTemplate.id.in_(list(ft_ids))
        ).all()
        ft_cat_map = {t.id: t.category for t in ft_list}
        ft_cat_sc_map = {t.id: t.category_secure_code for t in ft_list}

    result = []
    for task in my_tasks:
        fi = fi_map.get(task.form_instance_secure_code)
        serial_number = fi.serial_number if fi else None

        form_subject = None
        category = None
        category_sc = None
        if fi:
            form_subject = fi.subject or ''
            category = ft_cat_map.get(fi.form_template_id)
            category_sc = ft_cat_sc_map.get(fi.form_template_id)

        # 鎖定資訊
        lock_info = {}
        if task.is_locked:
            lock_info = {
                'is_locked': True,
                'locked_by': task.locked_by,
                'locked_by_self': task.locked_by == user_code,
            }
        else:
            lock_info = {'is_locked': False}

        result.append({
            'queue_secure_code': task.secure_code,
            'node_id': task.node_id,
            'node_type': task.node_type,
            'node_name': task.node_name,
            'form_name': fi.form_name if fi else None,
            'serial_number': serial_number,
            'applicant_name': fi.applicant_name if fi else None,
            'submitted_at': task.scheduled_at.isoformat() if task.scheduled_at else None,
            'scheduled_at': task.scheduled_at.isoformat() if task.scheduled_at else None,
            'is_test': fi.is_test if fi else False,
            'form_subject': form_subject,
            'category': category,
            'category_secure_code': category_sc,
            'form_instance_secure_code': fi.secure_code if fi else None,
            'published_secure_code': fi.published_secure_code if fi else None,
            **lock_info,
        })

    # 排序
    sort_field = request.args.get('sort', 'scheduled_at')
    sort_order = request.args.get('order', 'asc')
    reverse = (sort_order == 'desc')
    if sort_field == 'serial_number':
        result.sort(key=lambda x: x.get('serial_number', '') or '', reverse=reverse)
    else:
        result.sort(key=lambda x: x.get('scheduled_at', '') or '', reverse=reverse)

    return jsonify({
        'success': True,
        'data': result
    })


@form_center_bp.route('/pending-tasks/<secure_code>')
@module_access_required('form_workflow', False)
def get_pending_task(secure_code):
    """取得待簽核任務詳情（含簽核歷程）"""
    from ..models import FwNodeExecutionQueue, FwFormInstance, FwApprovalRecord

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    task = FwNodeExecutionQueue.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code
    ).first()

    if not task:
        return jsonify({'success': False, 'error': _('找不到指定的任務')}), 404

    # 檢查當前用戶是否為指定簽核人
    task_result_data = (task.result or {}).get('data', {})
    assignee_type = task_result_data.get('assignee_type')
    assignees = task_result_data.get('assignees', [])
    if assignee_type and current_user.secure_code not in assignees:
        return jsonify({'success': False, 'error': _('您不是此任務的指定簽核人')}), 403

    # 取得表單資訊（使用 secure_code）
    form_instance = FwFormInstance.query.filter_by(
        secure_code=task.form_instance_secure_code
    ).first() if task.form_instance_secure_code else None

    # 取得可用路徑（FormAdapter 存在 result.data.available_paths）
    node_config = task.node_config or {}
    result_data = (task.result or {}).get('data', {})
    available_paths = result_data.get('available_paths', [])

    # 取得簽核配置
    selection_mode = result_data.get('selection_mode', 'single')
    allow_comment = result_data.get('allow_comment', True)
    require_comment = result_data.get('require_comment', False)
    min_comment_length = result_data.get('min_comment_length', 1 if require_comment else 0)
    use_custom_decisions = result_data.get('use_custom_decisions', False)
    output_variable = result_data.get('output_variable', '')
    input_variable_results = result_data.get('input_variable_results', {})

    # 判斷用戶角色 (approver/reader) 並取得欄位權限
    field_permissions = node_config.get('field_permissions', {})
    is_approver = current_user.secure_code in (task_result_data.get('assignees', []))
    user_role = 'approver' if is_approver else 'reader'
    role_permissions = field_permissions.get(user_role, {})

    # 根據欄位權限修改 form schema
    form_schema = form_instance.schema_snapshot if form_instance else {}
    has_editable = False
    if role_permissions and form_schema:
        form_schema, has_editable = _apply_field_permissions_to_schema(
            form_schema, role_permissions
        )

    # EGRESS-01 form_node 語境：出口政策過濾（欄位權限之後，政策為最終守門）
    form_data = form_instance.form_data if form_instance else {}
    if form_instance:
        from ..services.egress_adapter import apply_form_egress
        form_schema, form_data = apply_form_egress(
            form_instance, form_schema, task.node_id
        )

    # 取得簽核歷程
    approvals = []
    if task.workflow_instance_secure_code:
        approval_records = FwApprovalRecord.query.filter_by(
            workflow_instance_secure_code=task.workflow_instance_secure_code
        ).order_by(FwApprovalRecord.acted_at.asc()).all()

        for approval in approval_records:
            approvals.append({
                'node_id': approval.node_id,
                'node_name': approval.node_name,
                'approver_name': approval.approver_name,
                'action': approval.action,
                'comment': approval.comment,
                'acted_at': approval.acted_at.isoformat() if approval.acted_at else None,
            })

    return jsonify({
        'success': True,
        'data': {
            'queue_secure_code': task.secure_code,
            'node_id': task.node_id,
            'node_type': task.node_type,
            'node_name': task.node_name,
            'node_config': node_config,
            'form_data': form_data,
            'form_schema': form_schema,
            'form_name': form_instance.form_name if form_instance else None,
            'form_subject': form_instance.subject if form_instance else None,
            'serial_number': form_instance.serial_number if form_instance else None,
            'applicant_name': form_instance.applicant_name if form_instance else None,
            'builder_config': form_instance.builder_config if form_instance else None,
            'form_instance_secure_code': form_instance.secure_code if form_instance else None,
            'available_paths': available_paths,
            'selection_mode': selection_mode,
            'allow_comment': allow_comment,
            'require_comment': require_comment,
            'min_comment_length': min_comment_length,
            'use_custom_decisions': use_custom_decisions,
            'output_variable': output_variable,
            'input_variable_results': input_variable_results,
            'approvals': approvals,
            'field_permissions': role_permissions,
            'has_editable_fields': has_editable,
            'user_role': user_role,
        }
    })


@form_center_bp.route('/pending-tasks/<secure_code>/lock', methods=['POST'])
@csrf.exempt
@module_access_required('form_workflow', False)
def lock_task(secure_code):
    """
    取得簽核鎖定

    使用 SELECT ... FOR UPDATE 悲觀鎖，確保同一時間只有一人能簽核。
    鎖定有效期 10 分鐘，逾時自動失效。
    """
    from ..models import FwNodeExecutionQueue
    from app.models.user import User

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    try:
        # FOR UPDATE 鎖定行，防止並行取鎖
        task = FwNodeExecutionQueue.query.filter_by(
            secure_code=secure_code,
            org_secure_code=org.secure_code,
            status='WAITING'
        ).with_for_update().first()

        if not task:
            return jsonify({'success': False, 'error': _('找不到任務或已處理')}), 404

        # 檢查當前用戶是否為指定簽核人
        task_result_data = (task.result or {}).get('data', {})
        assignee_type = task_result_data.get('assignee_type')
        assignees = task_result_data.get('assignees', [])
        if assignee_type and current_user.secure_code not in assignees:
            return jsonify({'success': False, 'error': _('您不是此任務的指定簽核人')}), 403

        # 檢查是否已被鎖定
        if task.is_locked:
            if task.locked_by == current_user.secure_code:
                # 同一人重複取鎖：刷新鎖定時間
                task.acquire_lock(current_user.secure_code)
                db.session.commit()
                return jsonify({
                    'success': True,
                    'message': _('鎖定已刷新'),
                    'remaining_seconds': task.lock_remaining_seconds
                })
            else:
                # 被他人鎖定：查詢鎖定者資訊
                locker = User.query.filter_by(secure_code=task.locked_by).first()
                locker_display = locker.employee_id or locker.display_name or locker.username if locker else '未知'
                return jsonify({
                    'success': False,
                    'error': _('此表單由 %(locker)s 簽核中', locker=locker_display),
                    'locked_by_display': locker_display,
                    'code': 'LOCKED'
                }), 409

        # 取得鎖定
        task.acquire_lock(current_user.secure_code)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': _('已取得簽核鎖定'),
            'remaining_seconds': task.lock_remaining_seconds
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f'取得簽核鎖定失敗: {e}')
        return jsonify({'success': False, 'error': _('取得鎖定失敗: %(error)s', error=str(e))}), 500


@form_center_bp.route('/pending-tasks/<secure_code>/lock', methods=['DELETE'])
@csrf.exempt
@module_access_required('form_workflow', False)
def unlock_task(secure_code):
    """
    釋放簽核鎖定（best-effort，用於關閉分頁時呼叫）
    只有鎖定者本人可釋放。
    """
    from ..models import FwNodeExecutionQueue

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    try:
        task = FwNodeExecutionQueue.query.filter_by(
            secure_code=secure_code,
            org_secure_code=org.secure_code
        ).with_for_update().first()

        if not task:
            return jsonify({'success': False, 'error': _('找不到任務')}), 404

        # 只有鎖定者可以釋放
        if task.locked_by == current_user.secure_code:
            task.release_lock()
            db.session.commit()

        return jsonify({'success': True, 'message': _('鎖定已釋放')})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@form_center_bp.route('/pending-tasks/<secure_code>/approve', methods=['POST'])
@csrf.exempt
@module_access_required('form_workflow', False)
def approve_task(secure_code):
    """簽核任務（含鎖定驗證 + 重複簽核防護）"""
    from ..models import FwNodeExecutionQueue, FwApprovalRecord
    from ..services.workflow_engine import WorkflowEngine

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    try:
        # FOR UPDATE 鎖定行，防止並行簽核
        task = FwNodeExecutionQueue.query.filter_by(
            secure_code=secure_code,
            org_secure_code=org.secure_code,
            status='WAITING'
        ).with_for_update().first()

        if not task:
            return jsonify({'success': False, 'error': _('找不到任務或已處理')}), 404

        # 檢查當前用戶是否為指定簽核人
        task_result_data = (task.result or {}).get('data', {})
        assignee_type = task_result_data.get('assignee_type')
        assignees = task_result_data.get('assignees', [])
        if assignee_type and current_user.secure_code not in assignees:
            return jsonify({'success': False, 'error': _('您不是此任務的指定簽核人')}), 403

        # 驗證鎖定持有者：必須是當前用戶且未逾時
        if task.is_locked and task.locked_by != current_user.secure_code:
            return jsonify({
                'success': False,
                'error': _('此表單正由他人簽核中'),
                'code': 'LOCKED'
            }), 409

        if task.locked_by == current_user.secure_code and not task.is_locked:
            return jsonify({
                'success': False,
                'error': _('簽核逾時，鎖定已失效，請重新開啟'),
                'code': 'LOCK_EXPIRED'
            }), 409

        # P1: 防止同一人重複簽核同一佇列項目（而非 node_id，以支援合法迴圈）
        existing_approval = FwApprovalRecord.query.filter_by(
            workflow_instance_secure_code=task.workflow_instance_secure_code,
            node_queue_secure_code=task.secure_code,
            approver_secure_code=current_user.secure_code
        ).filter(FwApprovalRecord.action.in_(['approved', 'rejected'])).first()

        if existing_approval:
            return jsonify({
                'success': False,
                'error': _('您已簽核過此節點，無法重複簽核'),
                'code': 'DUPLICATE'
            }), 409

        data = request.get_json() or {}
        decision = data.get('decision', 'approved')
        selected_path = data.get('selected_path')          # 舊模式: 單一 edge ID (str)
        selected_edges = data.get('selected_edges')         # 新模式: edge ID 列表 (list)
        selected_option_value = data.get('selected_option_value')  # 自定義決策的選項值
        comment = data.get('comment', '')
        updated_form_data = data.get('form_data')

        # 判斷是否為自定義決策模式
        use_custom_decisions = task_result_data.get('use_custom_decisions', False)
        output_variable = task_result_data.get('output_variable', '')

        # 驗證簽核意見最少字數
        min_comment_length = task_result_data.get('min_comment_length', 0)
        if min_comment_length > 0 and len(comment.strip()) < min_comment_length:
            return jsonify({'success': False, 'error': _('簽核意見至少需要 %(count)s 字', count=min_comment_length)}), 400

        # 處理表單欄位修改
        from ..models import FwFormInstance, FwFormFieldChange
        node_config = task.node_config or {}
        field_permissions = node_config.get('field_permissions', {})
        approver_permissions = field_permissions.get('approver', {})

        # 動態欄位權限覆蓋（來向變數控制）
        input_variable_results = task_result_data.get('input_variable_results', {})
        field_permission_overrides = input_variable_results.get('field_permission_overrides', {})
        if field_permission_overrides:
            approver_permissions = dict(approver_permissions)
            approver_permissions.update(field_permission_overrides)

        if updated_form_data and approver_permissions:
            form_instance = FwFormInstance.query.filter_by(
                secure_code=task.form_instance_secure_code
            ).first()

            if form_instance:
                old_form_data = form_instance.form_data or {}

                for field_key, new_value in updated_form_data.items():
                    perm = approver_permissions.get(field_key, 'readonly')
                    old_value = old_form_data.get(field_key)

                    if old_value == new_value:
                        continue

                    if perm != 'editable':
                        return jsonify({
                            'success': False,
                            'error': _('欄位 %(field_key)s 不允許修改', field_key=field_key)
                        }), 403

                    field_change = FwFormFieldChange(
                        secure_code=secrets.token_urlsafe(16),
                        org_secure_code=org.secure_code,
                        form_instance_secure_code=task.form_instance_secure_code,
                        workflow_instance_secure_code=task.workflow_instance_secure_code,
                        node_id=task.node_id,
                        node_name=task.node_name,
                        changed_by_secure_code=current_user.secure_code,
                        changed_by_name=current_user.display_name or current_user.username,
                        field_key=field_key,
                        field_label=field_key,
                        old_value=old_value,
                        new_value=new_value,
                        changed_at=datetime.utcnow(),
                    )
                    db.session.add(field_change)

                merged_data = dict(old_form_data)
                for field_key, new_value in updated_form_data.items():
                    if approver_permissions.get(field_key) == 'editable':
                        merged_data[field_key] = new_value
                form_instance.form_data = merged_data

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
            action=decision,
            comment=comment,
            acted_at=datetime.utcnow(),
        )
        db.session.add(approval_record)

        # 寫入傳出變數（output_variable）
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
            'approver': current_user.secure_code
        }
        task.release_lock()

        # 簽核確認：將 pending_delete 的附件正式刪除
        from app.services import file_service as _fs
        _fs.confirm_pending_deletes(org.secure_code, task.form_instance_secure_code)

        db.session.commit()

        # 觸發工作流推進
        if decision == 'approved':
            try:
                if use_custom_decisions and selected_edges:
                    # 自定義決策模式：N:M 映射，逐條 edge 推進
                    # 去重同一 target_node
                    advanced_nodes = set()
                    for edge_id in selected_edges:
                        items = WorkflowEngine.advance_workflow(
                            task.workflow_instance_secure_code,
                            task.node_id,
                            edge_id
                        )
                        for item in items:
                            advanced_nodes.add(item.node_id)
                elif selected_path:
                    # 舊模式：單一 edge
                    WorkflowEngine.advance_workflow(
                        task.workflow_instance_secure_code,
                        task.node_id,
                        selected_path
                    )
                else:
                    # Fallback: 取所有出邊
                    WorkflowEngine.advance_workflow(
                        task.workflow_instance_secure_code,
                        task.node_id,
                        None
                    )
            except Exception as e:
                logger.error(f'Workflow advance error: {e}')
        elif decision == 'rejected' and use_custom_decisions:
            # 自定義決策模式下 rejected 且 target_edges 為空 -> 完成工作流為 REJECTED
            try:
                WorkflowEngine.complete_workflow(
                    task.workflow_instance_secure_code,
                    status='REJECTED'
                )
            except Exception as e:
                logger.error(f'Workflow complete (rejected) error: {e}')

        return jsonify({
            'success': True,
            'message': _('簽核完成') if decision == 'approved' else _('已退回')
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': _('簽核失敗: %(error)s', error=str(e))}), 500
