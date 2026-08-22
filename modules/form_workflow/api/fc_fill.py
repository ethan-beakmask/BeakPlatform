"""
表單中心 - 取得表單 + 送出表單
"""
import logging

from flask import jsonify, request
from flask_login import current_user

from app.security.decorators import module_access_required
from app.platform.data import get_current_org
from app import db, csrf

from .form_center import form_center_bp
from flask_babel import gettext as _

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
        # 測試模式：需 design.tryout 權限（與 submit 測試模式一致）
        from app.platform.auth import has_permission
        can_tryout = has_permission('form_workflow.design.tryout')
        if not can_tryout:
            return jsonify({'success': False, 'error': _('需要試行設計稿權限')}), 403

        # 測試模式：從設計稿取得表單定義
        form_template = FwFormTemplate.query.filter_by(
            secure_code=secure_code,
            org_secure_code=org.secure_code,
            is_deleted=False
        ).first()

        if not form_template:
            return jsonify({'success': False, 'error': _('找不到指定的表單')}), 404

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
            return jsonify({'success': False, 'error': _('找不到指定的表單或已停用')}), 404

        # 驗證填寫權限（與列表/送單同一套 FwMappingPermission 判斷），防 schema 洩漏
        from ..services.fill_permission_service import user_can_fill_mapping
        if not user_can_fill_mapping(
            current_user, org.secure_code,
            published.source_mapping_secure_code,
        ):
            return jsonify({'success': False, 'error': _('您沒有填寫此表單的權限')}), 403

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
    2. 測試模式：使用 mapping_secure_code（設計稿，需 design.tryout 權限）

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
        FwPublishedFormWorkflow, FwFormTemplate, FwWorkflowTemplate,
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
        return jsonify({'success': False, 'error': _('請填寫表單主旨')}), 400

    # 判斷模式
    is_test_mode = bool(mapping_secure_code) and not published_secure_code

    if not published_secure_code and not mapping_secure_code:
        return jsonify({'success': False, 'error': _('缺少 published_secure_code 或 mapping_secure_code')}), 400

    try:
        if is_test_mode:
            # ============================================
            # 測試模式：使用設計稿（需 design.tryout 權限）
            # ============================================
            from app.platform.auth import has_permission
            can_tryout = has_permission('form_workflow.design.tryout')
            if not can_tryout:
                return jsonify({'success': False, 'error': _('需要試行設計稿權限')}), 403

            # 查找配對
            mapping = FwFormWorkflowMapping.query.filter_by(
                secure_code=mapping_secure_code,
                org_secure_code=org.secure_code,
                is_deleted=False
            ).first()

            if not mapping:
                return jsonify({'success': False, 'error': _('找不到指定的配對')}), 404

            # 取得表單設計稿
            form_template = FwFormTemplate.query.filter_by(
                id=mapping.form_template_id,
                is_deleted=False
            ).first()

            if not form_template:
                return jsonify({'success': False, 'error': _('找不到關聯的表單模板')}), 404

            # 取得流程設計稿
            workflow_template = FwWorkflowTemplate.query.filter_by(
                id=mapping.workflow_template_id,
                is_deleted=False
            ).first()

            if not workflow_template:
                return jsonify({'success': False, 'error': _('找不到關聯的流程模板')}), 404

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
                return jsonify({'success': False, 'error': _('找不到指定的表單')}), 404

            if published.status != 'Published':
                return jsonify({'success': False, 'error': _('此表單已停用')}), 400

            # A-1：驗證填寫權限（與表單中心列表同一套 FwMappingPermission 判斷）
            from ..services.fill_permission_service import user_can_fill_mapping
            if not user_can_fill_mapping(
                current_user, org.secure_code,
                published.source_mapping_secure_code,
            ):
                return jsonify({'success': False, 'error': _('您沒有填寫此表單的權限')}), 403

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

        # 序號配發 + 建實例 + 啟動流程（共用 service，與外部發動閘道一致）
        from ..services.form_submit_service import (
            allocate_serial_number, create_instance_and_start, SubmitError,
        )

        serial_number, org_form_seq = allocate_serial_number(
            org.secure_code, is_test_mode,
            published=(None if is_test_mode else published),
        )

        try:
            form_instance, workflow_instance = create_instance_and_start(
                org_secure_code=org.secure_code,
                serial_number=serial_number,
                org_form_seq=org_form_seq,
                subject=subject,
                form_data=form_data,
                is_test=is_test_mode,
                source_type='WEB',
                source_ip=request.remote_addr,
                form_name=form_name,
                form_code=form_code,
                form_version=form_version,
                form_schema=form_schema,
                form_builder_config=form_builder_config,
                workflow_name=workflow_name,
                workflow_version=workflow_version,
                workflow_graph=workflow_graph,
                source_form_template_id=source_form_template_id,
                source_form_template_secure_code=source_form_template_secure_code,
                source_workflow_template_id=source_workflow_template_id,
                source_workflow_template_secure_code=source_workflow_template_secure_code,
                published_sc=published_sc,
                proc_prefix=proc_prefix,
                applicant_secure_code=current_user.secure_code,
                applicant_name=current_user.display_name or current_user.username,
                applicant_username=current_user.username,
                applicant_email=getattr(current_user, 'email', None),
                applicant_dept=getattr(current_user, 'department_name', None),
            )
        except SubmitError as exc:
            return jsonify({'success': False, 'error': str(exc)}), 400

        # SQL Sync：不在送出時同步，改在流程結束時由 workflow_engine 觸發

        return jsonify({
            'success': True,
            'message': _('表單已送出，流程已啟動（測試模式）') if is_test_mode else _('表單已送出，流程已啟動'),
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
        return jsonify({'success': False, 'error': _('建立失敗: %(error)s', error=str(e))}), 500
