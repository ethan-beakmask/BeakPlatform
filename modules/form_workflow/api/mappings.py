"""
FormWorkflow Module - Mappings API
表單-流程配對 API

提供表單與工作流配對管理、發行等功能。
"""
import secrets
from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_login import current_user

from app.security.decorators import login_required
from app.platform.data import get_current_org
from app import db, csrf

# 建立 API Blueprint
mappings_bp = Blueprint(
    'form_workflow_mappings',
    __name__,
    url_prefix='/api/mappings'
)


# =============================================================================
# 配對管理 API
# =============================================================================

@mappings_bp.route('')
@mappings_bp.route('/')
@login_required
def list_mappings():
    """取得配對列表"""
    from ..models import FwFormWorkflowMapping

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    query = FwFormWorkflowMapping.query.filter_by(
        org_secure_code=org.secure_code,
        is_deleted=False
    )

    # 篩選條件
    form_id = request.args.get('form_template_id', type=int)
    if form_id:
        query = query.filter_by(form_template_id=form_id)

    workflow_id = request.args.get('workflow_template_id', type=int)
    if workflow_id:
        query = query.filter_by(workflow_template_id=workflow_id)

    is_published = request.args.get('is_published')
    if is_published is not None:
        query = query.filter_by(is_published=is_published.lower() == 'true')

    mappings = query.order_by(FwFormWorkflowMapping.updated_at.desc()).all()

    return jsonify({
        'success': True,
        'data': [m.to_dict() for m in mappings]
    })


@mappings_bp.route('/<secure_code>')
@login_required
def get_mapping(secure_code):
    """取得單一配對"""
    from ..models import FwFormWorkflowMapping

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    mapping = FwFormWorkflowMapping.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not mapping:
        return jsonify({'success': False, 'error': 'Mapping not found'}), 404

    return jsonify({
        'success': True,
        'data': mapping.to_dict()
    })


@mappings_bp.route('', methods=['POST'])
@mappings_bp.route('/', methods=['POST'])
@csrf.exempt
@login_required
def create_mapping():
    """建立配對"""
    from ..models import FwFormWorkflowMapping, FwFormTemplate, FwWorkflowTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    data = request.get_json() or {}

    # 驗證必要欄位
    form_secure_code = data.get('form_template_secure_code')
    workflow_secure_code = data.get('workflow_template_secure_code')

    if not form_secure_code:
        return jsonify({'success': False, 'error': '必須指定表單模板'}), 400
    if not workflow_secure_code:
        return jsonify({'success': False, 'error': '必須指定工作流模板'}), 400

    # 查詢表單模板
    form_template = FwFormTemplate.query.filter_by(
        secure_code=form_secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not form_template:
        return jsonify({'success': False, 'error': '找不到指定的表單模板'}), 404

    # 查詢工作流模板
    workflow_template = FwWorkflowTemplate.query.filter_by(
        secure_code=workflow_secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not workflow_template:
        return jsonify({'success': False, 'error': '找不到指定的工作流模板'}), 404

    # 檢查是否已存在相同配對
    existing = FwFormWorkflowMapping.query.filter_by(
        form_template_id=form_template.id,
        workflow_template_id=workflow_template.id,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if existing:
        return jsonify({'success': False, 'error': '此配對已存在'}), 400

    # 建立配對
    mapping = FwFormWorkflowMapping(
        secure_code=secrets.token_urlsafe(16),
        org_secure_code=org.secure_code,
        form_template_id=form_template.id,
        form_template_secure_code=form_template.secure_code,
        form_template_code=form_template.code,
        form_template_version=form_template.version,
        workflow_template_id=workflow_template.id,
        workflow_template_secure_code=workflow_template.secure_code,
        workflow_template_code=workflow_template.code,
        workflow_template_version=workflow_template.version,
        is_active=data.get('is_active', True),
        priority=data.get('priority', 0),
        trigger_condition=data.get('trigger_condition'),
        description=data.get('description', ''),
    )

    db.session.add(mapping)
    db.session.commit()

    return jsonify({
        'success': True,
        'data': mapping.to_dict(),
        'message': '配對已建立'
    })


@mappings_bp.route('/<secure_code>', methods=['PUT'])
@csrf.exempt
@login_required
def update_mapping(secure_code):
    """更新配對"""
    from ..models import FwFormWorkflowMapping

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    mapping = FwFormWorkflowMapping.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not mapping:
        return jsonify({'success': False, 'error': 'Mapping not found'}), 404

    data = request.get_json() or {}

    if 'is_active' in data:
        mapping.is_active = data['is_active']
    if 'priority' in data:
        mapping.priority = data['priority']
    if 'trigger_condition' in data:
        mapping.trigger_condition = data['trigger_condition']
    if 'description' in data:
        mapping.description = data['description']

    mapping.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'success': True,
        'data': mapping.to_dict(),
        'message': '配對已更新'
    })


@mappings_bp.route('/<secure_code>', methods=['DELETE'])
@csrf.exempt
@login_required
def delete_mapping(secure_code):
    """刪除配對"""
    from ..models import FwFormWorkflowMapping

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    mapping = FwFormWorkflowMapping.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not mapping:
        return jsonify({'success': False, 'error': 'Mapping not found'}), 404

    # 檢查是否已發行
    if mapping.is_published:
        return jsonify({'success': False, 'error': '已發行的配對無法刪除，請先取消發行'}), 400

    mapping.is_deleted = True
    mapping.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'success': True,
        'message': '配對已刪除'
    })


# =============================================================================
# 發行管理 API
# =============================================================================

@mappings_bp.route('/<secure_code>/publish', methods=['POST'])
@csrf.exempt
@login_required
def publish_mapping(secure_code):
    """
    發行配對

    將設計區的表單和流程定義複製到發行區，產生不可修改的執行版本。
    """
    from ..models import (
        FwFormWorkflowMapping, FwPublishedFormWorkflow,
        FwFormTemplate, FwWorkflowTemplate
    )

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    # 查詢配對
    mapping = FwFormWorkflowMapping.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not mapping:
        return jsonify({'success': False, 'error': '找不到指定的配對'}), 404

    # 取得表單和流程模板
    form_template = FwFormTemplate.query.filter_by(
        id=mapping.form_template_id,
        is_deleted=False
    ).first()

    workflow_template = FwWorkflowTemplate.query.filter_by(
        id=mapping.workflow_template_id,
        is_deleted=False
    ).first()

    if not form_template:
        return jsonify({'success': False, 'error': '表單模板不存在或已刪除'}), 404

    if not workflow_template:
        return jsonify({'success': False, 'error': '工作流模板不存在或已刪除'}), 404

    # 驗證表單
    if not form_template.schema or not form_template.schema.get('components'):
        return jsonify({'success': False, 'error': '表單沒有欄位，無法發行'}), 400

    # 驗證流程
    if not workflow_template.graph or not workflow_template.graph.get('nodes'):
        return jsonify({'success': False, 'error': '工作流沒有節點，無法發行'}), 400

    try:
        # 檢查並停用現有 Published 版本
        existing_published = FwPublishedFormWorkflow.query.filter_by(
            source_mapping_secure_code=secure_code,
            status='Published'
        ).first()

        if existing_published:
            existing_published.suspend(suspended_by=current_user.secure_code)

        # 建立發行版本
        data = request.get_json() or {}

        published = FwPublishedFormWorkflow.create_from_mapping(
            mapping=mapping,
            form_template=form_template,
            workflow_template=workflow_template,
            published_by=current_user.secure_code,
            published_by_name=current_user.display_name or current_user.username,
        )

        if data.get('name'):
            published.name = data['name']
        if data.get('description'):
            published.description = data['description']

        # 更新配對狀態
        mapping.is_published = True
        mapping.form_template_version = form_template.version
        mapping.workflow_template_version = workflow_template.version

        db.session.add(published)
        db.session.commit()

        return jsonify({
            'success': True,
            'data': published.to_dict(),
            'message': f'發行成功 (版本 {published.publish_version})'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'發行失敗: {str(e)}'}), 500


# =============================================================================
# 已發行版本 API
# =============================================================================

@mappings_bp.route('/published')
@login_required
def list_published():
    """取得已發行版本列表"""
    from ..models import FwPublishedFormWorkflow

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    query = FwPublishedFormWorkflow.query.filter_by(
        org_secure_code=org.secure_code,
        is_deleted=False
    )

    # 篩選條件
    status = request.args.get('status')
    if status:
        query = query.filter_by(status=status)

    mapping_code = request.args.get('mapping_secure_code')
    if mapping_code:
        query = query.filter_by(source_mapping_secure_code=mapping_code)

    published_list = query.order_by(FwPublishedFormWorkflow.published_at.desc()).all()

    return jsonify({
        'success': True,
        'data': [p.to_dict() for p in published_list]
    })


@mappings_bp.route('/published/<secure_code>')
@login_required
def get_published(secure_code):
    """取得已發行版本詳情"""
    from ..models import FwPublishedFormWorkflow

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    published = FwPublishedFormWorkflow.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not published:
        return jsonify({'success': False, 'error': '找不到指定的發行版本'}), 404

    include_snapshots = request.args.get('include_snapshots', 'false').lower() == 'true'

    return jsonify({
        'success': True,
        'data': published.to_dict(include_snapshots=include_snapshots)
    })


@mappings_bp.route('/published/<secure_code>/suspend', methods=['POST'])
@csrf.exempt
@login_required
def suspend_published(secure_code):
    """停用發行版本"""
    from ..models import FwPublishedFormWorkflow

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    published = FwPublishedFormWorkflow.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not published:
        return jsonify({'success': False, 'error': '找不到指定的發行版本'}), 404

    if published.status == 'Archived':
        return jsonify({'success': False, 'error': '已封存的版本無法停用'}), 400

    if published.status == 'Suspended':
        return jsonify({'success': False, 'error': '此版本已是停用狀態'}), 400

    try:
        published.suspend(suspended_by=current_user.secure_code)
        return jsonify({
            'success': True,
            'data': published.to_dict(),
            'message': '已停用此發行版本'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'停用失敗: {str(e)}'}), 500


@mappings_bp.route('/published/<secure_code>/reopen', methods=['POST'])
@csrf.exempt
@login_required
def reopen_published(secure_code):
    """重新開放發行版本"""
    from ..models import FwPublishedFormWorkflow

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    published = FwPublishedFormWorkflow.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not published:
        return jsonify({'success': False, 'error': '找不到指定的發行版本'}), 404

    if published.status != 'Suspended':
        return jsonify({'success': False, 'error': '只有 Suspended 狀態才能重新開放'}), 400

    # 檢查是否有其他 Published 版本
    existing_published = FwPublishedFormWorkflow.query.filter(
        FwPublishedFormWorkflow.source_mapping_secure_code == published.source_mapping_secure_code,
        FwPublishedFormWorkflow.status == 'Published',
        FwPublishedFormWorkflow.id != published.id
    ).first()

    if existing_published:
        return jsonify({'success': False, 'error': f'已有其他發行版本 (v{existing_published.publish_version})'}), 400

    try:
        published.reopen()
        return jsonify({
            'success': True,
            'data': published.to_dict(),
            'message': '已重新開放此發行版本'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'重新開放失敗: {str(e)}'}), 500


@mappings_bp.route('/published/<secure_code>/archive', methods=['POST'])
@csrf.exempt
@login_required
def archive_published(secure_code):
    """封存發行版本"""
    from ..models import FwPublishedFormWorkflow

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    published = FwPublishedFormWorkflow.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not published:
        return jsonify({'success': False, 'error': '找不到指定的發行版本'}), 404

    if published.status == 'Archived':
        return jsonify({'success': False, 'error': '此版本已是封存狀態'}), 400

    try:
        published.archive()
        return jsonify({
            'success': True,
            'data': published.to_dict(),
            'message': '已封存此發行版本'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'封存失敗: {str(e)}'}), 500


# =============================================================================
# 一般用戶端點
# =============================================================================

@mappings_bp.route('/unmapped-forms')
@login_required
def list_unmapped_forms():
    """取得未配對的表單列表"""
    from ..models import FwFormTemplate, FwFormWorkflowMapping

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    # 取得已配對的表單 ID
    mapped_form_ids = db.session.query(FwFormWorkflowMapping.form_template_id).filter_by(
        org_secure_code=org.secure_code,
        is_deleted=False
    ).distinct()

    # 取得未配對的表單
    unmapped = FwFormTemplate.query.filter(
        FwFormTemplate.org_secure_code == org.secure_code,
        FwFormTemplate.is_deleted == False,
        FwFormTemplate.is_active == True,
        ~FwFormTemplate.id.in_(mapped_form_ids)
    ).order_by(FwFormTemplate.name.asc()).all()

    return jsonify({
        'success': True,
        'data': [{
            'secure_code': f.secure_code,
            'name': f.name,
            'code': f.code,
            'version': f.version
        } for f in unmapped]
    })


@mappings_bp.route('/workflows-for-mapping')
@login_required
def list_workflows_for_mapping():
    """取得可用於配對的主流程列表"""
    from ..models import FwWorkflowTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    # 取得所有啟用的工作流（只取主流程，非子流程）
    workflows = FwWorkflowTemplate.query.filter_by(
        org_secure_code=org.secure_code,
        is_deleted=False,
        is_active=True,
        is_sub_workflow=False
    ).order_by(FwWorkflowTemplate.name.asc()).all()

    return jsonify({
        'success': True,
        'data': [{
            'secure_code': w.secure_code,
            'name': w.name,
            'code': w.code,
            'version': w.version
        } for w in workflows]
    })


@mappings_bp.route('/available')
@login_required
def list_available_forms():
    """
    取得可填寫的表單列表（一般用戶使用）

    只回傳 Published 狀態的發行版本。
    """
    from ..models import FwPublishedFormWorkflow

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    published_list = FwPublishedFormWorkflow.query.filter_by(
        org_secure_code=org.secure_code,
        status='Published',
        is_deleted=False
    ).order_by(FwPublishedFormWorkflow.name.asc()).all()

    # 簡化輸出
    result = []
    for p in published_list:
        result.append({
            'secure_code': p.secure_code,
            'name': p.name,
            'description': p.description,
            'publish_version': p.publish_version,
            'published_at': p.published_at.isoformat() if p.published_at else None,
            'form_name': p.form_snapshot.get('name') if p.form_snapshot else None,
            'workflow_name': p.workflow_snapshot.get('name') if p.workflow_snapshot else None,
        })

    return jsonify({
        'success': True,
        'data': result
    })
