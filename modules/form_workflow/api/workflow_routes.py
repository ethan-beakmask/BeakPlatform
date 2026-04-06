"""
FormWorkflow Module - Workflow API Routes
工作流模板 API

提供工作流模板的 CRUD、樹系查詢與批次操作。
"""
import secrets
from datetime import datetime, timezone
from flask import jsonify, request

from app import csrf, db
from app.security.decorators import module_access_required
from app.platform.auth import current_user, require_permission
from app.platform.data import get_current_org

from . import api_bp


@api_bp.route('/workflows')
@module_access_required('form_workflow')
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

    # flow_type 篩選（專屬子流程不在列表中顯示，只從樹系圖查看）
    flow_type = request.args.get('flow_type', '').strip().lower()
    if flow_type == 'main':
        query = query.filter(FwWorkflowTemplate.is_subprocess == False)
    elif flow_type == 'subflow':
        # 通用子流程：is_subprocess=True 且無父流程
        query = query.filter(
            FwWorkflowTemplate.is_subprocess == True,
            FwWorkflowTemplate.parent_workflow_secure_code == None
        )
    else:
        # 全部：排除專屬子流程
        from sqlalchemy import or_
        query = query.filter(
            or_(
                FwWorkflowTemplate.is_subprocess == False,
                FwWorkflowTemplate.parent_workflow_secure_code == None
            )
        )

    workflows = query.order_by(FwWorkflowTemplate.updated_at.desc()).all()

    # 查詢每個流程的配對數量
    from sqlalchemy import func
    mapping_counts = dict(
        db.session.query(
            FwFormWorkflowMapping.workflow_template_id,
            func.count(FwFormWorkflowMapping.id)
        ).filter_by(
            org_secure_code=org.secure_code, is_deleted=False
        ).group_by(FwFormWorkflowMapping.workflow_template_id).all()
    )

    # 收集專屬子流程的父流程名稱
    parent_codes = set()
    for w in workflows:
        if w.parent_workflow_secure_code:
            parent_codes.add(w.parent_workflow_secure_code)

    parent_names = {}
    if parent_codes:
        parents = FwWorkflowTemplate.query.filter(
            FwWorkflowTemplate.secure_code.in_(parent_codes),
            FwWorkflowTemplate.org_secure_code == org.secure_code
        ).all()
        parent_names = {p.secure_code: p.name for p in parents}

    # 專屬子流程計數（per parent workflow）
    dedicated_counts = dict(
        db.session.query(
            FwWorkflowTemplate.parent_workflow_secure_code,
            func.count(FwWorkflowTemplate.id)
        ).filter(
            FwWorkflowTemplate.org_secure_code == org.secure_code,
            FwWorkflowTemplate.is_deleted == False,
            FwWorkflowTemplate.is_subprocess == True,
            FwWorkflowTemplate.parent_workflow_secure_code != None
        ).group_by(FwWorkflowTemplate.parent_workflow_secure_code).all()
    )

    # 通用子流程計數：解析每個流程 graph 中的 SubFlow 節點
    all_child_codes = set()
    workflow_child_flows = {}
    for w in workflows:
        child_codes = []
        if w.graph:
            for node in w.graph.get('nodes', []):
                node_data = node.get('data', {})
                node_type = (node_data.get('type') or node.get('type') or '').lower()
                if node_type == 'subflow':
                    config = node_data.get('config') or node.get('config') or {}
                    child_id = config.get('childFlowId')
                    if child_id:
                        child_codes.append(child_id)
                        all_child_codes.add(child_id)
        workflow_child_flows[w.secure_code] = child_codes

    # 批次查詢哪些是通用子流程
    common_sf_codes = set()
    if all_child_codes:
        common_sfs = FwWorkflowTemplate.query.filter(
            FwWorkflowTemplate.code.in_(all_child_codes),
            FwWorkflowTemplate.org_secure_code == org.secure_code,
            FwWorkflowTemplate.is_deleted == False,
            FwWorkflowTemplate.is_subprocess == True,
            FwWorkflowTemplate.parent_workflow_secure_code == None
        ).all()
        common_sf_codes = {sf.code for sf in common_sfs}

    # 專屬子流程 code 清單（per parent workflow），用於計算未用數
    dedicated_sf_codes = {}
    dedicated_sfs = FwWorkflowTemplate.query.filter(
        FwWorkflowTemplate.org_secure_code == org.secure_code,
        FwWorkflowTemplate.is_deleted == False,
        FwWorkflowTemplate.is_subprocess == True,
        FwWorkflowTemplate.parent_workflow_secure_code != None
    ).all()
    for sf in dedicated_sfs:
        dedicated_sf_codes.setdefault(sf.parent_workflow_secure_code, set()).add(sf.code)

    # 建立 code → [引用的 childFlowId] 映射（所有子流程）
    sf_graph_refs = {}
    for sf in dedicated_sfs:
        refs = []
        if sf.graph:
            for node in sf.graph.get('nodes', []):
                node_data = node.get('data', {})
                node_type = (node_data.get('type') or node.get('type') or '').lower()
                if node_type == 'subflow':
                    config = node_data.get('config') or node.get('config') or {}
                    child_id = config.get('childFlowId')
                    if child_id:
                        refs.append(child_id)
        sf_graph_refs[sf.code] = refs

    def _reachable_codes(root_child_codes):
        """BFS：從主流程直接引用的 codes 出發，遞迴收集所有可達的子流程 codes"""
        reachable = set()
        queue = list(root_child_codes)
        while queue:
            code = queue.pop()
            if code in reachable:
                continue
            reachable.add(code)
            for ref in sf_graph_refs.get(code, []):
                if ref not in reachable:
                    queue.append(ref)
        return reachable

    result = []
    for w in workflows:
        d = w.to_dict(include_graph=False)
        d['mapping_count'] = mapping_counts.get(w.id, 0)
        d['parent_workflow_name'] = parent_names.get(w.parent_workflow_secure_code) if w.parent_workflow_secure_code else None
        d['dedicated_subflow_count'] = dedicated_counts.get(w.secure_code, 0)
        child_codes = workflow_child_flows.get(w.secure_code, [])
        d['common_subflow_count'] = len([c for c in child_codes if c in common_sf_codes])
        # 未用專屬子流程：從主流程 BFS 不可達的專屬子流程
        my_dedicated_codes = dedicated_sf_codes.get(w.secure_code, set())
        reachable = _reachable_codes(child_codes)
        d['unused_subflow_count'] = len(my_dedicated_codes - reachable)
        result.append(d)

    return jsonify({
        'success': True,
        'data': {
            'workflows': result
        }
    })


@api_bp.route('/workflows/<secure_code>')
@module_access_required('form_workflow')
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
@module_access_required('form_workflow')
@require_permission('form_workflow.workflow.create')
def create_workflow():
    """建立工作流模板"""
    from ..models import FwWorkflowTemplate

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
        category_secure_code=data.get('category_secure_code') or 'SYS_CAT_WORKFLOW_REC',
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
@module_access_required('form_workflow')
@require_permission('form_workflow.workflow.edit')
def update_workflow(secure_code):
    """更新工作流模板"""
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

    db.session.commit()

    return jsonify({
        'success': True,
        'data': workflow.to_dict(include_graph=True),
        'message': '工作流模板已更新'
    })


@api_bp.route('/workflows/flow-trees')
@module_access_required('form_workflow')
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


@api_bp.route('/workflows/<secure_code>/unused-subflows')
@module_access_required('form_workflow')
@require_permission('form_workflow.workflow.view')
def get_unused_subflows(secure_code):
    """取得指定主流程的未使用專屬子流程清單（含縮圖）"""
    from ..models import FwWorkflowTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    target = FwWorkflowTemplate.query.filter_by(
        org_secure_code=org.secure_code,
        secure_code=secure_code,
        is_deleted=False
    ).first()
    if not target:
        return jsonify({'success': False, 'error': '找不到此工作流'}), 404

    # 收集整棵樹中所有被引用的子流程 codes（遞迴掃描所有層級的 graph）
    used_codes = set()

    def collect_used_codes(wf):
        """遞迴掃描 workflow 及其子流程的 graph，收集所有被引用的 childFlowId"""
        if not wf.graph:
            return
        for node in wf.graph.get('nodes', []):
            node_data = node.get('data', {}) if isinstance(node.get('data'), dict) else {}
            node_type = (node_data.get('type') or node.get('type') or '').lower()
            if node_type == 'subflow':
                config = node_data.get('config') or node.get('config') or {}
                child_id = config.get('childFlowId')
                if child_id and child_id not in used_codes:
                    used_codes.add(child_id)
                    # 遞迴掃描被引用的子流程
                    child_wf = FwWorkflowTemplate.query.filter_by(
                        code=child_id,
                        org_secure_code=org.secure_code,
                        is_deleted=False
                    ).first()
                    if child_wf:
                        collect_used_codes(child_wf)

    collect_used_codes(target)

    # 查詢所有專屬子流程
    dedicated_sfs = FwWorkflowTemplate.query.filter_by(
        org_secure_code=org.secure_code,
        parent_workflow_secure_code=secure_code,
        is_subprocess=True,
        is_deleted=False
    ).all()

    # 過濾出未被整棵樹引用的
    unused = [sf for sf in dedicated_sfs if sf.code not in used_codes]

    result = []
    for sf in unused:
        node_count = len(sf.graph.get('nodes', [])) if sf.graph else 0
        result.append({
            'secure_code': sf.secure_code,
            'name': sf.name,
            'code': sf.code,
            'thumbnail_2x1': sf.thumbnail_2x1,
            'node_count': node_count,
            'updated_at': sf.updated_at.isoformat() if sf.updated_at else None
        })

    return jsonify({
        'success': True,
        'data': {
            'workflow_name': target.name,
            'workflow_code': target.code,
            'subflows': result
        }
    })


@api_bp.route('/workflows/<secure_code>/flow-overview')
@module_access_required('form_workflow')
@require_permission('form_workflow.workflow.view')
def get_workflow_flow_overview(secure_code):
    """取得工作流模板的流程總圖資料（主流程 graph + 所有子流程 graph，供 Cytoscape 渲染）"""
    from ..models import FwWorkflowTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    org_code = org.secure_code

    target = FwWorkflowTemplate.query.filter_by(
        org_secure_code=org_code,
        secure_code=secure_code,
        is_deleted=False
    ).first()

    if not target:
        return jsonify({'success': False, 'error': '找不到此工作流'}), 404

    # 收集所有可用的子流程（同企業）
    all_subflows = FwWorkflowTemplate.query.filter_by(
        org_secure_code=org_code,
        is_subprocess=True,
        is_deleted=False
    ).all()
    code_to_wf = {wf.code: wf for wf in all_subflows}

    # 遞迴收集所有被引用的子流程 code
    def collect_referenced_codes(graph, visited=None):
        if visited is None:
            visited = set()
        if not graph:
            return visited
        for node in graph.get('nodes', []):
            node_type = (node.get('type') or '').lower()
            if node_type == 'subflow':
                config = node.get('config') or {}
                child_id = config.get('childFlowId')
                if child_id and child_id not in visited:
                    visited.add(child_id)
                    child_wf = code_to_wf.get(child_id)
                    if child_wf and child_wf.graph:
                        collect_referenced_codes(child_wf.graph, visited)
        return visited

    referenced_codes = collect_referenced_codes(target.graph)

    # 組裝 workflow_tabs（與 fc_monitor 的 execution path 格式相容）
    workflow_tabs = [{
        'workflow_code': target.code,
        'name': target.name,
        'is_main': True,
        'graph': target.graph or {}
    }]

    for code in referenced_codes:
        wf = code_to_wf.get(code)
        if wf:
            workflow_tabs.append({
                'workflow_code': wf.code,
                'name': wf.name,
                'is_main': False,
                'graph': wf.graph or {}
            })

    return jsonify({
        'success': True,
        'data': {
            'workflow_tabs': workflow_tabs,
            'workflow_name': target.name,
            'workflow_code': target.code
        }
    })


@api_bp.route('/workflows/flow-trees/<secure_code>')
@module_access_required('form_workflow')
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

    # 收集樹中已出現的子流程 code（graph 有引用的）
    used_codes_in_tree = set()
    def collect_codes(node):
        used_codes_in_tree.add(node.get('code', ''))
        for ch in node.get('children', []):
            collect_codes(ch)
    collect_codes(tree)

    # 追加未引用的專屬子流程（標記 is_unused）
    dedicated_sfs = FwWorkflowTemplate.query.filter_by(
        org_secure_code=org_code,
        parent_workflow_secure_code=secure_code,
        is_subprocess=True,
        is_deleted=False
    ).all()
    for sf in dedicated_sfs:
        if sf.code not in used_codes_in_tree:
            nc = len(sf.graph.get('nodes', [])) if sf.graph else 0
            tree['children'].append({
                'secure_code': sf.secure_code,
                'name': sf.name,
                'code': sf.code,
                'thumbnail_2x1': sf.thumbnail_2x1,
                'node_count': nc,
                'is_subprocess': True,
                'is_unused': True,
                'children': []
            })

    return jsonify({
        'success': True,
        'data': {
            'tree': tree
        }
    })


@api_bp.route('/workflows/batch/delete', methods=['POST'])
@csrf.exempt
@module_access_required('form_workflow')
@require_permission('form_workflow.workflow.delete')
def batch_delete_workflows():
    """批次刪除工作流模板（軟刪除）"""
    from ..models import FwWorkflowTemplate

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


@api_bp.route('/workflows/batch/export', methods=['POST'])
@csrf.exempt
@module_access_required('form_workflow')
@require_permission('form_workflow.workflow.view')
def batch_export_workflows():
    """批次匯出工作流模板（含子流程樹系收集）"""
    from ..models import FwWorkflowTemplate
    from ..services.workflow_tree import collect_sub_workflow_tree

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    data = request.get_json() or {}
    secure_codes = data.get('secure_codes', [])
    if not secure_codes:
        return jsonify({'success': False, 'error': 'secure_codes is required'}), 400

    items = []
    for sc in secure_codes:
        wf = FwWorkflowTemplate.query.filter_by(
            secure_code=sc, org_secure_code=org.secure_code, is_deleted=False
        ).first()
        if not wf:
            continue

        # 遞迴收集子流程樹
        sub_workflows = {}
        if wf.graph:
            collected = collect_sub_workflow_tree(wf.graph, org.secure_code)
            for code, sf in collected.items():
                sub_workflows[code] = {
                    'code': sf.code,
                    'name': sf.name,
                    'description': sf.description,
                    'graph': sf.graph,
                    'cytoscape_config': sf.cytoscape_config,
                    'is_subprocess': sf.is_subprocess,
                }

        items.append({
            'code': wf.code,
            'name': wf.name,
            'description': wf.description,
            'graph': wf.graph,
            'cytoscape_config': wf.cytoscape_config,
            'is_subprocess': wf.is_subprocess,
            'sub_workflows': sub_workflows,
        })

    return jsonify({
        'success': True,
        'data': {
            'export_type': 'workflows',
            'exported_at': datetime.now(timezone.utc).isoformat(),
            'count': len(items),
            'items': items,
        }
    })


@api_bp.route('/workflows/batch/import', methods=['POST'])
@csrf.exempt
@module_access_required('form_workflow')
@require_permission('form_workflow.workflow.create')
def batch_import_workflows():
    """批次匯入工作流模板（JSON）

    讀取 export 格式的 JSON，先建子流程再建主流程。
    code 重複則跳過。category_secure_code 不存在則歸預設。
    """
    from ..models import FwWorkflowTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    data = request.get_json() or {}

    # 防呆：檢查 export_type
    export_type = data.get('export_type', '')
    if export_type and export_type != 'workflows':
        return jsonify({'success': False, 'error': f'檔案類型不符：期望 workflows，實際為 {export_type}'}), 400

    items = data.get('items', [])
    if not items:
        return jsonify({'success': False, 'error': 'items is required'}), 400

    def _is_valid_workflow_code(code):
        """流程 code 必須以 WF 或 SF 開頭"""
        c = code.upper()
        return c.startswith('WF') or c.startswith('SF')

    # 預載現有 code 集合
    existing_codes = set(
        r[0] for r in db.session.query(FwWorkflowTemplate.code).filter_by(
            org_secure_code=org.secure_code, is_deleted=False
        ).all()
    )

    # 預載有效 category_secure_code 集合
    from ..models import FwCategory
    valid_cats = set(
        r[0] for r in db.session.query(FwCategory.secure_code).filter_by(
            org_secure_code=org.secure_code, is_deleted=False
        ).all()
    )

    default_cat_code = 'SYS_CAT_WORKFLOW_REC'

    results = []
    created = 0
    skipped = 0

    for item in items:
        # 先匯入 sub_workflows
        sub_workflows = item.get('sub_workflows') or {}
        for sf_code, sf_data in sub_workflows.items():
            sf_code_clean = (sf_data.get('code') or sf_code).strip()
            if not sf_code_clean or sf_code_clean in existing_codes:
                continue
            if not _is_valid_workflow_code(sf_code_clean):
                continue

            sf = FwWorkflowTemplate(
                secure_code=secrets.token_urlsafe(16),
                org_secure_code=org.secure_code,
                code=sf_code_clean,
                name=sf_data.get('name', sf_code_clean),
                description=sf_data.get('description', ''),
                category_secure_code=default_cat_code,
                graph=sf_data.get('graph') or {'nodes': [], 'edges': []},
                cytoscape_config=sf_data.get('cytoscape_config'),
                is_active=True,
                is_subprocess=True,
                owner_secure_code=current_user.secure_code,
            )
            db.session.add(sf)
            existing_codes.add(sf_code_clean)

        # 再匯入主流程
        code = (item.get('code') or '').strip()
        if not code:
            results.append({'code': code, 'status': 'skipped', 'reason': '缺少 code'})
            skipped += 1
            continue

        # 防呆：流程 code 必須以 WF 或 SF 開頭
        if not _is_valid_workflow_code(code):
            results.append({'code': code, 'status': 'skipped', 'reason': 'code 格式不符（需 WF 或 SF 開頭）'})
            skipped += 1
            continue

        if code in existing_codes:
            results.append({'code': code, 'status': 'skipped', 'reason': 'code 已存在'})
            skipped += 1
            continue

        cat_code = item.get('category_secure_code') or default_cat_code
        if cat_code not in valid_cats:
            cat_code = default_cat_code

        wf = FwWorkflowTemplate(
            secure_code=secrets.token_urlsafe(16),
            org_secure_code=org.secure_code,
            code=code,
            name=item.get('name', code),
            description=item.get('description', ''),
            category_secure_code=cat_code,
            graph=item.get('graph') or {'nodes': [], 'edges': []},
            cytoscape_config=item.get('cytoscape_config'),
            is_active=True,
            is_subprocess=item.get('is_subprocess', False),
            owner_secure_code=current_user.secure_code,
        )
        db.session.add(wf)
        existing_codes.add(code)
        results.append({'code': code, 'status': 'created', 'sub_workflows': list(sub_workflows.keys())})
        created += 1

    db.session.commit()

    return jsonify({
        'success': True,
        'summary': {'total': len(items), 'created': created, 'skipped': skipped},
        'results': results,
    })


@api_bp.route('/workflows/batch/save-new-version', methods=['POST'])
@csrf.exempt
@module_access_required('form_workflow')
@require_permission('form_workflow.workflow.edit')
def batch_save_new_version_workflows():
    """批次另存新版工作流模板（複製出新記錄，版本號遞增）"""
    from ..models import FwWorkflowTemplate

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
@module_access_required('form_workflow')
@require_permission('form_workflow.workflow.delete')
def delete_workflow(secure_code):
    """
    刪除工作流模板（軟刪除）

    刪除邏輯：
    - 遞迴軟刪除所有專屬子流程（有 parent_workflow_secure_code 的）
    - 連帶軟刪除相關的表單-流程配對（fw_form_workflow_mappings）
    - 通用子流程（parent_workflow_secure_code 為 NULL）不受影響
    - 已發行版本（有快照）和歷史實例保留不動
    - 若有運行中的流程實例則阻擋刪除

    Query Parameters:
        check: 若為 1，只回傳影響範圍不刪除（前端預檢用）
    """
    from ..models import (
        FwWorkflowTemplate, FwFormWorkflowMapping, FwFormTemplate,
        FwWorkflowInstance
    )

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

    # 遞迴收集所有專屬子流程（BFS）
    exclusive_subflows = []
    queue_bfs = [workflow.secure_code]
    visited = {workflow.secure_code}
    while queue_bfs:
        parent_code = queue_bfs.pop(0)
        children = FwWorkflowTemplate.query.filter_by(
            parent_workflow_secure_code=parent_code,
            org_secure_code=org.secure_code,
            is_deleted=False
        ).all()
        for child in children:
            if child.secure_code not in visited:
                visited.add(child.secure_code)
                exclusive_subflows.append(child)
                queue_bfs.append(child.secure_code)

    # 要刪除的所有 secure_code（主流程 + 專屬子流程）
    all_codes = [workflow.secure_code] + [sf.secure_code for sf in exclusive_subflows]

    # 查詢所有相關配對
    mappings = FwFormWorkflowMapping.query.filter(
        FwFormWorkflowMapping.workflow_template_secure_code.in_(all_codes),
        FwFormWorkflowMapping.org_secure_code == org.secure_code,
        FwFormWorkflowMapping.is_deleted == False
    ).all()

    # 預檢模式：回傳影響範圍
    if request.args.get('check') == '1':
        # 檢查運行中實例
        running_count = FwWorkflowInstance.query.filter(
            FwWorkflowInstance.workflow_template_secure_code.in_(all_codes),
            FwWorkflowInstance.org_secure_code == org.secure_code,
            FwWorkflowInstance.status.in_(['PENDING', 'RUNNING']),
            FwWorkflowInstance.is_deleted == False
        ).count()

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

        subflow_info = [{'name': sf.name, 'code': sf.code} for sf in exclusive_subflows]

        return jsonify({
            'success': True,
            'has_mappings': len(mappings) > 0,
            'mappings': mapping_info,
            'exclusive_subflows': subflow_info,
            'running_instances': running_count,
        })

    # 檢查運行中實例
    running_count = FwWorkflowInstance.query.filter(
        FwWorkflowInstance.workflow_template_secure_code.in_(all_codes),
        FwWorkflowInstance.org_secure_code == org.secure_code,
        FwWorkflowInstance.status.in_(['PENDING', 'RUNNING']),
        FwWorkflowInstance.is_deleted == False
    ).count()

    if running_count > 0:
        return jsonify({
            'success': False,
            'error': f'無法刪除：尚有 {running_count} 個運行中的流程實例'
        }), 409

    now = datetime.utcnow()

    # 軟刪除主流程
    workflow.is_deleted = True
    workflow.updated_at = now

    # 軟刪除所有專屬子流程
    for sf in exclusive_subflows:
        sf.is_deleted = True
        sf.updated_at = now

    # 軟刪除相關的表單-流程配對
    for mapping in mappings:
        mapping.is_deleted = True
        mapping.updated_at = now

    db.session.commit()

    deleted_names = [workflow.name] + [sf.name for sf in exclusive_subflows]

    return jsonify({
        'success': True,
        'message': '工作流模板已刪除',
        'details': {
            'deleted_workflows': deleted_names,
            'deleted_mappings': len(mappings)
        }
    })
