"""
FormWorkflow Module - Workflow Tree Service
流程樹系收集服務

提供子流程樹系的 BFS 收集功能，供匯出 API 和發行快照共用。
"""


def extract_child_flow_ids(graph):
    """
    從 graph JSON 提取所有 SubFlow 節點的 childFlowId

    Args:
        graph: 流程 graph dict，包含 nodes 和 edges

    Returns:
        set: childFlowId 的集合
    """
    result = set()
    if not graph or not isinstance(graph, dict):
        return result

    for node in graph.get('nodes', []):
        node_data = node.get('data', {}) if isinstance(node.get('data'), dict) else {}
        node_type = (node_data.get('type') or node.get('type') or '').lower()
        if node_type in ('subflow', 'subprocess'):
            config = node_data.get('config') or node.get('config') or {}
            child_id = config.get('childFlowId')
            if child_id:
                result.add(child_id)

    return result


def collect_sub_workflow_tree(main_graph, org_secure_code):
    """
    BFS 收集主流程引用的所有子流程（遞迴），去重回傳

    Args:
        main_graph: 主流程的 graph dict
        org_secure_code: 組織代碼

    Returns:
        dict: code → FwWorkflowTemplate 的映射
    """
    from ..models import FwWorkflowTemplate

    pending = extract_child_flow_ids(main_graph)
    visited = {}  # code → FwWorkflowTemplate

    while pending:
        code = pending.pop()
        if code in visited:
            continue

        subflow = FwWorkflowTemplate.query.filter_by(
            code=code,
            org_secure_code=org_secure_code,
            is_deleted=False
        ).first()

        if not subflow or not subflow.graph:
            continue

        visited[code] = subflow
        # 從子流程的 graph 繼續提取更深層的子流程
        deeper_ids = extract_child_flow_ids(subflow.graph)
        for deeper_code in deeper_ids:
            if deeper_code not in visited:
                pending.add(deeper_code)

    return visited
