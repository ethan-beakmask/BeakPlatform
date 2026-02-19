"""
FormWorkflow Module - Form Center API
表單中心 API

提供一般用戶填寫表單、發起流程、查看進度等功能。
"""
import logging
import secrets
from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_login import current_user

from app.security.decorators import login_required
from app.platform.data import get_current_org
from app import db, csrf

logger = logging.getLogger(__name__)


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

    # 預先載入分類映射（category_secure_code → parent info）
    from ..models import FwCategory
    all_cats = FwCategory.query.filter_by(is_deleted=False).filter(
        db.or_(
            FwCategory.org_secure_code.is_(None),
            FwCategory.org_secure_code == org.secure_code
        )
    ).all()
    cat_map = {c.secure_code: c for c in all_cats}

    def _enrich_category(item, cat_sc):
        """補充分類資訊到 item"""
        item['category_secure_code'] = cat_sc
        cat = cat_map.get(cat_sc) if cat_sc else None
        if cat and cat.parent_secure_code:
            parent = cat_map.get(cat.parent_secure_code)
            item['parent_category_secure_code'] = cat.parent_secure_code
            item['parent_category_name'] = parent.name if parent else ''
            item['child_category_name'] = cat.name
        elif cat:
            item['parent_category_secure_code'] = cat.secure_code
            item['parent_category_name'] = cat.name
            item['child_category_name'] = None
        else:
            item['parent_category_secure_code'] = None
            item['parent_category_name'] = None
            item['child_category_name'] = None

    result = []
    seen_mapping_ids = set()
    need_category_ids = []  # 需要 fallback 查 category 的 form_template_id

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
        category = form_snapshot.get('category')
        cat_sc = form_snapshot.get('category_secure_code')

        item = {
            'id': p.source_form_template_id,
            'secure_code': p.secure_code,
            'name': form_snapshot.get('name') or p.name,
            'description': form_snapshot.get('description') or p.description,
            'category': category,
            'code': form_snapshot.get('code'),
            'version': form_snapshot.get('version'),
            'publish_version': p.publish_version,
            'published_at': p.published_at.isoformat() if p.published_at else None,
            'workflow_template_name': workflow_snapshot.get('name'),
            'mapping_id': mapping_id,
            '_status': 'published',
            '_source': 'published',
        }

        # 嘗試從快照取 category_secure_code
        if cat_sc:
            _enrich_category(item, cat_sc)
        else:
            # fallback 待後面批次處理
            item['category_secure_code'] = None
            item['parent_category_secure_code'] = None
            item['parent_category_name'] = None
            item['child_category_name'] = None
            if p.source_form_template_id:
                need_category_ids.append((len(result), p.source_form_template_id))

        result.append(item)

    # category fallback: 快照沒有 category_secure_code 時查 FwFormTemplate
    if need_category_ids:
        ft_ids = list(set(fid for _, fid in need_category_ids))
        templates = FwFormTemplate.query.filter(
            FwFormTemplate.id.in_(ft_ids)
        ).all()
        ft_map = {t.id: t for t in templates}
        for idx, ft_id in need_category_ids:
            ft = ft_map.get(ft_id)
            if ft:
                result[idx]['category'] = ft.category
                _enrich_category(result[idx], ft.category_secure_code)

    # 2. 管理員額外顯示未發行的配對（用於測試）
    if is_admin:
        mappings = FwFormWorkflowMapping.query.filter_by(
            org_secure_code=org.secure_code,
            is_active=True,
            is_deleted=False
        ).order_by(FwFormWorkflowMapping.created_at.desc()).all()

        for mapping in mappings:
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

            item = {
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
            }
            _enrich_category(item, form_template.category_secure_code)
            result.append(item)

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
    subject = (data.get('subject') or '').strip()

    if not subject:
        return jsonify({'success': False, 'error': '請填寫表單主旨'}), 400

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
            form_builder_config = form_template.builder_config
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
            form_builder_config = form_snapshot.get('builder_config')
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
            subject=subject,
            form_data=form_data,
            schema_snapshot=form_schema,
            builder_config=form_builder_config,
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

        # SQL Sync：不在送出時同步，改在流程結束時由 workflow_engine 觸發

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
        data['is_test'] = data.get('serial_number', '').startswith('TEST-')
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
# 欄位權限處理
# =============================================================================

def _apply_field_permissions_to_schema(schema, role_permissions):
    """
    根據欄位權限修改 form.io schema

    role_permissions: {"field_key": "hidden"|"readonly"|"editable", ...}
    未配置的欄位預設為 readonly

    Returns: (modified_schema, has_editable)
    """
    import copy
    schema = copy.deepcopy(schema)
    has_editable = False

    def process_components(components):
        nonlocal has_editable
        result = []
        for comp in components:
            comp = dict(comp)

            # 處理容器元件 (panel, columns, fieldset, tabs, well 等)
            if 'components' in comp:
                comp['components'] = process_components(comp['components'])
                result.append(comp)
                continue

            # 處理 columns 元件
            if 'columns' in comp:
                for col in comp.get('columns', []):
                    if 'components' in col:
                        col['components'] = process_components(col['components'])
                result.append(comp)
                continue

            key = comp.get('key')
            if not key:
                result.append(comp)
                continue

            perm = role_permissions.get(key, 'readonly')

            if perm == 'hidden':
                # 跳過此欄位 (不加入結果)
                continue
            elif perm == 'editable':
                comp['disabled'] = False
                has_editable = True
                result.append(comp)
            else:
                # readonly (預設)
                comp['disabled'] = True
                result.append(comp)

        return result

    if schema.get('components'):
        schema['components'] = process_components(schema['components'])

    return schema, has_editable


# =============================================================================
# 待簽核任務
# =============================================================================

@form_center_bp.route('/pending-tasks')
@login_required
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
            'is_test': serial_number.startswith('TEST-') if serial_number else False,
            'form_subject': form_subject,
            'category': category,
            'category_secure_code': category_sc,
            'form_instance_secure_code': fi.secure_code if fi else None,
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
@login_required
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
        return jsonify({'success': False, 'error': '找不到指定的任務'}), 404

    # 檢查當前用戶是否為指定簽核人
    task_result_data = (task.result or {}).get('data', {})
    assignee_type = task_result_data.get('assignee_type')
    assignees = task_result_data.get('assignees', [])
    if assignee_type and current_user.secure_code not in assignees:
        return jsonify({'success': False, 'error': '您不是此任務的指定簽核人'}), 403

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
            'form_data': form_instance.form_data if form_instance else {},
            'form_schema': form_schema,
            'form_name': form_instance.form_name if form_instance else None,
            'form_subject': form_instance.subject if form_instance else None,
            'serial_number': form_instance.serial_number if form_instance else None,
            'applicant_name': form_instance.applicant_name if form_instance else None,
            'builder_config': form_instance.builder_config if form_instance else None,
            'available_paths': available_paths,
            'selection_mode': selection_mode,
            'allow_comment': allow_comment,
            'require_comment': require_comment,
            'min_comment_length': min_comment_length,
            'approvals': approvals,
            'field_permissions': role_permissions,
            'has_editable_fields': has_editable,
            'user_role': user_role,
        }
    })


@form_center_bp.route('/pending-tasks/<secure_code>/lock', methods=['POST'])
@csrf.exempt
@login_required
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
            return jsonify({'success': False, 'error': '找不到任務或已處理'}), 404

        # 檢查當前用戶是否為指定簽核人
        task_result_data = (task.result or {}).get('data', {})
        assignee_type = task_result_data.get('assignee_type')
        assignees = task_result_data.get('assignees', [])
        if assignee_type and current_user.secure_code not in assignees:
            return jsonify({'success': False, 'error': '您不是此任務的指定簽核人'}), 403

        # 檢查是否已被鎖定
        if task.is_locked:
            if task.locked_by == current_user.secure_code:
                # 同一人重複取鎖：刷新鎖定時間
                task.acquire_lock(current_user.secure_code)
                db.session.commit()
                return jsonify({
                    'success': True,
                    'message': '鎖定已刷新',
                    'remaining_seconds': task.lock_remaining_seconds
                })
            else:
                # 被他人鎖定：查詢鎖定者資訊
                locker = User.query.filter_by(secure_code=task.locked_by).first()
                locker_display = locker.employee_id or locker.display_name or locker.username if locker else '未知'
                return jsonify({
                    'success': False,
                    'error': f'此表單由 {locker_display} 簽核中',
                    'locked_by_display': locker_display,
                    'code': 'LOCKED'
                }), 409

        # 取得鎖定
        task.acquire_lock(current_user.secure_code)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': '已取得簽核鎖定',
            'remaining_seconds': task.lock_remaining_seconds
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f'取得簽核鎖定失敗: {e}')
        return jsonify({'success': False, 'error': f'取得鎖定失敗: {str(e)}'}), 500


@form_center_bp.route('/pending-tasks/<secure_code>/lock', methods=['DELETE'])
@csrf.exempt
@login_required
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
            return jsonify({'success': False, 'error': '找不到任務'}), 404

        # 只有鎖定者可以釋放
        if task.locked_by == current_user.secure_code:
            task.release_lock()
            db.session.commit()

        return jsonify({'success': True, 'message': '鎖定已釋放'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@form_center_bp.route('/pending-tasks/<secure_code>/approve', methods=['POST'])
@csrf.exempt
@login_required
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
            return jsonify({'success': False, 'error': '找不到任務或已處理'}), 404

        # 檢查當前用戶是否為指定簽核人
        task_result_data = (task.result or {}).get('data', {})
        assignee_type = task_result_data.get('assignee_type')
        assignees = task_result_data.get('assignees', [])
        if assignee_type and current_user.secure_code not in assignees:
            return jsonify({'success': False, 'error': '您不是此任務的指定簽核人'}), 403

        # 驗證鎖定持有者：必須是當前用戶且未逾時
        if task.is_locked and task.locked_by != current_user.secure_code:
            return jsonify({
                'success': False,
                'error': '此表單正由他人簽核中',
                'code': 'LOCKED'
            }), 409

        if task.locked_by == current_user.secure_code and not task.is_locked:
            return jsonify({
                'success': False,
                'error': '簽核逾時，鎖定已失效，請重新開啟',
                'code': 'LOCK_EXPIRED'
            }), 409

        # P1: 防止同一人重複簽核同一節點
        existing_approval = FwApprovalRecord.query.filter_by(
            workflow_instance_secure_code=task.workflow_instance_secure_code,
            node_id=task.node_id,
            approver_secure_code=current_user.secure_code
        ).filter(FwApprovalRecord.action.in_(['approved', 'rejected'])).first()

        if existing_approval:
            return jsonify({
                'success': False,
                'error': '您已簽核過此節點，無法重複簽核',
                'code': 'DUPLICATE'
            }), 409

        data = request.get_json() or {}
        decision = data.get('decision', 'approved')
        selected_path = data.get('selected_path')
        comment = data.get('comment', '')
        updated_form_data = data.get('form_data')

        # 驗證簽核意見最少字數
        min_comment_length = task_result_data.get('min_comment_length', 0)
        if min_comment_length > 0 and len(comment.strip()) < min_comment_length:
            return jsonify({'success': False, 'error': f'簽核意見至少需要 {min_comment_length} 字'}), 400

        # 處理表單欄位修改
        from ..models import FwFormInstance, FwFormFieldChange
        node_config = task.node_config or {}
        field_permissions = node_config.get('field_permissions', {})
        approver_permissions = field_permissions.get('approver', {})

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
                            'error': f'欄位 {field_key} 不允許修改'
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
            approver_secure_code=current_user.secure_code,
            approver_name=current_user.display_name or current_user.username,
            action=decision,
            comment=comment,
            acted_at=datetime.utcnow(),
        )
        db.session.add(approval_record)

        # 更新任務狀態 + 釋放鎖定
        task.status = 'SUCCESS' if decision == 'approved' else 'REJECTED'
        task.completed_at = datetime.utcnow()
        task.result = {
            'decision': decision,
            'selected_path': selected_path,
            'comment': comment,
            'approver': current_user.secure_code
        }
        task.release_lock()

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
                logger.error(f'Workflow advance error: {e}')

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

    # 取得所有節點執行記錄（使用 secure_code）
    queue_items = FwNodeExecutionQueue.query.filter_by(
        workflow_instance_secure_code=workflow.secure_code
    ).order_by(FwNodeExecutionQueue.scheduled_at.asc()).all()

    # 取得所有簽核記錄（使用 secure_code）
    approvals = FwApprovalRecord.query.filter_by(
        workflow_instance_secure_code=workflow.secure_code
    ).order_by(FwApprovalRecord.acted_at.asc()).all()

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


@form_center_bp.route('/form-detail/<secure_code>')
@login_required
def get_form_detail(secure_code):
    """
    取得表單詳情（用於歷史表單查看）

    包含：表單內容、schema、簽核歷史
    """
    from ..models import FwFormInstance, FwWorkflowInstance, FwApprovalRecord

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
        return jsonify({'success': False, 'error': '找不到指定的表單'}), 404

    # 取得簽核歷史
    approvals = []
    if form_instance.workflow_instance_secure_code:
        approval_records = FwApprovalRecord.query.filter_by(
            workflow_instance_secure_code=form_instance.workflow_instance_secure_code
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
            'secure_code': form_instance.secure_code,
            'serial_number': form_instance.serial_number,
            'form_name': form_instance.form_name,
            'form_subject': form_instance.subject,
            'form_code': form_instance.form_code,
            'status': form_instance.status,
            'applicant_name': form_instance.applicant_name,
            'applicant_dept': form_instance.applicant_dept,
            'submitted_at': form_instance.submitted_at.isoformat() if form_instance.submitted_at else None,
            'completed_at': form_instance.completed_at.isoformat() if form_instance.completed_at else None,
            'form_data': form_instance.form_data,
            'schema': form_instance.schema_snapshot,
            'builder_config': form_instance.builder_config,
            'approvals': approvals
        }
    })


# =============================================================================
# 強制結束流程
# =============================================================================

@form_center_bp.route('/force-end/<secure_code>', methods=['POST'])
@csrf.exempt
@login_required
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
        return jsonify({'success': False, 'error': '找不到指定的表單'}), 404

    # 查詢流程實例
    workflow_instance = FwWorkflowInstance.query.filter_by(
        secure_code=form_instance.workflow_instance_secure_code,
        org_secure_code=org.secure_code
    ).first()

    if not workflow_instance:
        return jsonify({'success': False, 'error': '找不到關聯的流程'}), 404

    # 權限檢查：發起人 or 管理員
    is_applicant = form_instance.applicant_secure_code == current_user.secure_code
    is_admin = getattr(current_user, 'is_org_admin', False)
    if not is_applicant and not is_admin:
        return jsonify({'success': False, 'error': '無權限執行此操作'}), 403

    # 狀態檢查
    if workflow_instance.status != 'RUNNING':
        return jsonify({'success': False, 'error': f'流程狀態為 {workflow_instance.status}，無法強制結束'}), 400

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
            'message': '流程已強制結束'
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f'強制結束流程失敗: {e}')
        return jsonify({'success': False, 'error': f'操作失敗: {str(e)}'}), 500


# =============================================================================
# 批量刪除測試表單
# =============================================================================

@form_center_bp.route('/my-test-forms', methods=['DELETE'])
@csrf.exempt
@login_required
def delete_my_test_forms():
    """
    批量 soft delete 當前用戶的測試表單（歷史終態）

    權限：管理員（system_admin 或 org_admin）
    條件：is_test=True, 終態, 本人發起, 未刪除
    """
    from ..models import FwFormInstance, FwWorkflowInstance

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    # 權限：僅管理員可操作
    is_admin = (
        getattr(current_user, 'is_system_admin', False) or
        getattr(current_user, 'level', 0) >= 90
    )
    if not is_admin:
        return jsonify({'success': False, 'error': '無權限執行此操作'}), 403

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
        return jsonify({'success': True, 'deleted_count': 0, 'message': '沒有可刪除的測試表單'})

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
            'message': f'已刪除 {deleted_count} 筆測試表單'
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f'批量刪除測試表單失敗: {e}')
        return jsonify({'success': False, 'error': f'操作失敗: {str(e)}'}), 500


# =============================================================================
# 流程執行追蹤（監控用）
# =============================================================================

@form_center_bp.route('/executions/<instance_id>/path')
@login_required
def get_execution_path(instance_id):
    """
    取得流程執行路徑（用於監控與追蹤）

    Args:
        instance_id: 工作流實例 secure_code 或 execution_code

    Returns:
        JSON: {
            "success": true,
            "data": {
                "active_nodes": ["node-1"],          # 執行中
                "completed_nodes": ["node-start"],   # 已完成
                "failed_nodes": [],                  # 失敗
                "pending_nodes": [],                 # 待執行
                "active_paths": ["edge-1"],          # 活動路徑
                "instance_status": "RUNNING",        # 流程狀態
                "execution_history": [...],          # 執行歷程
                "workflow_tabs": [...]               # 流程分頁（主流程+子流程）
            }
        }
    """
    from ..models import FwWorkflowInstance, FwNodeExecutionQueue, FwFormInstance
    from sqlalchemy import or_, func

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    # 查詢流程實例（支援 secure_code 或 execution_code）
    instance = FwWorkflowInstance.query.filter(
        FwWorkflowInstance.org_secure_code == org.secure_code,
        or_(
            FwWorkflowInstance.secure_code == instance_id,
            FwWorkflowInstance.execution_code == instance_id
        )
    ).first()

    if not instance:
        return jsonify({'success': False, 'error': f'流程實例 {instance_id} 不存在'}), 404

    # 查詢此流程實例的所有節點執行記錄
    nodes = FwNodeExecutionQueue.query.filter_by(
        workflow_instance_secure_code=instance.secure_code
    ).all()

    # 分類節點狀態
    active_nodes = [n.node_id for n in nodes if n.status == 'RUNNING']
    completed_nodes = [n.node_id for n in nodes if n.status == 'SUCCESS']
    failed_nodes = [n.node_id for n in nodes if n.status in ('FAILED', 'ERROR', 'TIMEOUT')]
    pending_nodes = [n.node_id for n in nodes if n.status == 'PENDING']
    waiting_nodes = [n.node_id for n in nodes if n.status == 'WAITING']

    # 計算活動路徑（已完成 → 執行中/等待中的連線）
    active_paths = []
    graph = instance.graph_snapshot or {}
    if graph:
        edges = graph.get('edges', [])
        for edge in edges:
            source = edge.get('source')
            target = edge.get('target')
            edge_id = edge.get('id')
            if (source in completed_nodes and
                (target in active_nodes or target in waiting_nodes or target in pending_nodes)):
                active_paths.append(edge_id)

    # 查詢執行歷程（同一表單實例的所有節點記錄，包含子流程）
    # 依 started_at 排序以呈現真實執行順序
    execution_history = FwNodeExecutionQueue.query.filter_by(
        form_instance_secure_code=instance.form_instance_secure_code
    ).order_by(
        func.coalesce(FwNodeExecutionQueue.started_at, FwNodeExecutionQueue.scheduled_at).asc()
    ).all()

    # 收集所有相關的 workflow_instance（主流程 + 子流程）
    workflow_instance_codes = list(set([item.workflow_instance_secure_code for item in execution_history]))
    workflow_instances = FwWorkflowInstance.query.filter(
        FwWorkflowInstance.secure_code.in_(workflow_instance_codes)
    ).all()

    # 建立映射表
    workflow_map = {wi.secure_code: wi for wi in workflow_instances}

    # 準備 workflow_tabs（流程分頁）
    workflow_tabs = []
    for wi in workflow_instances:
        # 計算該流程的狀態
        sub_nodes = [n for n in execution_history if n.workflow_instance_secure_code == wi.secure_code]
        has_running = any(n.status == 'RUNNING' for n in sub_nodes)
        has_failed = any(n.status in ('FAILED', 'ERROR', 'TIMEOUT') for n in sub_nodes)
        has_waiting = any(n.status == 'WAITING' for n in sub_nodes)
        all_completed = all(n.status == 'SUCCESS' for n in sub_nodes) if sub_nodes else False

        if has_running:
            tab_status = 'RUNNING'
        elif has_failed:
            tab_status = 'ERROR'
        elif has_waiting:
            tab_status = 'WAITING'
        elif all_completed:
            tab_status = 'COMPLETED'
        else:
            tab_status = 'INITIAL'

        workflow_tabs.append({
            'instance_id': wi.secure_code,
            'secure_code': wi.secure_code,
            'execution_code': wi.execution_code,
            'name': wi.workflow_name or '未命名流程',
            'is_main': wi.secure_code == instance.secure_code,
            'status': tab_status,
            'graph': wi.graph_snapshot
        })

    # 確保主流程排在最前面
    workflow_tabs.sort(key=lambda x: (not x['is_main'], x.get('execution_code', '')))

    # 轉換執行歷程為前端格式
    history_data = []
    for queue_item in execution_history:
        wi = workflow_map.get(queue_item.workflow_instance_secure_code)
        is_subprocess = queue_item.calling_instance_code is not None
        workflow_name = wi.workflow_name if wi else '未知流程'

        history_data.append({
            'node_id': queue_item.node_id,
            'node_name': queue_item.node_name or queue_item.node_id,
            'display_name': queue_item.node_name or '',
            'node_type': queue_item.node_type,
            'status': queue_item.status,
            'scheduled_at': queue_item.scheduled_at.isoformat() if queue_item.scheduled_at else None,
            'started_at': queue_item.started_at.isoformat() if queue_item.started_at else None,
            'completed_at': queue_item.completed_at.isoformat() if queue_item.completed_at else None,
            'error_message': queue_item.error_message,
            'retry_count': queue_item.retry_count or 0,
            'is_subprocess': is_subprocess,
            'workflow_name': workflow_name,
            'workflow_instance_id': queue_item.workflow_instance_secure_code
        })

    return jsonify({
        'success': True,
        'data': {
            'active_nodes': active_nodes,
            'completed_nodes': completed_nodes,
            'failed_nodes': failed_nodes,
            'pending_nodes': pending_nodes,
            'waiting_nodes': waiting_nodes,
            'active_paths': active_paths,
            'instance_status': instance.status,
            'current_node_id': instance.current_node_id,
            'execution_history': history_data,
            'workflow_tabs': workflow_tabs
        }
    })


@form_center_bp.route('/executions/<instance_id>/logs')
@login_required
def get_execution_logs(instance_id):
    """
    取得流程執行日誌（用於 Debug 和追蹤）

    Args:
        instance_id: 工作流實例 secure_code 或 execution_code

    Query Params:
        level: 過濾日誌等級 (INFO, WARNING, ERROR, DEBUG)
        limit: 限制筆數，預設 500

    Returns:
        JSON: {
            "success": true,
            "data": {
                "instance": {...},
                "logs": [...],
                "variables": {...}
            }
        }
    """
    from ..models import (
        FwWorkflowInstance, FwNodeExecutionLog,
        FwWorkflowVariable, FwNodeExecutionQueue
    )
    from sqlalchemy import or_

    logger.info(f'[LOGS API] 查詢執行日誌: instance_id={instance_id}')

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    # 查詢流程實例（支援 secure_code 或 execution_code）
    instance = FwWorkflowInstance.query.filter(
        FwWorkflowInstance.org_secure_code == org.secure_code,
        or_(
            FwWorkflowInstance.secure_code == instance_id,
            FwWorkflowInstance.execution_code == instance_id
        )
    ).first()

    if not instance:
        return jsonify({'success': False, 'error': f'流程實例 {instance_id} 不存在'}), 404

    # 取得查詢參數
    level_filter = request.args.get('level')
    limit = request.args.get('limit', 500, type=int)

    # 取得所有相關的流程實例（主流程 + 子流程）
    # 使用 root_instance_code 或 form_instance_secure_code 來查詢整個流程樹
    all_instances = FwWorkflowInstance.query.filter(
        FwWorkflowInstance.org_secure_code == org.secure_code,
        FwWorkflowInstance.form_instance_secure_code == instance.form_instance_secure_code
    ).all()

    all_instance_ids = [wi.id for wi in all_instances]
    all_instance_codes = [wi.secure_code for wi in all_instances]
    logger.info(f'[LOGS API] 找到 {len(all_instances)} 個相關流程實例, IDs: {all_instance_ids}')

    # 建立 workflow_instance_id -> workflow_name 映射
    workflow_name_map = {}
    for wi in all_instances:
        workflow_name_map[wi.id] = wi.workflow_name or '未命名流程'
        workflow_name_map[wi.secure_code] = wi.workflow_name or '未命名流程'

    # 取得節點顯示名稱映射（從執行佇列）
    node_display_names = {}  # key: (workflow_instance_secure_code, node_id)
    queue_items = FwNodeExecutionQueue.query.filter(
        FwNodeExecutionQueue.workflow_instance_secure_code.in_(all_instance_codes)
    ).all()
    for item in queue_items:
        key = (item.workflow_instance_secure_code, item.node_id)
        node_display_names[key] = item.node_name or item.node_id

    # 查詢執行日誌
    log_query = FwNodeExecutionLog.query.filter(
        FwNodeExecutionLog.workflow_instance_id.in_(all_instance_ids)
    )
    if level_filter:
        log_query = log_query.filter(FwNodeExecutionLog.log_level == level_filter.upper())
    log_query = log_query.order_by(
        FwNodeExecutionLog.created_at.asc()
    ).limit(limit)

    logs = []
    log_results = log_query.all()
    logger.info(f'[LOGS API] 查詢到 {len(log_results)} 筆日誌')
    for log in log_results:
        # 找到對應的 workflow instance
        wi = next((w for w in all_instances if w.id == log.workflow_instance_id), None)
        workflow_name = wi.workflow_name if wi else '未知流程'
        node_id = log.node_id or ''

        # 嘗試取得節點顯示名稱
        display_name_key = (wi.secure_code if wi else '', node_id)
        display_name = node_display_names.get(display_name_key, node_id.replace('node-', '') if node_id else '')

        logs.append({
            'timestamp': log.created_at.strftime('%Y-%m-%d %H:%M:%S') if log.created_at else '',
            'level': log.log_level or 'INFO',
            'node_id': node_id,
            'workflow_instance_id': wi.secure_code if wi else None,
            'workflow_name': workflow_name,
            'display_name': display_name,
            'message': log.log_message or '',
            'data': log.log_data if log.log_data else None
        })

    # 查詢所有相關流程的變數值（只取 GLOBAL 範圍）
    # 注意：資料庫實際欄位是 workflow_instance_secure_code 和 var_type
    variables = {}
    vars_query = FwWorkflowVariable.query.filter(
        FwWorkflowVariable.workflow_instance_secure_code.in_(all_instance_codes),
        FwWorkflowVariable.var_type == 'GLOBAL'
    ).all()
    logger.info(f'[LOGS API] 查詢到 {len(vars_query)} 個變數')
    for v in vars_query:
        # 使用 workflow_name::var_name 格式區分不同流程的變數
        wi = next((w for w in all_instances if w.secure_code == v.workflow_instance_secure_code), None)
        wf_name = wi.workflow_name if wi else ''
        var_key = f"{wf_name}::{v.var_name}" if wf_name and v.workflow_instance_secure_code != instance.secure_code else v.var_name
        variables[var_key] = v.var_value

    return jsonify({
        'success': True,
        'data': {
            'instance': {
                'secure_code': instance.secure_code,
                'execution_code': instance.execution_code,
                'status': instance.status,
                'started_at': instance.started_at.strftime('%Y-%m-%d %H:%M:%S') if instance.started_at else None,
                'completed_at': instance.completed_at.strftime('%Y-%m-%d %H:%M:%S') if instance.completed_at else None,
                'template_name': instance.workflow_name
            },
            'logs': logs,
            'variables': variables
        }
    })
