"""
表單中心 - 我的表單
"""
from flask import jsonify, request
from flask_login import current_user

from app.security.decorators import module_access_required
from app.platform.data import get_current_org
from app import db

from .form_center import form_center_bp
from flask_babel import gettext as _


@form_center_bp.route('/my-forms')
@module_access_required('form_workflow', False)
def list_my_forms():
    """
    取得我提交/簽核過的表單列表

    Query Parameters:
    - status: 篩選流程狀態，支援逗號分隔多值（如 status=COMPLETED,ERROR）
              對應的是 workflow_instance 的狀態
    - signed: 若為 1，顯示我簽核過的表單（而非我提交的表單）
    - limit: 回傳筆數上限（預設 50）
    """
    from ..models import FwFormInstance, FwWorkflowInstance, FwApprovalRecord, FwFormTemplate, FwPublishedFormWorkflow
    from sqlalchemy.orm import aliased

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    # 篩選條件
    status = request.args.get('status')
    signed = request.args.get('signed', '0')
    limit = request.args.get('limit', 500, type=int)
    sort_field = request.args.get('sort', 'created_at')
    sort_order = request.args.get('order', 'desc')

    FT = aliased(FwFormTemplate)
    P = aliased(FwPublishedFormWorkflow)

    # 建立基礎查詢（JOIN workflow_instance + outerjoin form_template 取 category + outerjoin published 取 publish_version）
    base_query = db.session.query(
        FwFormInstance, FwWorkflowInstance, FT.category, FT.category_secure_code, P.publish_version
    ).join(
        FwWorkflowInstance,
        FwFormInstance.workflow_instance_secure_code == FwWorkflowInstance.secure_code
    ).outerjoin(
        FT,
        FwFormInstance.form_template_id == FT.id
    ).outerjoin(
        P,
        FwFormInstance.published_secure_code == P.secure_code
    ).filter(
        FwFormInstance.org_secure_code == org.secure_code,
        FwFormInstance.is_deleted == False
    )

    # 資安分類隔離：資安案件不在一般表單中心顯示（NULL 分類為一般表單，保留）
    from ..services.security_center import SECURITY_CATEGORY_PREFIX
    base_query = base_query.filter(
        db.or_(
            FT.category_secure_code.is_(None),
            ~FT.category_secure_code.like(f'{SECURITY_CATEGORY_PREFIX}%'),
        )
    )

    if signed == '1':
        # 查詢我簽核過的表單（使用 secure_code），排除自己發起的
        signed_form_codes = db.session.query(FwApprovalRecord.form_instance_secure_code).filter(
            FwApprovalRecord.org_secure_code == org.secure_code,
            FwApprovalRecord.approver_secure_code == current_user.secure_code
        ).distinct().subquery()

        base_query = base_query.filter(
            FwFormInstance.secure_code.in_(signed_form_codes),
            FwFormInstance.applicant_secure_code != current_user.secure_code
        )
    else:
        # 查詢我提交的表單
        base_query = base_query.filter(
            FwFormInstance.applicant_secure_code == current_user.secure_code
        )

    # 根據流程狀態篩選（使用 workflow_instance.status）
    if status:
        status_list = [s.strip() for s in status.split(',') if s.strip()]
        if len(status_list) == 1:
            base_query = base_query.filter(FwWorkflowInstance.status == status_list[0])
        elif len(status_list) > 1:
            base_query = base_query.filter(FwWorkflowInstance.status.in_(status_list))

    # 動態排序
    sort_column_map = {
        'serial_number': FwFormInstance.serial_number,
        'submitted_at': FwFormInstance.submitted_at,
        'workflow_completed_at': FwWorkflowInstance.completed_at,
        'created_at': FwFormInstance.created_at,
    }
    sort_col = sort_column_map.get(sort_field, FwFormInstance.created_at)
    if sort_order == 'asc':
        base_query = base_query.order_by(sort_col.asc())
    else:
        base_query = base_query.order_by(sort_col.desc())

    rows = base_query.limit(limit).all()

    # 取得所有流程的當前等待節點（用於顯示「待簽關卡」）
    from ..models import FwNodeExecutionQueue
    workflow_secure_codes = [w.secure_code for f, w, _, _, _ in rows]
    waiting_nodes = {}
    if workflow_secure_codes:
        waiting_items = FwNodeExecutionQueue.query.filter(
            FwNodeExecutionQueue.workflow_instance_secure_code.in_(workflow_secure_codes),
            FwNodeExecutionQueue.status == 'WAITING'
        ).all()
        for item in waiting_items:
            waiting_nodes[item.workflow_instance_secure_code] = item.node_name

    # signed=1 時批次查 FwApprovalRecord 取當前用戶的 acted_at
    acted_at_map = {}
    if signed == '1':
        form_scs = [f.secure_code for f, w, _, _, _ in rows]
        if form_scs:
            acted_records = FwApprovalRecord.query.filter(
                FwApprovalRecord.form_instance_secure_code.in_(form_scs),
                FwApprovalRecord.approver_secure_code == current_user.secure_code
            ).all()
            # 每張表單取最後一次簽核時間
            for rec in acted_records:
                existing = acted_at_map.get(rec.form_instance_secure_code)
                if not existing or (rec.acted_at and rec.acted_at > existing):
                    acted_at_map[rec.form_instance_secure_code] = rec.acted_at

    # 判斷當前用戶是否為管理員（用於 can_force_end 判斷）
    is_org_admin = getattr(current_user, 'is_org_admin', False)

    # 組裝結果
    result = []
    for form_instance, workflow_instance, ft_category, ft_category_sc, pub_version in rows:
        data = form_instance.to_dict(include_form_data=False)
        data['is_test'] = form_instance.is_test
        # 附加流程資訊
        data['workflow_status'] = workflow_instance.status
        data['execution_code'] = workflow_instance.execution_code
        data['workflow_name'] = workflow_instance.workflow_name
        data['workflow_instance_secure_code'] = workflow_instance.secure_code
        # 當前等待的簽核關卡
        data['current_approver'] = waiting_nodes.get(workflow_instance.secure_code, None)
        # 新增欄位
        data['category'] = ft_category
        data['category_secure_code'] = ft_category_sc
        data['form_subject'] = form_instance.subject or ''
        data['workflow_started_at'] = workflow_instance.started_at.isoformat() if workflow_instance.started_at else None
        data['workflow_completed_at'] = workflow_instance.completed_at.isoformat() if workflow_instance.completed_at else None
        # 版本資訊
        data['workflow_version'] = workflow_instance.workflow_version
        data['publish_version'] = pub_version
        # 強制結束權限：RUNNING 狀態 + (發起人 or 管理員)
        data['can_force_end'] = (
            workflow_instance.status == 'RUNNING' and (
                form_instance.applicant_secure_code == current_user.secure_code
                or is_org_admin
            )
        )
        if signed == '1':
            acted = acted_at_map.get(form_instance.secure_code)
            data['my_acted_at'] = acted.isoformat() if acted else None
        result.append(data)

    return jsonify({
        'success': True,
        'data': result
    })


@form_center_bp.route('/my-forms/<secure_code>')
@module_access_required('form_workflow', False)
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
        return jsonify({'success': False, 'error': _('找不到指定的表單')}), 404

    return jsonify({
        'success': True,
        'data': instance.to_dict(include_form_data=True)
    })
