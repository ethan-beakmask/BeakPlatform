"""
表單中心 - 取得表單 + 送出表單
"""
import logging
import secrets
from datetime import datetime

from flask import jsonify, request
from flask_login import current_user

from app.security.decorators import module_access_required
from app.platform.data import get_current_org
from app.models import UserNumberingRule
from app.services.numbering_service import NumberingService
from app import db, csrf

from .form_center import form_center_bp

logger = logging.getLogger(__name__)


@form_center_bp.route('/forms/<secure_code>')
@module_access_required('form_workflow', False)
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
@module_access_required('form_workflow', False)
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
            # 測試模式：使用設計稿（需管理員或 design.tryout 權限）
            # ============================================
            from app.platform.auth import has_permission
            can_tryout = (
                getattr(current_user, 'is_org_admin', False) or
                has_permission('form_workflow.design.tryout')
            )
            if not can_tryout:
                return jsonify({'success': False, 'error': '需要試行設計稿權限'}), 403

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

            proc_prefix = 'PROC-'

        # 生成表單序號（三層架構）
        org_form_seq = None

        if is_test_mode:
            # 測試模式：固定 TEST-YYYYMMDD-NNNN 格式
            result = db.session.execute(
                text("""
                    SELECT COALESCE(MAX(CAST(SUBSTRING(serial_number FROM '\\d{4}$') AS INTEGER)), 0) + 1
                    FROM fw_form_instances
                    WHERE serial_number LIKE :pattern
                """),
                {'pattern': f'TEST-{date_str}-%'}
            )
            form_seq = result.scalar() or 1
            serial_number = f"TEST-{date_str}-{str(form_seq).zfill(4)}"
        else:
            # 正式模式：透過萬用編號系統取得企業專屬格式
            # 從 mapping 讀取編號規則（即時生效，不需重新發行）
            form_rule = None
            if published:
                from modules.form_workflow.models import FwFormWorkflowMapping
                mapping_obj = FwFormWorkflowMapping.query.filter_by(
                    secure_code=published.source_mapping_secure_code,
                    is_deleted=False
                ).first()
                if mapping_obj and mapping_obj.numbering_rule_secure_code:
                    form_rule = UserNumberingRule.query.filter_by(
                        secure_code=mapping_obj.numbering_rule_secure_code,
                        org_secure_code=org.secure_code,
                        is_active=True,
                        is_deleted=False
                    ).first()
            if not form_rule:
                form_rule = NumberingService.get_default_rule(
                    org.secure_code, default_for='FORM'
                )
            if form_rule:
                detail = NumberingService.get_next_number_with_detail(
                    form_rule, consume=True
                )
                serial_number = detail['number']
                # org_form_seq 獨立於編號規則，取企業層級最大值 +1
                result = db.session.execute(
                    text("""
                        SELECT COALESCE(MAX(org_form_seq), 0) + 1
                        FROM fw_form_instances
                        WHERE org_secure_code = :osc
                    """),
                    {'osc': org.secure_code}
                )
                org_form_seq = result.scalar() or 1
            else:
                # 無規則 fallback：FORM-YYYYMMDD-NNNNN
                result = db.session.execute(
                    text("""
                        SELECT COALESCE(MAX(CAST(SUBSTRING(serial_number FROM '\\d+$') AS INTEGER)), 0) + 1
                        FROM fw_form_instances
                        WHERE serial_number LIKE :pattern
                    """),
                    {'pattern': f'FORM-{date_str}-%'}
                )
                form_seq = result.scalar() or 1
                serial_number = f"FORM-{date_str}-{str(form_seq).zfill(5)}"

        # 建立表單實例
        form_instance = FwFormInstance(
            secure_code=secrets.token_urlsafe(16),
            org_secure_code=org.secure_code,
            form_template_id=source_form_template_id,
            form_template_secure_code=source_form_template_secure_code,
            published_secure_code=published_sc,
            serial_number=serial_number,
            org_form_seq=org_form_seq,
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
            is_test=is_test_mode,
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
