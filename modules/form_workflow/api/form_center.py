"""
FormWorkflow Module - Form Center API
表單中心 API

提供一般用戶填寫表單、發起流程、查看進度等功能。
"""
import secrets
from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_login import current_user

from app.security.decorators import login_required
from app.platform.data import get_current_org
from app import db, csrf

# 建立 API Blueprint
form_center_bp = Blueprint(
    'form_workflow_form_center',
    __name__,
    url_prefix='/api/form-center'
)


# =============================================================================
# 可用表單列表
# =============================================================================

@form_center_bp.route('/available-forms')
@login_required
def list_available_forms():
    """
    取得可填寫的表單列表

    權限控制：
    - 一般用戶 (ORG_USER)：只顯示已發行 (Published) 的表單
    - 管理員 (ORG_ADMIN/SYSTEM_ADMIN)：顯示已發行 + 未發行配對（用於測試，標記 TEST）

    回傳格式：
    - _status: 'published' (已發行) 或 'test' (測試中)
    - _source: 'published' (來自快照) 或 'mapping' (來自設計稿)
    """
    from ..models import (
        FwPublishedFormWorkflow, FwFormWorkflowMapping,
        FwFormTemplate, FwWorkflowTemplate
    )

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    # 判斷是否為管理員
    is_admin = (
        getattr(current_user, 'is_system_admin', False) or
        getattr(current_user, 'level', 0) >= 90  # ORG_ADMIN level
    )

    result = []
    seen_mapping_ids = set()

    # 1. 優先顯示已發行版本（從快照取得，設計稿刪除不影響）
    published_list = FwPublishedFormWorkflow.query.filter_by(
        org_secure_code=org.secure_code,
        status='Published',
        is_deleted=False
    ).order_by(FwPublishedFormWorkflow.published_at.desc()).all()

    for p in published_list:
        mapping_id = p.source_mapping_id
        if mapping_id in seen_mapping_ids:
            continue
        seen_mapping_ids.add(mapping_id)

        form_snapshot = p.form_snapshot or {}
        workflow_snapshot = p.workflow_snapshot or {}

        result.append({
            'id': p.source_form_template_id,
            'secure_code': p.secure_code,
            'name': form_snapshot.get('name') or p.name,
            'description': form_snapshot.get('description') or p.description,
            'category': form_snapshot.get('category'),
            'code': form_snapshot.get('code'),
            'version': form_snapshot.get('version'),
            'publish_version': p.publish_version,
            'published_at': p.published_at.isoformat() if p.published_at else None,
            'workflow_template_name': workflow_snapshot.get('name'),
            'mapping_id': mapping_id,
            '_status': 'published',
            '_source': 'published',
        })

    # 2. 管理員額外顯示未發行的配對（用於測試）
    if is_admin:
        mappings = FwFormWorkflowMapping.query.filter_by(
            org_secure_code=org.secure_code,
            is_active=True,
            is_deleted=False
        ).order_by(FwFormWorkflowMapping.created_at.desc()).all()

        for mapping in mappings:
            # 跳過已經顯示的發行版本
            if mapping.id in seen_mapping_ids:
                continue

            # 查詢表單和流程模板
            form_template = FwFormTemplate.query.filter_by(
                id=mapping.form_template_id,
                is_deleted=False,
                is_active=True
            ).first()

            workflow_template = FwWorkflowTemplate.query.filter_by(
                id=mapping.workflow_template_id,
                is_deleted=False,
                is_subprocess=False
            ).first()

            if not form_template or not workflow_template:
                continue

            result.append({
                'id': form_template.id,
                'secure_code': form_template.secure_code,
                'name': form_template.name,
                'description': form_template.description,
                'category': form_template.category,
                'code': form_template.code,
                'version': form_template.version,
                'mapping_id': mapping.id,
                'mapping_secure_code': mapping.secure_code,
                'workflow_template_id': workflow_template.id,
                'workflow_template_name': workflow_template.name,
                'workflow_template_secure_code': workflow_template.secure_code,
                '_status': 'test',
                '_source': 'mapping',
            })

    return jsonify({
        'success': True,
        'data': result,
        'is_admin': is_admin
    })


@form_center_bp.route('/forms/<secure_code>')
@login_required
def get_form_for_filling(secure_code):
    """
    取得表單定義（用於填寫）

    支援兩種來源：
    1. 已發行版本 (Published) - 使用 published 的 secure_code
    2. 設計稿測試 (Test) - 使用 form_template 的 secure_code + ?source=mapping

    Args:
        secure_code: 已發行版本或表單模板的 secure_code
        source: 'published' (預設) 或 'mapping' (測試模式)
    """
    from ..models import FwPublishedFormWorkflow, FwFormTemplate, FwFormWorkflowMapping

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    source = request.args.get('source', 'published')

    if source == 'mapping':
        # 測試模式：從設計稿取得表單定義
        form_template = FwFormTemplate.query.filter_by(
            secure_code=secure_code,
            org_secure_code=org.secure_code,
            is_deleted=False
        ).first()

        if not form_template:
            return jsonify({'success': False, 'error': '找不到指定的表單'}), 404

        # 取得配對資訊
        mapping = FwFormWorkflowMapping.query.filter_by(
            form_template_secure_code=secure_code,
            org_secure_code=org.secure_code,
            is_deleted=False
        ).first()

        return jsonify({
            'success': True,
            'data': {
                'secure_code': form_template.secure_code,
                'name': form_template.name,
                'form_name': form_template.name,
                'form_code': form_template.code,
                'schema': form_template.schema,
                'description': form_template.description,
                'builder_config': form_template.builder_config,
                '_source': 'mapping',
                '_is_test': True,
                'mapping_secure_code': mapping.secure_code if mapping else None,
            }
        })
    else:
        # 正式模式：從已發行快照取得
        published = FwPublishedFormWorkflow.query.filter_by(
            secure_code=secure_code,
            org_secure_code=org.secure_code,
            status='Published',
            is_deleted=False
        ).first()

        if not published:
            return jsonify({'success': False, 'error': '找不到指定的表單或已停用'}), 404

        form_snapshot = published.form_snapshot or {}

        return jsonify({
            'success': True,
            'data': {
                'secure_code': published.secure_code,
                'name': published.name,
                'form_name': form_snapshot.get('name'),
                'form_code': form_snapshot.get('code'),
                'schema': form_snapshot.get('schema'),
                'description': published.description,
                'builder_config': form_snapshot.get('builder_config'),
                '_source': 'published',
                '_is_test': False,
            }
        })


# =============================================================================
# 表單提交與流程觸發
# =============================================================================

@form_center_bp.route('/submit', methods=['POST'])
@csrf.exempt
@login_required
def submit_form():
    """
    提交表單並觸發流程

    支援兩種模式：
    1. 正式模式：使用 published_secure_code（已發行快照）
    2. 測試模式：使用 mapping_secure_code（設計稿，需管理員權限）

    Request JSON:
    {
        "published_secure_code": "xxx",  # 正式模式
        "mapping_secure_code": "xxx",    # 測試模式（二選一）
        "form_data": {...}               # 表單資料
    }

    Response:
    {
        "success": true,
        "data": {
            "form_instance_secure_code": "xxx",
            "serial_number": "xxx",
            "workflow_instance_secure_code": "xxx",
            "execution_code": "xxx",
            "is_test": false
        }
    }
    """
    from ..models import (
        FwPublishedFormWorkflow, FwFormInstance, FwWorkflowInstance,
        FwNodeExecutionQueue, FwFormTemplate, FwWorkflowTemplate,
        FwFormWorkflowMapping
    )

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    data = request.get_json() or {}
    published_secure_code = data.get('published_secure_code')
    mapping_secure_code = data.get('mapping_secure_code')
    form_data = data.get('form_data', {})

    # 判斷模式
    is_test_mode = bool(mapping_secure_code) and not published_secure_code

    if not published_secure_code and not mapping_secure_code:
        return jsonify({'success': False, 'error': '缺少 published_secure_code 或 mapping_secure_code'}), 400

    try:
        date_str = datetime.now().strftime('%Y%m%d')
        from sqlalchemy import text

        if is_test_mode:
            # ============================================
            # 測試模式：使用設計稿（需管理員權限）
            # ============================================
            is_admin = (
                getattr(current_user, 'is_system_admin', False) or
                getattr(current_user, 'level', 0) >= 90
            )
            if not is_admin:
                return jsonify({'success': False, 'error': '測試模式需要管理員權限'}), 403

            # 查找配對
            mapping = FwFormWorkflowMapping.query.filter_by(
                secure_code=mapping_secure_code,
                org_secure_code=org.secure_code,
                is_deleted=False
            ).first()

            if not mapping:
                return jsonify({'success': False, 'error': '找不到指定的配對'}), 404

            # 取得表單設計稿
            form_template = FwFormTemplate.query.filter_by(
                id=mapping.form_template_id,
                is_deleted=False
            ).first()

            if not form_template:
                return jsonify({'success': False, 'error': '找不到關聯的表單模板'}), 404

            # 取得流程設計稿
            workflow_template = FwWorkflowTemplate.query.filter_by(
                id=mapping.workflow_template_id,
                is_deleted=False
            ).first()

            if not workflow_template:
                return jsonify({'success': False, 'error': '找不到關聯的流程模板'}), 404

            # 使用設計稿資料
            form_name = form_template.name
            form_code = form_template.code
            form_version = form_template.version
            form_schema = form_template.schema
            workflow_name = workflow_template.name
            workflow_version = workflow_template.revision
            workflow_graph = workflow_template.graph or workflow_template.cytoscape_config or {}

            source_form_template_id = form_template.id
            source_form_template_secure_code = form_template.secure_code
            source_workflow_template_id = workflow_template.id
            source_workflow_template_secure_code = workflow_template.secure_code
            published_sc = None  # 測試模式沒有 published

            # 生成測試序號 (TEST-YYYYMMDD-NNNN)
            form_prefix = 'TEST-'
            proc_prefix = 'TEST-'

        else:
            # ============================================
            # 正式模式：使用已發行快照
            # ============================================
            published = FwPublishedFormWorkflow.query.filter_by(
                secure_code=published_secure_code,
                org_secure_code=org.secure_code,
                is_deleted=False
            ).first()

            if not published:
                return jsonify({'success': False, 'error': '找不到指定的表單'}), 404

            if published.status != 'Published':
                return jsonify({'success': False, 'error': '此表單已停用'}), 400

            # 標記為已使用
            published.mark_as_used()

            # 從快照取得表單和流程定義
            form_snapshot = published.form_snapshot or {}
            workflow_snapshot = published.workflow_snapshot or {}

            form_name = form_snapshot.get('name')
            form_code = form_snapshot.get('code')
            form_version = published.source_form_version
            form_schema = form_snapshot.get('schema')
            workflow_name = workflow_snapshot.get('name')
            workflow_version = published.source_workflow_version
            workflow_graph = workflow_snapshot.get('graph') or workflow_snapshot.get('cytoscape_config') or {}

            source_form_template_id = published.source_form_template_id
            source_form_template_secure_code = published.source_form_template_secure_code
            source_workflow_template_id = published.source_workflow_template_id
            source_workflow_template_secure_code = published.source_workflow_template_secure_code
            published_sc = published.secure_code

            # 生成正式序號 (FORM-YYYYMMDD-NNNN / PROC-YYYYMMDD-NNNN)
            form_prefix = 'FORM-'
            proc_prefix = 'PROC-'

        # 生成表單序號
        result = db.session.execute(
            text("""
                SELECT COALESCE(MAX(CAST(SUBSTRING(serial_number FROM '\\d{4}$') AS INTEGER)), 0) + 1
                FROM fw_form_instances
                WHERE serial_number LIKE :pattern
            """),
            {'pattern': f'{form_prefix}{date_str}-%'}
        )
        form_seq = result.scalar() or 1
        serial_number = f"{form_prefix}{date_str}-{str(form_seq).zfill(4)}"

        # 建立表單實例
        form_instance = FwFormInstance(
            secure_code=secrets.token_urlsafe(16),
            org_secure_code=org.secure_code,
            form_template_id=source_form_template_id,
            form_template_secure_code=source_form_template_secure_code,
            published_secure_code=published_sc,
            serial_number=serial_number,
            form_name=form_name,
            form_code=form_code,
            form_version=form_version,
            applicant_secure_code=current_user.secure_code,
            applicant_name=current_user.display_name or current_user.username,
            applicant_username=current_user.username,
            applicant_email=getattr(current_user, 'email', None),
            applicant_dept=getattr(current_user, 'department_name', None),
            form_data=form_data,
            schema_snapshot=form_schema,
            status='INITIAL',
            source_type='WEB',
            source_ip=request.remote_addr,
            submitted_at=datetime.utcnow(),
        )

        db.session.add(form_instance)
        db.session.flush()

        # 生成流程執行編號
        result = db.session.execute(
            text("""
                SELECT COALESCE(MAX(CAST(SUBSTRING(execution_code FROM '\\d{4}$') AS INTEGER)), 0) + 1
                FROM fw_workflow_instances
                WHERE execution_code LIKE :pattern
            """),
            {'pattern': f'{proc_prefix}{date_str}-%'}
        )
        proc_seq = result.scalar() or 1
        execution_code = f"{proc_prefix}{date_str}-{str(proc_seq).zfill(4)}"

        # 建立流程實例
        workflow_instance = FwWorkflowInstance(
            secure_code=secrets.token_urlsafe(16),
            org_secure_code=org.secure_code,
            form_instance_id=form_instance.id,
            form_instance_secure_code=form_instance.secure_code,
            workflow_template_id=source_workflow_template_id,
            workflow_template_secure_code=source_workflow_template_secure_code,
            published_secure_code=published_sc,
            execution_code=execution_code,
            workflow_name=workflow_name,
            workflow_version=workflow_version,
            graph_snapshot=workflow_graph,
            status='RUNNING',
            started_at=datetime.utcnow(),
        )

        db.session.add(workflow_instance)
        db.session.flush()

        # 更新表單實例的流程關聯
        form_instance.workflow_instance_id = workflow_instance.id
        form_instance.workflow_instance_secure_code = workflow_instance.secure_code

        # 找到起始節點
        nodes = workflow_graph.get('nodes', [])
        start_node = None
        for node in nodes:
            node_id = node.get('id', '')
            node_type = node.get('type', '')
            if node_id.startswith('node-Start') or node_type in ('Start', 'START'):
                start_node = node
                break

        if not start_node:
            db.session.rollback()
            return jsonify({'success': False, 'error': '流程中找不到起始節點'}), 400

        # 將起始節點加入執行佇列
        node_id = start_node.get('id')
        node_config = start_node.get('config', {})
        display_name = start_node.get('label') or start_node.get('data', {}).get('label') or '開始'

        queue_item = FwNodeExecutionQueue(
            secure_code=secrets.token_urlsafe(16),
            org_secure_code=org.secure_code,
            workflow_instance_secure_code=workflow_instance.secure_code,
            form_instance_secure_code=form_instance.secure_code,
            node_id=node_id,
            node_type='Start',
            node_name=display_name,
            node_config=node_config,
            status='PENDING',
            priority=10,
            scheduled_at=datetime.utcnow(),
        )

        db.session.add(queue_item)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': '表單已送出，流程已啟動' + ('（測試模式）' if is_test_mode else ''),
            'data': {
                'form_instance_secure_code': form_instance.secure_code,
                'serial_number': form_instance.serial_number,
                'workflow_instance_secure_code': workflow_instance.secure_code,
                'execution_code': workflow_instance.execution_code,
                'is_test': is_test_mode,
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'建立失敗: {str(e)}'}), 500


# =============================================================================
# 我的表單
# =============================================================================

@form_center_bp.route('/my-forms')
@login_required
def list_my_forms():
    """取得我提交的表單列表"""
    from ..models import FwFormInstance

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    # 篩選條件
    status = request.args.get('status')
    limit = request.args.get('limit', 50, type=int)

    query = FwFormInstance.query.filter_by(
        org_secure_code=org.secure_code,
        applicant_secure_code=current_user.secure_code,
        is_deleted=False
    )

    if status:
        query = query.filter_by(status=status)

    instances = query.order_by(FwFormInstance.created_at.desc()).limit(limit).all()

    return jsonify({
        'success': True,
        'data': [i.to_dict(include_form_data=False) for i in instances]
    })


@form_center_bp.route('/my-forms/<secure_code>')
@login_required
def get_my_form(secure_code):
    """取得我的表單詳情"""
    from ..models import FwFormInstance

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    instance = FwFormInstance.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        applicant_secure_code=current_user.secure_code,
        is_deleted=False
    ).first()

    if not instance:
        return jsonify({'success': False, 'error': '找不到指定的表單'}), 404

    return jsonify({
        'success': True,
        'data': instance.to_dict(include_form_data=True)
    })


# =============================================================================
# 待簽核任務
# =============================================================================

@form_center_bp.route('/pending-tasks')
@login_required
def list_pending_tasks():
    """取得我的待簽核任務"""
    from ..models import FwNodeExecutionQueue, FwFormInstance

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    # 查詢等待簽核的節點
    # TODO: 需要加入簽核人過濾邏輯
    tasks = FwNodeExecutionQueue.query.filter(
        FwNodeExecutionQueue.org_secure_code == org.secure_code,
        FwNodeExecutionQueue.status == 'WAITING',
        FwNodeExecutionQueue.node_type.in_(['Approve', 'FormAdapter', 'FORMADAPTER'])
    ).order_by(FwNodeExecutionQueue.scheduled_at.asc()).all()

    result = []
    for task in tasks:
        # 取得表單資訊
        form_instance = FwFormInstance.query.filter_by(
            id=task.form_instance_id
        ).first() if task.form_instance_id else None

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
        'data': result
    })


@form_center_bp.route('/pending-tasks/<secure_code>')
@login_required
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
        return jsonify({'success': False, 'error': '找不到指定的任務'}), 404

    # 取得表單資訊
    form_instance = FwFormInstance.query.filter_by(
        id=task.form_instance_id
    ).first() if task.form_instance_id else None

    # 取得可用路徑
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
            'form_schema': form_instance.schema_snapshot if form_instance else {},
            'form_name': form_instance.form_name if form_instance else None,
            'serial_number': form_instance.serial_number if form_instance else None,
            'applicant_name': form_instance.applicant_name if form_instance else None,
            'available_paths': available_paths,
        }
    })


@form_center_bp.route('/pending-tasks/<secure_code>/approve', methods=['POST'])
@csrf.exempt
@login_required
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
        return jsonify({'success': False, 'error': '找不到任務或已處理'}), 404

    data = request.get_json() or {}
    decision = data.get('decision', 'approved')  # approved, rejected
    selected_path = data.get('selected_path')
    comment = data.get('comment', '')

    try:
        # 建立簽核記錄
        approval_record = FwApprovalRecord(
            secure_code=secrets.token_urlsafe(16),
            org_secure_code=org.secure_code,
            workflow_instance_id=task.workflow_instance_id,
            workflow_instance_secure_code=task.workflow_instance_secure_code,
            form_instance_id=task.form_instance_id,
            form_instance_secure_code=task.form_instance_secure_code,
            node_id=task.node_id,
            approver_secure_code=current_user.secure_code,
            approver_name=current_user.display_name or current_user.username,
            decision=decision,
            selected_path=selected_path,
            comment=comment,
            approved_at=datetime.utcnow(),
        )
        db.session.add(approval_record)

        # 更新任務狀態
        task.status = 'SUCCESS' if decision == 'approved' else 'REJECTED'
        task.completed_at = datetime.utcnow()
        task.result = {
            'decision': decision,
            'selected_path': selected_path,
            'comment': comment,
            'approver': current_user.secure_code
        }

        db.session.commit()

        # 觸發工作流推進
        if decision == 'approved':
            try:
                engine = WorkflowEngine()
                engine.advance_workflow(
                    task.workflow_instance_secure_code,
                    task.node_id,
                    selected_path
                )
            except Exception as e:
                import logging
                logging.error(f'Workflow advance error: {e}')

        return jsonify({
            'success': True,
            'message': '簽核完成' if decision == 'approved' else '已退回'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'簽核失敗: {str(e)}'}), 500


# =============================================================================
# 流程進度
# =============================================================================

@form_center_bp.route('/workflow-progress/<secure_code>')
@login_required
def get_workflow_progress(secure_code):
    """取得流程進度"""
    from ..models import FwWorkflowInstance, FwNodeExecutionQueue, FwApprovalRecord

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    workflow = FwWorkflowInstance.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not workflow:
        return jsonify({'success': False, 'error': '找不到指定的流程'}), 404

    # 取得所有節點執行記錄
    queue_items = FwNodeExecutionQueue.query.filter_by(
        workflow_instance_id=workflow.id
    ).order_by(FwNodeExecutionQueue.scheduled_at.asc()).all()

    # 取得所有簽核記錄
    approvals = FwApprovalRecord.query.filter_by(
        workflow_instance_id=workflow.id
    ).order_by(FwApprovalRecord.approved_at.asc()).all()

    return jsonify({
        'success': True,
        'data': {
            'workflow': {
                'secure_code': workflow.secure_code,
                'execution_code': workflow.execution_code,
                'status': workflow.status,
                'started_at': workflow.started_at.isoformat() if workflow.started_at else None,
                'completed_at': workflow.completed_at.isoformat() if workflow.completed_at else None,
            },
            'nodes': [
                {
                    'node_id': item.node_id,
                    'node_type': item.node_type,
                    'node_name': item.node_name,
                    'status': item.status,
                    'scheduled_at': item.scheduled_at.isoformat() if item.scheduled_at else None,
                    'completed_at': item.completed_at.isoformat() if item.completed_at else None,
                }
                for item in queue_items
            ],
            'approvals': [
                {
                    'node_id': approval.node_id,
                    'approver_name': approval.approver_name,
                    'decision': approval.decision,
                    'comment': approval.comment,
                    'approved_at': approval.approved_at.isoformat() if approval.approved_at else None,
                }
                for approval in approvals
            ]
        }
    })
