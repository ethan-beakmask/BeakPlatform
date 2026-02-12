"""
FormWorkflow Module - API Routes
表單流程模組 API

提供表單和工作流的 RESTful API。
"""
import secrets
from datetime import datetime
from flask import Blueprint, jsonify, request

from app import csrf
from app.security.decorators import public_route
from app.platform.auth import (
    current_user,
    has_permission,
    require_permission,
    get_user_permissions,
)
from app.platform.data import get_current_org

# 建立 API Blueprint
api_bp = Blueprint(
    'form_workflow_api',
    __name__,
    url_prefix='/api/form-workflow'
)


# =============================================================================
# 模組資訊
# =============================================================================

@api_bp.route('/info')
@public_route
def module_info():
    """取得模組資訊（公開）"""
    from .. import MODULE_INFO
    return jsonify({
        'success': True,
        'data': {
            'name': MODULE_INFO['name'],
            'display_name': MODULE_INFO['display_name'],
            'version': MODULE_INFO['version'],
            'description': MODULE_INFO['description'],
        }
    })


@api_bp.route('/permissions')
@public_route
def module_permissions():
    """取得模組權限列表（公開）"""
    from app.platform.auth import get_module_permissions
    perms = get_module_permissions('form_workflow')
    return jsonify({
        'success': True,
        'data': {'permissions': perms}
    })


# =============================================================================
# 表單模板 API
# =============================================================================

@api_bp.route('/templates')
@require_permission('form_workflow.template.view')
def list_templates():
    """取得表單模板列表"""
    from ..models import FwFormTemplate, FwFormWorkflowMapping

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    query = FwFormTemplate.query.filter_by(
        org_secure_code=org.secure_code,
        is_deleted=False
    )

    # 搜尋
    q = request.args.get('q', '').strip()
    if q:
        query = query.filter(
            FwFormTemplate.name.ilike(f'%{q}%') |
            FwFormTemplate.code.ilike(f'%{q}%')
        )

    templates = query.order_by(FwFormTemplate.updated_at.desc()).all()

    # 查詢已配對的表單 ID 集合
    from app import db
    mapped_form_ids = set(
        r[0] for r in db.session.query(FwFormWorkflowMapping.form_template_id).filter_by(
            org_secure_code=org.secure_code, is_deleted=False
        ).all()
    )

    result = []
    for t in templates:
        d = t.to_dict(include_schema=False)
        d['is_mapped'] = t.id in mapped_form_ids
        result.append(d)

    return jsonify({
        'success': True,
        'data': {
            'templates': result
        }
    })


@api_bp.route('/templates/<secure_code>')
@require_permission('form_workflow.template.view')
def get_template(secure_code):
    """取得單一表單模板"""
    from ..models import FwFormTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    template = FwFormTemplate.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not template:
        return jsonify({'success': False, 'error': 'Template not found'}), 404

    return jsonify({
        'success': True,
        'data': template.to_dict(include_schema=True)
    })


@api_bp.route('/templates', methods=['POST'])
@csrf.exempt
@require_permission('form_workflow.template.create')
def create_template():
    """建立表單模板"""
    from ..models import FwFormTemplate
    from app import db

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    data = request.get_json() or {}
    name = data.get('name', '').strip()

    if not name:
        return jsonify({'success': False, 'error': 'Name is required'}), 400

    # 自動產生 code
    code = data.get('code', '').strip().upper()
    if not code:
        code = f'FT{secrets.token_hex(4).upper()}'

    # 檢查 code 是否重複
    existing = FwFormTemplate.query.filter_by(
        code=code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()
    if existing:
        return jsonify({'success': False, 'error': f'Code {code} already exists'}), 400

    template = FwFormTemplate(
        secure_code=secrets.token_urlsafe(16),
        org_secure_code=org.secure_code,
        name=name,
        code=code,
        description=data.get('description', ''),
        category=data.get('category', '其他'),
        category_secure_code=data.get('category_secure_code') or 'SYS_CAT_OTHER',
        schema=data.get('schema', {}),
        is_active=data.get('is_active', True)
    )

    db.session.add(template)
    db.session.commit()

    return jsonify({
        'success': True,
        'data': template.to_dict(include_schema=True),
        'message': '表單模板已建立'
    })


@api_bp.route('/templates/<secure_code>', methods=['PUT'])
@csrf.exempt
@require_permission('form_workflow.template.edit')
def update_template(secure_code):
    """更新表單模板"""
    from ..models import FwFormTemplate
    from app import db

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    template = FwFormTemplate.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not template:
        return jsonify({'success': False, 'error': 'Template not found'}), 404

    data = request.get_json() or {}

    if 'name' in data:
        template.name = data['name'].strip()
    if 'description' in data:
        template.description = data['description']
    if 'category_secure_code' in data:
        template.category_secure_code = data['category_secure_code']
    if 'category' in data:
        template.category = data['category']
    if 'schema' in data:
        template.schema = data['schema']
    if 'is_active' in data:
        template.is_active = data['is_active']

    # 縮圖
    if 'thumbnail_2x1' in data:
        template.thumbnail_2x1 = data['thumbnail_2x1']
    if 'thumbnail_1x1' in data:
        template.thumbnail_1x1 = data['thumbnail_1x1']
    if 'thumbnail_1x2' in data:
        template.thumbnail_1x2 = data['thumbnail_1x2']

    db.session.commit()

    return jsonify({
        'success': True,
        'data': template.to_dict(include_schema=True),
        'message': '表單模板已更新'
    })


@api_bp.route('/templates/batch/delete', methods=['POST'])
@csrf.exempt
@require_permission('form_workflow.template.delete')
def batch_delete_templates():
    """批次刪除表單模板（軟刪除）"""
    from ..models import FwFormTemplate
    from app import db

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    data = request.get_json() or {}
    secure_codes = data.get('secure_codes', [])
    if not secure_codes:
        return jsonify({'success': False, 'error': 'secure_codes is required'}), 400

    results = []
    succeeded = 0
    for sc in secure_codes:
        tpl = FwFormTemplate.query.filter_by(
            secure_code=sc, org_secure_code=org.secure_code, is_deleted=False
        ).first()
        if not tpl:
            results.append({'secure_code': sc, 'success': False, 'message': '找不到表單'})
            continue
        tpl.is_deleted = True
        results.append({'secure_code': sc, 'success': True, 'message': '已刪除'})
        succeeded += 1

    db.session.commit()
    return jsonify({
        'success': True,
        'results': results,
        'summary': {'total': len(secure_codes), 'succeeded': succeeded, 'failed': len(secure_codes) - succeeded}
    })


@api_bp.route('/templates/batch/save-new-version', methods=['POST'])
@csrf.exempt
@require_permission('form_workflow.template.edit')
def batch_save_new_version_templates():
    """批次另存新版表單模板（複製出新記錄，版本號遞增）"""
    from ..models import FwFormTemplate
    from app import db

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    data = request.get_json() or {}
    secure_codes = data.get('secure_codes', [])
    if not secure_codes:
        return jsonify({'success': False, 'error': 'secure_codes is required'}), 400

    results = []
    succeeded = 0
    for sc in secure_codes:
        tpl = FwFormTemplate.query.filter_by(
            secure_code=sc, org_secure_code=org.secure_code, is_deleted=False
        ).first()
        if not tpl:
            results.append({'secure_code': sc, 'success': False, 'message': '找不到表單'})
            continue
        current_version = tpl.version or 'AA'
        if len(current_version) >= 2:
            first, second = current_version[0], current_version[1]
            new_version = (chr(ord(first) + 1) + 'A') if second == 'Z' else (first + chr(ord(second) + 1))
        else:
            new_version = 'AA'
        new_tpl = FwFormTemplate(
            secure_code=secrets.token_urlsafe(16),
            org_secure_code=tpl.org_secure_code,
            code=f'FT{secrets.token_hex(4).upper()}',
            name=tpl.name,
            description=tpl.description,
            category=tpl.category,
            category_secure_code=tpl.category_secure_code,
            schema=tpl.schema,
            builder_config=tpl.builder_config,
            version=new_version,
            revision=1,
            thumbnail_2x1=tpl.thumbnail_2x1,
            thumbnail_1x1=tpl.thumbnail_1x1,
            thumbnail_1x2=tpl.thumbnail_1x2,
            is_active=tpl.is_active,
            owner_secure_code=current_user.secure_code,
        )
        db.session.add(new_tpl)
        results.append({'secure_code': sc, 'success': True, 'message': f'已另存為版本 {new_version}', 'new_secure_code': new_tpl.secure_code})
        succeeded += 1

    db.session.commit()
    return jsonify({
        'success': True,
        'results': results,
        'summary': {'total': len(secure_codes), 'succeeded': succeeded, 'failed': len(secure_codes) - succeeded}
    })


@api_bp.route('/templates/<secure_code>', methods=['DELETE'])
@csrf.exempt
@require_permission('form_workflow.template.delete')
def delete_template(secure_code):
    """
    刪除表單模板（軟刪除）

    Query Parameters:
        check: 若為 1，只回傳配對資訊不刪除（前端預檢用）
    """
    from ..models import FwFormTemplate, FwFormWorkflowMapping, FwWorkflowTemplate
    from app import db

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    template = FwFormTemplate.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not template:
        return jsonify({'success': False, 'error': 'Template not found'}), 404

    # 查詢關聯的配對
    mappings = FwFormWorkflowMapping.query.filter_by(
        form_template_id=template.id,
        is_deleted=False
    ).all()

    # 預檢模式：回傳配對資訊
    if request.args.get('check') == '1':
        mapping_info = []
        if mappings:
            wf_ids = [m.workflow_template_id for m in mappings]
            wf_map = {}
            if wf_ids:
                wfs = FwWorkflowTemplate.query.filter(FwWorkflowTemplate.id.in_(wf_ids)).all()
                wf_map = {w.id: w.name for w in wfs}
            for m in mappings:
                mapping_info.append({
                    'workflow_name': wf_map.get(m.workflow_template_id, '未知流程'),
                    'is_published': m.is_published,
                })
        return jsonify({
            'success': True,
            'has_mappings': len(mappings) > 0,
            'mappings': mapping_info,
        })

    template.is_deleted = True
    db.session.commit()

    return jsonify({
        'success': True,
        'message': '表單模板已刪除'
    })


# =============================================================================
# 工作流模板 API
# =============================================================================

@api_bp.route('/workflows')
@require_permission('form_workflow.workflow.view')
def list_workflows():
    """取得工作流模板列表"""
    from ..models import FwWorkflowTemplate, FwFormWorkflowMapping

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    query = FwWorkflowTemplate.query.filter_by(
        org_secure_code=org.secure_code,
        is_deleted=False
    )

    # 搜尋
    q = request.args.get('q', '').strip()
    if q:
        query = query.filter(
            FwWorkflowTemplate.name.ilike(f'%{q}%') |
            FwWorkflowTemplate.code.ilike(f'%{q}%')
        )

    # flow_type 篩選：main=主流程, subflow=子流程, 不傳=全部
    flow_type = request.args.get('flow_type', '').strip().lower()
    if flow_type == 'main':
        query = query.filter(FwWorkflowTemplate.is_subprocess == False)
    elif flow_type == 'subflow':
        query = query.filter(FwWorkflowTemplate.is_subprocess == True)

    workflows = query.order_by(FwWorkflowTemplate.updated_at.desc()).all()

    # 查詢每個流程的配對數量
    from app import db
    from sqlalchemy import func
    mapping_counts = dict(
        db.session.query(
            FwFormWorkflowMapping.workflow_template_id,
            func.count(FwFormWorkflowMapping.id)
        ).filter_by(
            org_secure_code=org.secure_code, is_deleted=False
        ).group_by(FwFormWorkflowMapping.workflow_template_id).all()
    )

    result = []
    for w in workflows:
        d = w.to_dict(include_graph=False)
        d['mapping_count'] = mapping_counts.get(w.id, 0)
        result.append(d)

    return jsonify({
        'success': True,
        'data': {
            'workflows': result
        }
    })


@api_bp.route('/workflows/<secure_code>')
@require_permission('form_workflow.workflow.view')
def get_workflow(secure_code):
    """取得單一工作流模板"""
    from ..models import FwWorkflowTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    workflow = FwWorkflowTemplate.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not workflow:
        return jsonify({'success': False, 'error': 'Workflow not found'}), 404

    return jsonify({
        'success': True,
        'data': workflow.to_dict(include_graph=True)
    })


@api_bp.route('/workflows', methods=['POST'])
@csrf.exempt
@require_permission('form_workflow.workflow.create')
def create_workflow():
    """建立工作流模板"""
    from ..models import FwWorkflowTemplate
    from app import db

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    data = request.get_json() or {}
    name = data.get('name', '').strip()

    if not name:
        return jsonify({'success': False, 'error': 'Name is required'}), 400

    # 自動產生 code
    code = data.get('code', '').strip().upper()
    if not code:
        code = f'WF{secrets.token_hex(4).upper()}'

    # 檢查 code 是否重複
    existing = FwWorkflowTemplate.query.filter_by(
        code=code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()
    if existing:
        return jsonify({'success': False, 'error': f'Code {code} already exists'}), 400

    is_subprocess = data.get('is_subprocess', False)

    # 子流程自動使用 SF 前綴的 code
    if is_subprocess and not data.get('code', '').strip():
        code = f'SF{secrets.token_hex(4).upper()}'

    workflow = FwWorkflowTemplate(
        secure_code=secrets.token_urlsafe(16),
        org_secure_code=org.secure_code,
        name=name,
        code=code,
        description=data.get('description', ''),
        category=data.get('category', '其他'),
        category_secure_code=data.get('category_secure_code') or 'SYS_CAT_OTHER',
        graph=data.get('graph', {'nodes': [], 'edges': []}),
        is_active=data.get('is_active', True),
        is_subprocess=is_subprocess
    )

    db.session.add(workflow)
    db.session.commit()

    return jsonify({
        'success': True,
        'data': workflow.to_dict(include_graph=True),
        'message': '工作流模板已建立'
    })


@api_bp.route('/workflows/<secure_code>', methods=['PUT'])
@csrf.exempt
@require_permission('form_workflow.workflow.edit')
def update_workflow(secure_code):
    """更新工作流模板"""
    from ..models import FwWorkflowTemplate
    from app import db

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    workflow = FwWorkflowTemplate.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not workflow:
        return jsonify({'success': False, 'error': 'Workflow not found'}), 404

    data = request.get_json() or {}

    if 'name' in data:
        workflow.name = data['name'].strip()
    if 'description' in data:
        workflow.description = data['description']
    if 'category_secure_code' in data:
        workflow.category_secure_code = data['category_secure_code']
    if 'category' in data:
        workflow.category = data['category']
    if 'graph' in data:
        workflow.graph = data['graph']
    if 'is_active' in data:
        workflow.is_active = data['is_active']

    # 縮圖
    if 'thumbnail_2x1' in data:
        workflow.thumbnail_2x1 = data['thumbnail_2x1']
    if 'thumbnail_1x1' in data:
        workflow.thumbnail_1x1 = data['thumbnail_1x1']
    if 'thumbnail_1x2' in data:
        workflow.thumbnail_1x2 = data['thumbnail_1x2']

    db.session.commit()

    return jsonify({
        'success': True,
        'data': workflow.to_dict(include_graph=True),
        'message': '工作流模板已更新'
    })


@api_bp.route('/workflows/flow-trees')
@require_permission('form_workflow.workflow.view')
def list_flow_trees():
    """取得流程樹系（主流程及其引用的子流程樹）"""
    from ..models import FwWorkflowTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    org_code = org.secure_code

    # 查詢所有非刪除的流程（主流程 + 子流程）
    all_workflows = FwWorkflowTemplate.query.filter_by(
        org_secure_code=org_code,
        is_deleted=False
    ).all()

    # 分離主流程與子流程，建立 code → workflow 映射
    main_flows = []
    subflow_by_code = {}
    for wf in all_workflows:
        if wf.is_subprocess:
            subflow_by_code[wf.code] = wf
        else:
            main_flows.append(wf)

    def extract_child_flow_ids(graph):
        """從 graph 中提取所有 SubFlow 節點的 childFlowId"""
        if not graph or not isinstance(graph, dict):
            return []
        nodes = graph.get('nodes', [])
        child_ids = []
        for node in nodes:
            # 支援兩種格式: node.data.config 或 node.config
            node_data = node.get('data', {}) if isinstance(node.get('data'), dict) else {}
            node_type = (node_data.get('type') or node.get('type') or '').lower()
            if node_type == 'subflow':
                config = node_data.get('config') or node.get('config') or {}
                child_id = config.get('childFlowId')
                if child_id:
                    child_ids.append(child_id)
        return child_ids

    def build_tree_node(wf, depth=0, visited=None):
        """遞迴建構樹節點"""
        if visited is None:
            visited = set()
        if depth > 10 or wf.code in visited:
            return None
        visited.add(wf.code)

        node_count = len(wf.graph.get('nodes', [])) if wf.graph else 0
        tree_node = {
            'secure_code': wf.secure_code,
            'name': wf.name,
            'code': wf.code,
            'thumbnail_2x1': wf.thumbnail_2x1,
            'node_count': node_count,
            'is_subprocess': wf.is_subprocess,
            'children': []
        }

        # 提取子流程引用
        child_codes = extract_child_flow_ids(wf.graph)
        for code in child_codes:
            child_wf = subflow_by_code.get(code)
            if child_wf and child_wf.code not in visited:
                child_node = build_tree_node(child_wf, depth + 1, visited.copy())
                if child_node:
                    tree_node['children'].append(child_node)

        return tree_node

    # 為每個主流程建構樹，只保留有子流程引用的
    trees = []
    for mf in main_flows:
        child_codes = extract_child_flow_ids(mf.graph)
        if not child_codes:
            continue
        tree = build_tree_node(mf)
        if tree and tree['children']:
            trees.append(tree)

    # 按名稱排序
    trees.sort(key=lambda t: t['name'])

    return jsonify({
        'success': True,
        'data': {
            'trees': trees,
            'total': len(trees)
        }
    })


@api_bp.route('/workflows/flow-trees/<secure_code>')
@require_permission('form_workflow.workflow.view')
def get_flow_tree(secure_code):
    """取得單一主流程的樹系（主流程及其引用的子流程）"""
    from ..models import FwWorkflowTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    org_code = org.secure_code

    # 找到目標主流程
    target = FwWorkflowTemplate.query.filter_by(
        org_secure_code=org_code,
        secure_code=secure_code,
        is_deleted=False
    ).first()

    if not target:
        return jsonify({'success': False, 'error': '找不到此工作流'}), 404

    # 取得所有子流程建立映射
    all_subflows = FwWorkflowTemplate.query.filter_by(
        org_secure_code=org_code,
        is_subprocess=True,
        is_deleted=False
    ).all()
    subflow_by_code = {wf.code: wf for wf in all_subflows}

    def extract_child_flow_ids(graph):
        if not graph or not isinstance(graph, dict):
            return []
        nodes = graph.get('nodes', [])
        child_ids = []
        for node in nodes:
            node_data = node.get('data', {}) if isinstance(node.get('data'), dict) else {}
            node_type = (node_data.get('type') or node.get('type') or '').lower()
            if node_type == 'subflow':
                config = node_data.get('config') or node.get('config') or {}
                child_id = config.get('childFlowId')
                if child_id:
                    child_ids.append(child_id)
        return child_ids

    def build_tree_node(wf, depth=0, visited=None):
        if visited is None:
            visited = set()
        if depth > 10 or wf.code in visited:
            return None
        visited.add(wf.code)

        node_count = len(wf.graph.get('nodes', [])) if wf.graph else 0
        tree_node = {
            'secure_code': wf.secure_code,
            'name': wf.name,
            'code': wf.code,
            'thumbnail_2x1': wf.thumbnail_2x1,
            'node_count': node_count,
            'is_subprocess': wf.is_subprocess,
            'children': []
        }

        child_codes = extract_child_flow_ids(wf.graph)
        for code in child_codes:
            child_wf = subflow_by_code.get(code)
            if child_wf and child_wf.code not in visited:
                child_node = build_tree_node(child_wf, depth + 1, visited.copy())
                if child_node:
                    tree_node['children'].append(child_node)

        return tree_node

    tree = build_tree_node(target)

    return jsonify({
        'success': True,
        'data': {
            'tree': tree
        }
    })


@api_bp.route('/workflows/batch/delete', methods=['POST'])
@csrf.exempt
@require_permission('form_workflow.workflow.delete')
def batch_delete_workflows():
    """批次刪除工作流模板（軟刪除）"""
    from ..models import FwWorkflowTemplate
    from app import db

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    data = request.get_json() or {}
    secure_codes = data.get('secure_codes', [])
    if not secure_codes:
        return jsonify({'success': False, 'error': 'secure_codes is required'}), 400

    results = []
    succeeded = 0
    for sc in secure_codes:
        wf = FwWorkflowTemplate.query.filter_by(
            secure_code=sc, org_secure_code=org.secure_code, is_deleted=False
        ).first()
        if not wf:
            results.append({'secure_code': sc, 'success': False, 'message': '找不到流程'})
            continue
        wf.is_deleted = True
        results.append({'secure_code': sc, 'success': True, 'message': '已刪除'})
        succeeded += 1

    db.session.commit()
    return jsonify({
        'success': True,
        'results': results,
        'summary': {'total': len(secure_codes), 'succeeded': succeeded, 'failed': len(secure_codes) - succeeded}
    })


@api_bp.route('/workflows/batch/save-new-version', methods=['POST'])
@csrf.exempt
@require_permission('form_workflow.workflow.edit')
def batch_save_new_version_workflows():
    """批次另存新版工作流模板（複製出新記錄，版本號遞增）"""
    from ..models import FwWorkflowTemplate
    from app import db

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    data = request.get_json() or {}
    secure_codes = data.get('secure_codes', [])
    if not secure_codes:
        return jsonify({'success': False, 'error': 'secure_codes is required'}), 400

    results = []
    succeeded = 0
    for sc in secure_codes:
        wf = FwWorkflowTemplate.query.filter_by(
            secure_code=sc, org_secure_code=org.secure_code, is_deleted=False
        ).first()
        if not wf:
            results.append({'secure_code': sc, 'success': False, 'message': '找不到流程'})
            continue
        current_version = wf.version or 'AA'
        if len(current_version) >= 2:
            first, second = current_version[0], current_version[1]
            new_version = (chr(ord(first) + 1) + 'A') if second == 'Z' else (first + chr(ord(second) + 1))
        else:
            new_version = 'AA'
        new_wf = FwWorkflowTemplate(
            secure_code=secrets.token_urlsafe(16),
            org_secure_code=wf.org_secure_code,
            code=f'WF{secrets.token_hex(4).upper()}',
            name=wf.name,
            description=wf.description,
            category=wf.category,
            category_secure_code=wf.category_secure_code,
            graph=wf.graph,
            cytoscape_config=wf.cytoscape_config,
            version=new_version,
            revision=1,
            thumbnail_2x1=wf.thumbnail_2x1,
            thumbnail_1x1=wf.thumbnail_1x1,
            thumbnail_1x2=wf.thumbnail_1x2,
            is_active=wf.is_active,
            is_subprocess=wf.is_subprocess,
            owner_secure_code=current_user.secure_code,
        )
        db.session.add(new_wf)
        results.append({'secure_code': sc, 'success': True, 'message': f'已另存為版本 {new_version}', 'new_secure_code': new_wf.secure_code})
        succeeded += 1

    db.session.commit()
    return jsonify({
        'success': True,
        'results': results,
        'summary': {'total': len(secure_codes), 'succeeded': succeeded, 'failed': len(secure_codes) - succeeded}
    })


@api_bp.route('/workflows/<secure_code>', methods=['DELETE'])
@csrf.exempt
@require_permission('form_workflow.workflow.delete')
def delete_workflow(secure_code):
    """
    刪除工作流模板（軟刪除）

    Query Parameters:
        check: 若為 1，只回傳配對資訊不刪除（前端預檢用）
    """
    from ..models import FwWorkflowTemplate, FwFormWorkflowMapping, FwFormTemplate
    from app import db

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    workflow = FwWorkflowTemplate.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not workflow:
        return jsonify({'success': False, 'error': 'Workflow not found'}), 404

    # 查詢關聯的配對
    mappings = FwFormWorkflowMapping.query.filter_by(
        workflow_template_id=workflow.id,
        is_deleted=False
    ).all()

    # 預檢模式：回傳配對資訊
    if request.args.get('check') == '1':
        mapping_info = []
        if mappings:
            ft_ids = [m.form_template_id for m in mappings]
            ft_map = {}
            if ft_ids:
                fts = FwFormTemplate.query.filter(FwFormTemplate.id.in_(ft_ids)).all()
                ft_map = {f.id: f.name for f in fts}
            for m in mappings:
                mapping_info.append({
                    'form_name': ft_map.get(m.form_template_id, '未知表單'),
                    'is_published': m.is_published,
                })
        return jsonify({
            'success': True,
            'has_mappings': len(mappings) > 0,
            'mappings': mapping_info,
        })

    workflow.is_deleted = True
    db.session.commit()

    return jsonify({
        'success': True,
        'message': '工作流模板已刪除'
    })


# =============================================================================
# 表單實例 API
# =============================================================================

@api_bp.route('/instances')
@require_permission('form_workflow.form.view')
def list_instances():
    """取得表單實例列表（自己的）"""
    from ..models import FwFormInstance

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    # 只查看自己的表單，除非有 view_all 權限
    query = FwFormInstance.query.filter_by(
        org_secure_code=org.secure_code,
        is_deleted=False
    )

    if not has_permission('form_workflow.form.view_all'):
        query = query.filter_by(applicant_secure_code=current_user.secure_code)

    # 狀態篩選
    status = request.args.get('status')
    if status:
        query = query.filter_by(status=status)

    instances = query.order_by(FwFormInstance.created_at.desc()).limit(100).all()

    return jsonify({
        'success': True,
        'data': {
            'instances': [i.to_dict(include_form_data=False) for i in instances]
        }
    })


@api_bp.route('/instances/<secure_code>')
@require_permission('form_workflow.form.view')
def get_instance(secure_code):
    """取得單一表單實例"""
    from ..models import FwFormInstance

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    instance = FwFormInstance.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not instance:
        return jsonify({'success': False, 'error': 'Instance not found'}), 404

    # 檢查權限：只能查看自己的表單，除非有 view_all 權限
    if (instance.applicant_secure_code != current_user.secure_code and
        not has_permission('form_workflow.form.view_all')):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    return jsonify({
        'success': True,
        'data': instance.to_dict(include_form_data=True)
    })


# =============================================================================
# 待簽核任務 API
# =============================================================================

@api_bp.route('/pending-tasks')
@require_permission('form_workflow.form.approve')
def list_pending_tasks():
    """取得當前用戶的待簽核任務"""
    from ..models import FwNodeExecutionQueue, FwFormInstance

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    # 查詢等待簽核的節點（WAITING 狀態且類型為 Approve）
    tasks = FwNodeExecutionQueue.query.filter(
        FwNodeExecutionQueue.org_secure_code == org.secure_code,
        FwNodeExecutionQueue.status == 'WAITING',
        FwNodeExecutionQueue.node_type.in_(['Approve', 'FormAdapter'])
    ).order_by(FwNodeExecutionQueue.scheduled_at.asc()).all()

    user_code = current_user.secure_code
    result = []
    for task in tasks:
        # 檢查當前用戶是否為指定簽核人
        task_result_data = (task.result or {}).get('data', {})
        assignee_type = task_result_data.get('assignee_type')
        assignees = task_result_data.get('assignees', [])
        if assignee_type and user_code not in assignees:
            continue

        # 取得關聯的表單實例資訊
        form_instance = FwFormInstance.query.filter_by(
            secure_code=task.form_instance_secure_code
        ).first() if task.form_instance_secure_code else None

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
        'data': {
            'tasks': result
        }
    })


@api_bp.route('/pending-tasks/<secure_code>')
@require_permission('form_workflow.form.approve')
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
        return jsonify({'success': False, 'error': 'Task not found'}), 404

    # 檢查當前用戶是否為指定簽核人
    task_result_data = (task.result or {}).get('data', {})
    assignee_type = task_result_data.get('assignee_type')
    assignees = task_result_data.get('assignees', [])
    if assignee_type and current_user.secure_code not in assignees:
        return jsonify({'success': False, 'error': '您不是此任務的指定簽核人'}), 403

    # 取得關聯的表單實例
    form_instance = FwFormInstance.query.filter_by(
        secure_code=task.form_instance_secure_code
    ).first() if task.form_instance_secure_code else None

    # 取得可用的路徑（從節點配置）
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
            'form_name': form_instance.form_name if form_instance else None,
            'serial_number': form_instance.serial_number if form_instance else None,
            'available_paths': available_paths,
        }
    })


@api_bp.route('/pending-tasks/<secure_code>/approve', methods=['POST'])
@csrf.exempt
@require_permission('form_workflow.form.approve')
def approve_task(secure_code):
    """簽核任務"""
    from ..models import FwNodeExecutionQueue, FwApprovalRecord
    from ..services.workflow_engine import WorkflowEngine
    from app import db

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    task = FwNodeExecutionQueue.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        status='WAITING'
    ).first()

    if not task:
        return jsonify({'success': False, 'error': 'Task not found or already processed'}), 404

    # 檢查當前用戶是否為指定簽核人
    task_result_data = (task.result or {}).get('data', {})
    assignee_type = task_result_data.get('assignee_type')
    assignees = task_result_data.get('assignees', [])
    if assignee_type and current_user.secure_code not in assignees:
        return jsonify({'success': False, 'error': '您不是此任務的指定簽核人'}), 403

    data = request.get_json() or {}
    selected_path = data.get('selected_path')
    comment = data.get('comment', '')

    # 驗證簽核意見最少字數
    min_comment_length = task_result_data.get('min_comment_length', 0)
    if min_comment_length > 0 and len(comment.strip()) < min_comment_length:
        return jsonify({'success': False, 'error': f'簽核意見至少需要 {min_comment_length} 字'}), 400

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
        action='approved',
        comment=comment,
        acted_at=datetime.utcnow(),
    )
    db.session.add(approval_record)

    # 更新任務狀態
    task.status = 'SUCCESS'
    task.result = {
        'decision': 'approved',
        'selected_path': selected_path,
        'comment': comment,
        'approver': current_user.secure_code
    }

    db.session.commit()

    # 觸發工作流推進
    try:
        engine = WorkflowEngine()
        engine.advance_workflow(task.workflow_instance_secure_code, task.node_id, selected_path)
    except Exception as e:
        # 記錄錯誤但不回滾簽核
        import logging
        logging.error(f'Workflow advance error: {e}')

    return jsonify({
        'success': True,
        'message': '簽核完成'
    })


# =============================================================================
# 統計 API
# =============================================================================

@api_bp.route('/stats')
@require_permission('form_workflow.template.view')
def get_stats():
    """取得模組統計資訊"""
    from ..models import FwFormTemplate, FwWorkflowTemplate, FwFormInstance

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    org_code = org.secure_code

    template_count = FwFormTemplate.query.filter_by(
        org_secure_code=org_code, is_deleted=False
    ).count()

    workflow_count = FwWorkflowTemplate.query.filter_by(
        org_secure_code=org_code, is_deleted=False
    ).count()

    instance_count = FwFormInstance.query.filter_by(
        org_secure_code=org_code, is_deleted=False
    ).count()

    pending_count = FwFormInstance.query.filter_by(
        org_secure_code=org_code, is_deleted=False, status='PENDING'
    ).count()

    return jsonify({
        'success': True,
        'data': {
            'form_templates': template_count,
            'workflow_templates': workflow_count,
            'form_instances': instance_count,
            'pending_instances': pending_count,
        }
    })


# =============================================================================
# 額外的 Blueprint（用於與 A6 前端相容）
# =============================================================================

# 導入 workflows API Blueprint
from .workflows import workflows_bp

# 導入 forms API Blueprint
from .forms import forms_bp

# 導入 mappings API Blueprint
from .mappings import mappings_bp

# 導入 form_center API Blueprint
from .form_center import form_center_bp

# 導入 categories API Blueprint
from .categories import categories_bp

# 導入 backgrounds API Blueprint
from .backgrounds import backgrounds_bp

# 導出所有 Blueprint（供模組載入器使用）
additional_blueprints = [workflows_bp, forms_bp, mappings_bp, form_center_bp, categories_bp, backgrounds_bp]
