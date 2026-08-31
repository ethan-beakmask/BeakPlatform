"""
FormWorkflow Module - Mappings API
表單-流程配對 API

提供表單與工作流配對管理、發行等功能。
"""
import secrets
from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_login import current_user

from app.security.decorators import module_access_required, page_keys_required
from app.platform.data import get_current_org
from app import db, csrf
from flask_babel import gettext as _
from ..services.node_grant_service import find_unauthorized_node_types

# 建立 API Blueprint
mappings_bp = Blueprint(
    'form_workflow_mappings',
    __name__,
    url_prefix='/api/mappings'
)


# =============================================================================
# 輔助函式
# =============================================================================

def _sync_mapping_published_flag(mapping_secure_code):
    """同步配對的 is_published 旗標：檢查是否仍有 Published 狀態的版本"""
    from modules.form_workflow.models import FwFormWorkflowMapping, FwPublishedFormWorkflow

    has_published = FwPublishedFormWorkflow.query.filter_by(
        source_mapping_secure_code=mapping_secure_code,
        status='Published',
        is_deleted=False
    ).first() is not None

    mapping = FwFormWorkflowMapping.query.filter_by(
        secure_code=mapping_secure_code,
        is_deleted=False
    ).first()

    if mapping and mapping.is_published != has_published:
        mapping.is_published = has_published
        mapping.updated_at = datetime.utcnow()


def _nocode_usage(org_sc, mapping_sc):
    try:
        from modules.nocode_builder.services.pageir_mapping_usage import (
            find_pages_using_mapping,
        )
    except Exception:
        return []
    return find_pages_using_mapping(org_sc, mapping_sc)


def _reject_unauthorized_graph_nodes(graph, org):
    unauthorized = find_unauthorized_node_types(
        graph,
        org.secure_code if org else None,
    )
    if unauthorized:
        return jsonify({
            'success': False,
            'error': _('流程中含有本企業未獲授權的節點型別：%(types)s',
                       types=', '.join(unauthorized))
        }), 403
    return None


# =============================================================================
# 配對管理 API
# =============================================================================

@mappings_bp.route('')
@mappings_bp.route('/')
@module_access_required('form_workflow')
def list_mappings():
    """取得配對列表（含表單和流程名稱、發行版本資訊）"""
    from ..models import FwFormWorkflowMapping, FwFormTemplate, FwWorkflowTemplate, FwPublishedFormWorkflow

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    query = FwFormWorkflowMapping.query.filter_by(
        org_secure_code=org.secure_code,
        is_deleted=False
    )

    # 封存篩選（預設只顯示未封存）
    is_archived = request.args.get('is_archived', 'false').lower() == 'true'
    query = query.filter_by(is_archived=is_archived)

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

    # 批次查詢表單和流程（含名稱、版本）
    form_ids = [m.form_template_id for m in mappings]
    workflow_ids = [m.workflow_template_id for m in mappings]

    form_map = {}
    workflow_map = {}

    if form_ids:
        forms = FwFormTemplate.query.filter(FwFormTemplate.id.in_(form_ids)).all()
        form_map = {f.id: {'name': f.name, 'version': f.version, 'revision': f.revision} for f in forms}

    if workflow_ids:
        workflows = FwWorkflowTemplate.query.filter(FwWorkflowTemplate.id.in_(workflow_ids)).all()
        workflow_map = {w.id: {'name': w.name, 'version': w.version, 'revision': w.revision} for w in workflows}

    # 批次查詢每個配對的發行版本資訊
    mapping_codes = [m.secure_code for m in mappings]
    publish_map = {}  # mapping_secure_code -> {active_version, total_versions, published_form_name}

    if mapping_codes:
        published_all = FwPublishedFormWorkflow.query.filter(
            FwPublishedFormWorkflow.source_mapping_secure_code.in_(mapping_codes),
            FwPublishedFormWorkflow.is_deleted == False
        ).all()

        # 按 mapping 分組
        from collections import defaultdict
        grouped = defaultdict(list)
        for p in published_all:
            grouped[p.source_mapping_secure_code].append(p)

        for mcode, versions in grouped.items():
            total = len(versions)
            published_ones = [v for v in versions if v.status == 'Published']
            all_archived = total > 0 and all(v.status == 'Archived' for v in versions)
            if len(published_ones) == 1:
                active = published_ones[0]
                publish_map[mcode] = {
                    'active_version': active.publish_version,
                    'total_versions': total,
                    'published_form_name': active.form_snapshot.get('name', '') if active.form_snapshot else '',
                    'version_error': None,
                    'all_versions_archived': False,
                }
            elif len(published_ones) > 1:
                publish_map[mcode] = {
                    'active_version': 0,
                    'total_versions': total,
                    'published_form_name': '',
                    'version_error': f'異常：{len(published_ones)} 個版本同時為 Published',
                    'all_versions_archived': False,
                }
            else:
                # 有版本但無 Published（全部暫停或封存）
                publish_map[mcode] = {
                    'active_version': 0,
                    'total_versions': total,
                    'published_form_name': '',
                    'version_error': None,
                    'all_versions_archived': all_archived,
                }

    # 批次查詢編號規則名稱
    from app.models import UserNumberingRule
    rule_codes = [m.numbering_rule_secure_code for m in mappings if m.numbering_rule_secure_code]
    rule_name_map = {}
    if rule_codes:
        rules = UserNumberingRule.query.filter(
            UserNumberingRule.secure_code.in_(rule_codes),
            UserNumberingRule.is_deleted == False
        ).all()
        rule_name_map = {r.secure_code: r.name for r in rules}

    # 組合結果
    result = []
    for m in mappings:
        data = m.to_dict()
        fi = form_map.get(m.form_template_id, {})
        wi = workflow_map.get(m.workflow_template_id, {})
        data['form_template_name'] = fi.get('name', m.form_template_code)
        data['form_current_version'] = fi.get('version', 'AA')
        data['form_current_revision'] = fi.get('revision', 0)
        data['workflow_template_name'] = wi.get('name', m.workflow_template_code)
        data['workflow_current_version'] = wi.get('version', 'AA')
        data['workflow_current_revision'] = wi.get('revision', 0)

        # 編號規則名稱
        data['numbering_rule_name'] = rule_name_map.get(m.numbering_rule_secure_code)

        # 發行版本資訊
        pi = publish_map.get(m.secure_code, {})
        data['active_version'] = pi.get('active_version', 0)
        data['total_versions'] = pi.get('total_versions', 0)
        data['published_form_name'] = pi.get('published_form_name', '')
        data['version_error'] = pi.get('version_error')
        data['all_versions_archived'] = pi.get('all_versions_archived', False)

        result.append(data)

    return jsonify({
        'success': True,
        'data': result
    })


@mappings_bp.route('/<secure_code>')
@module_access_required('form_workflow')
@page_keys_required('form_workflow.mappings')
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
@module_access_required('form_workflow')
@page_keys_required('form_workflow.mappings')
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
        return jsonify({'success': False, 'error': _('必須指定表單模板')}), 400
    if not workflow_secure_code:
        return jsonify({'success': False, 'error': _('必須指定工作流模板')}), 400

    # 查詢表單模板
    form_template = FwFormTemplate.query.filter_by(
        secure_code=form_secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not form_template:
        return jsonify({'success': False, 'error': _('找不到指定的表單模板')}), 404

    # 查詢工作流模板
    workflow_template = FwWorkflowTemplate.query.filter_by(
        secure_code=workflow_secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not workflow_template:
        return jsonify({'success': False, 'error': _('找不到指定的工作流模板')}), 404

    # 檢查是否已存在相同配對
    existing = FwFormWorkflowMapping.query.filter_by(
        form_template_id=form_template.id,
        workflow_template_id=workflow_template.id,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if existing:
        return jsonify({'success': False, 'error': _('此配對已存在')}), 400

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
        'message': _('配對已建立')
    })


@mappings_bp.route('/<secure_code>', methods=['PUT'])
@csrf.exempt
@module_access_required('form_workflow')
@page_keys_required('form_workflow.mappings')
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
    if 'numbering_rule_secure_code' in data:
        rule_sc = data['numbering_rule_secure_code'] or None
        if rule_sc:
            # 驗證規則存在且屬於同企業
            from app.models import UserNumberingRule
            rule = UserNumberingRule.query.filter_by(
                secure_code=rule_sc,
                org_secure_code=org.secure_code,
                is_active=True,
                is_deleted=False
            ).first()
            if not rule:
                return jsonify({'success': False, 'error': _('找不到指定的編號規則')}), 404
        mapping.numbering_rule_secure_code = rule_sc
    mapping.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'success': True,
        'data': mapping.to_dict(),
        'message': _('配對已更新')
    })


@mappings_bp.route('/<secure_code>', methods=['DELETE'])
@csrf.exempt
@module_access_required('form_workflow')
@page_keys_required('form_workflow.mappings')
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
        return jsonify({'success': False, 'error': _('已發行的配對無法刪除，請先取消發行')}), 400

    usage = _nocode_usage(org.secure_code, secure_code)
    if usage:
        return jsonify({
            'success': False,
            'error': 'nocode_in_use',
            'message': _('此配對正被 NoCode 頁面使用，無法刪除'),
            'details': {'pages': usage},
        }), 400

    mapping.is_deleted = True
    mapping.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'success': True,
        'message': _('配對已刪除')
    })


# =============================================================================
# SQL 同步管理 API
# =============================================================================

@mappings_bp.route('/published/<secure_code>/sql-sync', methods=['PATCH'])
@csrf.exempt
@module_access_required('form_workflow')
@page_keys_required('form_workflow.mappings')
def toggle_sql_sync(secure_code):
    """啟用發行版本的 SQL 同步（單向，啟用後不可關閉）"""
    from ..models import FwPublishedFormWorkflow, FwFormWorkflowMapping, FwFormTemplate
    from ..models.sql_form_registry import FwSqlFormRegistry

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    published = FwPublishedFormWorkflow.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not published:
        return jsonify({'success': False, 'error': _('找不到指定的發行版本')}), 404

    data = request.get_json() or {}
    if 'sql_sync_enabled' not in data:
        return jsonify({'success': False, 'error': _('缺少 sql_sync_enabled 參數')}), 400

    enabled = bool(data['sql_sync_enabled'])

    # 規則：已啟用就不可關閉
    if published.sql_sync_enabled and not enabled:
        return jsonify({'success': False, 'error': _('SQL 同步啟用後無法關閉')}), 400

    # 規則：已封存的版本不可啟用
    if enabled and published.status == 'Archived':
        return jsonify({'success': False, 'error': _('已封存的版本無法啟用 SQL 同步')}), 400

    published.sql_sync_enabled = True
    published.updated_at = datetime.utcnow()

    # 建立同步表
    sync_table_created = False
    existing_reg = FwSqlFormRegistry.query.filter_by(
        published_secure_code=published.secure_code,
        status='active',
    ).first()

    if not existing_reg:
        try:
            from ..services.sql_sync.org_db_manager import get_org_database, provision_org_database
            from ..services.sql_sync.table_manager import create_sync_table_for_published

            org_db = get_org_database(org.secure_code)
            if not org_db:
                org_db = provision_org_database(
                    org_id=org.id,
                    org_secure_code=org.secure_code,
                )

            ft = FwFormTemplate.query.filter_by(
                secure_code=published.source_form_template_secure_code,
                version=published.source_form_version,
            ).first()

            mapping = FwFormWorkflowMapping.query.filter_by(
                secure_code=published.source_mapping_secure_code,
                is_deleted=False,
            ).first()

            if org_db and ft and mapping:
                reg = create_sync_table_for_published(
                    published=published,
                    form_schema=ft.schema,
                    org_secure_code=org.secure_code,
                    mapping_id=mapping.id,
                )
                if reg:
                    sync_table_created = True
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f'SQL Sync: 建表失敗: {e}')

    db.session.commit()

    msg = _('SQL 同步已啟用（已建立同步表）') if sync_table_created else _('SQL 同步已啟用')

    return jsonify({
        'success': True,
        'data': published.to_dict(),
        'message': msg
    })


@mappings_bp.route('/published/<secure_code>/sql-sync/status')
@module_access_required('form_workflow')
@page_keys_required('form_workflow.mappings')
def get_sql_sync_status(secure_code):
    """取得發行版本的 SQL 同步狀態"""
    from ..models import FwPublishedFormWorkflow, FwSqlFormRegistry

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    published = FwPublishedFormWorkflow.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not published:
        return jsonify({'success': False, 'error': _('找不到指定的發行版本')}), 404

    registry = FwSqlFormRegistry.query.filter_by(
        published_secure_code=secure_code,
    ).first()

    return jsonify({
        'success': True,
        'data': {
            'sql_sync_enabled': published.sql_sync_enabled,
            'table': {
                'table_name': registry.table_name,
                'publish_version': registry.publish_version,
                'status': registry.status,
                'row_count': registry.row_count,
                'last_synced_at': registry.last_synced_at.isoformat() if registry.last_synced_at else None,
            } if registry else None
        }
    })


# =============================================================================
# 發行管理 API
# =============================================================================

@mappings_bp.route('/<secure_code>/publish', methods=['POST'])
@csrf.exempt
@module_access_required('form_workflow')
@page_keys_required('form_workflow.mappings')
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
        return jsonify({'success': False, 'error': _('找不到指定的配對')}), 404

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
        return jsonify({'success': False, 'error': _('表單模板不存在或已刪除')}), 404

    if not workflow_template:
        return jsonify({'success': False, 'error': _('工作流模板不存在或已刪除')}), 404

    # 驗證表單
    if not form_template.schema or not form_template.schema.get('components'):
        return jsonify({'success': False, 'error': _('表單沒有欄位，無法發行')}), 400

    # 驗證流程
    if not workflow_template.graph or not workflow_template.graph.get('nodes'):
        return jsonify({'success': False, 'error': _('工作流沒有節點，無法發行')}), 400

    unauthorized_response = _reject_unauthorized_graph_nodes(workflow_template.graph, org)
    if unauthorized_response:
        return unauthorized_response

    try:
        # 檢查現有 Published 版本
        existing_published = FwPublishedFormWorkflow.query.filter_by(
            source_mapping_secure_code=secure_code,
            status='Published'
        ).first()

        if existing_published:
            # 比對版本 + revision，判斷是否有變更
            same_form = (
                existing_published.source_form_version == form_template.version and
                existing_published.source_form_revision == form_template.revision
            )
            same_workflow = (
                existing_published.source_workflow_version == workflow_template.version and
                existing_published.source_workflow_revision == workflow_template.revision
            )

            if same_form and same_workflow:
                # 版本完全相同 → 不建新版，直接回傳現有版本
                return jsonify({
                    'success': True,
                    'data': existing_published.to_dict(),
                    'message': _('版本未變更，維持現有發行版本 (版本 %(version)s)', version=existing_published.publish_version)
                })

            # 有變更 → 先查找是否有相同版本的 Suspended 記錄可重新啟用
            reusable = FwPublishedFormWorkflow.query.filter_by(
                source_mapping_secure_code=secure_code,
                source_form_version=form_template.version,
                source_form_revision=form_template.revision,
                source_workflow_version=workflow_template.version,
                source_workflow_revision=workflow_template.revision,
                status='Suspended'
            ).first()

            if reusable:
                # 停用現有 Published，重新啟用匹配的 Suspended 版本
                existing_published.suspend(suspended_by=current_user.secure_code)
                reusable.reopen()

                # 更新配對狀態
                mapping.is_published = True
                mapping.form_template_version = form_template.version
                mapping.workflow_template_version = workflow_template.version
                db.session.commit()

                return jsonify({
                    'success': True,
                    'data': reusable.to_dict(),
                    'message': _('已重新啟用先前的發行版本 (版本 %(version)s)', version=reusable.publish_version)
                })

            # 沒有可重用的版本 → 停用舊版，建立新版
            existing_published.suspend(suspended_by=current_user.secure_code)

        # 建立發行版本
        data = request.get_json(silent=True) or {}

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
            'message': _('發行成功 (版本 %(version)s)', version=published.publish_version)
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': _('發行失敗: %(error)s', error=str(e))}), 500


# =============================================================================
# 已發行版本 API
# =============================================================================

@mappings_bp.route('/published')
@module_access_required('form_workflow')
@page_keys_required('form_workflow.mappings')
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
@module_access_required('form_workflow')
@page_keys_required('form_workflow.mappings')
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
        return jsonify({'success': False, 'error': _('找不到指定的發行版本')}), 404

    include_snapshots = request.args.get('include_snapshots', 'false').lower() == 'true'

    return jsonify({
        'success': True,
        'data': published.to_dict(include_snapshots=include_snapshots)
    })


@mappings_bp.route('/published/<secure_code>/suspend', methods=['POST'])
@csrf.exempt
@module_access_required('form_workflow')
@page_keys_required('form_workflow.mappings')
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
        return jsonify({'success': False, 'error': _('找不到指定的發行版本')}), 404

    if published.status == 'Archived':
        return jsonify({'success': False, 'error': _('已封存的版本無法停用')}), 400

    if published.status == 'Suspended':
        return jsonify({'success': False, 'error': _('此版本已是停用狀態')}), 400

    try:
        published.suspend(suspended_by=current_user.secure_code)
        _sync_mapping_published_flag(published.source_mapping_secure_code)
        db.session.commit()
        return jsonify({
            'success': True,
            'data': published.to_dict(),
            'message': _('已停用此發行版本')
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': _('停用失敗: %(error)s', error=str(e))}), 500


@mappings_bp.route('/published/<secure_code>/reopen', methods=['POST'])
@csrf.exempt
@module_access_required('form_workflow')
@page_keys_required('form_workflow.mappings')
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
        return jsonify({'success': False, 'error': _('找不到指定的發行版本')}), 404

    if published.status != 'Suspended':
        return jsonify({'success': False, 'error': _('只有 Suspended 狀態才能重新開放')}), 400

    # 檢查是否有其他 Published 版本
    existing_published = FwPublishedFormWorkflow.query.filter(
        FwPublishedFormWorkflow.source_mapping_secure_code == published.source_mapping_secure_code,
        FwPublishedFormWorkflow.status == 'Published',
        FwPublishedFormWorkflow.id != published.id
    ).first()

    if existing_published:
        return jsonify({'success': False, 'error': _('已有其他發行版本 (v%(version)s)', version=existing_published.publish_version)}), 400

    try:
        published.reopen()
        _sync_mapping_published_flag(published.source_mapping_secure_code)
        db.session.commit()
        return jsonify({
            'success': True,
            'data': published.to_dict(),
            'message': _('已重新開放此發行版本')
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': _('重新開放失敗: %(error)s', error=str(e))}), 500


@mappings_bp.route('/published/<secure_code>/archive', methods=['POST'])
@csrf.exempt
@module_access_required('form_workflow')
@page_keys_required('form_workflow.mappings')
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
        return jsonify({'success': False, 'error': _('找不到指定的發行版本')}), 404

    if published.status == 'Archived':
        return jsonify({'success': False, 'error': _('此版本已是封存狀態')}), 400

    try:
        published.archive()
        _sync_mapping_published_flag(published.source_mapping_secure_code)
        db.session.commit()
        return jsonify({
            'success': True,
            'data': published.to_dict(),
            'message': _('已封存此發行版本')
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': _('封存失敗: %(error)s', error=str(e))}), 500


# =============================================================================
# 配對封存 API
# =============================================================================

@mappings_bp.route('/<secure_code>/archive', methods=['POST'])
@csrf.exempt
@module_access_required('form_workflow')
@page_keys_required('form_workflow.mappings')
def archive_mapping(secure_code):
    """封存配對（所有發行版本都已封存時才可執行）"""
    from ..models import FwFormWorkflowMapping, FwPublishedFormWorkflow

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    mapping = FwFormWorkflowMapping.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not mapping:
        return jsonify({'success': False, 'error': _('找不到指定的配對')}), 404

    if mapping.is_archived:
        return jsonify({'success': False, 'error': _('此配對已封存')}), 400

    # 檢查所有發行版本是否都為 Archived
    versions = FwPublishedFormWorkflow.query.filter_by(
        source_mapping_secure_code=secure_code,
        is_deleted=False
    ).all()

    if not versions:
        # 無發行版本也允許封存（直接歸檔未用的配對）
        pass
    else:
        non_archived = [v for v in versions if v.status != 'Archived']
        if non_archived:
            return jsonify({
                'success': False,
                'error': _('尚有 %(count)s 個發行版本未封存，請先封存所有版本', count=len(non_archived))
            }), 400

    usage = _nocode_usage(org.secure_code, secure_code)
    if usage:
        return jsonify({
            'success': False,
            'error': 'nocode_in_use',
            'message': _('此配對正被 NoCode 頁面使用，無法封存'),
            'details': {'pages': usage},
        }), 400

    mapping.is_archived = True
    mapping.is_published = False
    mapping.archived_at = datetime.utcnow()
    mapping.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'success': True,
        'data': mapping.to_dict(),
        'message': _('配對已封存')
    })


@mappings_bp.route('/<secure_code>/unarchive', methods=['POST'])
@csrf.exempt
@module_access_required('form_workflow')
@page_keys_required('form_workflow.mappings')
def unarchive_mapping(secure_code):
    """解除配對封存"""
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
        return jsonify({'success': False, 'error': _('找不到指定的配對')}), 404

    if not mapping.is_archived:
        return jsonify({'success': False, 'error': _('此配對未封存')}), 400

    mapping.is_archived = False
    mapping.archived_at = None
    mapping.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'success': True,
        'data': mapping.to_dict(),
        'message': _('配對已恢復')
    })


# =============================================================================
# 發行版本刪除 API
# =============================================================================

@mappings_bp.route('/published/<secure_code>', methods=['DELETE'])
@csrf.exempt
@module_access_required('form_workflow')
@page_keys_required('form_workflow.mappings')
def delete_published(secure_code):
    """刪除發行版本（僅限未使用過的版本）"""
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
        return jsonify({'success': False, 'error': _('找不到指定的發行版本')}), 404

    if published.is_used:
        return jsonify({'success': False, 'error': _('此版本已被使用過，無法刪除')}), 400

    if published.status == 'Published':
        return jsonify({'success': False, 'error': _('運作中的版本無法刪除，請先暫停或封存')}), 400

    # 軟刪除
    published.is_deleted = True
    published.updated_at = datetime.utcnow()
    _sync_mapping_published_flag(published.source_mapping_secure_code)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': _('發行版本 v%(version)s 已刪除', version=published.publish_version)
    })


# =============================================================================
# 編號規則端點
# =============================================================================

@mappings_bp.route('/numbering-rules')
@module_access_required('form_workflow')
@page_keys_required('form_workflow.mappings')
def list_numbering_rules():
    """取得可用於表單的編號規則列表（FORM 預設 + 無預設用途的規則）"""
    from app.models import UserNumberingRule
    from app.services.numbering_service import NumberingService

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    rules = UserNumberingRule.query.filter(
        UserNumberingRule.org_secure_code == org.secure_code,
        UserNumberingRule.is_active == True,
        UserNumberingRule.is_deleted == False,
        db.or_(
            UserNumberingRule.default_for == 'FORM',
            UserNumberingRule.default_for == None
        )
    ).order_by(
        UserNumberingRule.default_for.desc().nullslast(),
        UserNumberingRule.name
    ).all()

    result = []
    for r in rules:
        preview = NumberingService.preview_numbers(r, count=1)
        result.append({
            'secure_code': r.secure_code,
            'name': r.name,
            'default_for': r.default_for,
            'is_form_default': r.default_for == 'FORM',
            'preview': preview[0] if preview else '',
        })

    return jsonify({
        'success': True,
        'data': result
    })


# =============================================================================
# 一般用戶端點
# =============================================================================

@mappings_bp.route('/unmapped-forms')
@module_access_required('form_workflow')
@page_keys_required('form_workflow.mappings')
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
            'version': f.version,
            'revision': f.revision
        } for f in unmapped]
    })


@mappings_bp.route('/workflows-for-mapping')
@module_access_required('form_workflow')
@page_keys_required('form_workflow.mappings')
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
        is_subprocess=False
    ).order_by(FwWorkflowTemplate.name.asc()).all()

    return jsonify({
        'success': True,
        'data': [{
            'secure_code': w.secure_code,
            'name': w.name,
            'code': w.code,
            'version': w.version,
            'revision': w.revision
        } for w in workflows]
    })


