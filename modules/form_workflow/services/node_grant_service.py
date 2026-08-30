"""
流程節點型別企業授權服務。

所有設計器可見性、graph 寫入驗證與 handler 執行期授權判定都應呼叫本服務。
"""
import logging
from typing import Set

from modules.form_workflow.models import WorkflowNodeDefinition, WorkflowNodeOrgGrant


logger = logging.getLogger(__name__)


def restricted_node_types() -> set:
    """回傳所有 org_restricted=True 且未刪除的 node_type。"""
    rows = WorkflowNodeDefinition.query.with_entities(
        WorkflowNodeDefinition.node_type
    ).filter(
        WorkflowNodeDefinition.org_restricted.is_(True),
        WorkflowNodeDefinition.is_deleted.is_(False),
    ).all()
    return {row[0] for row in rows if row[0]}


def is_node_allowed(node_type: str, org_secure_code: str) -> bool:
    """單一節點型別對單一企業是否可用。"""
    if not isinstance(org_secure_code, str) or not org_secure_code.strip():
        return False

    try:
        node_def = WorkflowNodeDefinition.query.filter(
            WorkflowNodeDefinition.node_type == node_type,
            WorkflowNodeDefinition.is_deleted.is_(False),
        ).first()
        if not node_def:
            # 定義不存在或已軟刪除 → fail-closed。handler 呼叫時 node_type 是
            # 固定常數，查不到代表定義被刪或 migration 未跑；此時放行等於
            # 授權閘門靜默失效。
            return False
        if not node_def.org_restricted:
            return True

        grant = WorkflowNodeOrgGrant.query.filter(
            WorkflowNodeOrgGrant.node_type == node_type,
            WorkflowNodeOrgGrant.org_secure_code == org_secure_code,
            WorkflowNodeOrgGrant.is_deleted.is_(False),
        ).first()
        return grant is not None
    except Exception:
        logger.exception('node grant check failed node_type=%s', node_type)
        return False


def allowed_restricted_types(org_secure_code: str) -> set:
    """該企業有授權的 restricted node_type 集合（給可見性過濾用，一次查完）。"""
    if not isinstance(org_secure_code, str) or not org_secure_code.strip():
        return set()

    try:
        restricted = restricted_node_types()
        if not restricted:
            return set()

        rows = WorkflowNodeOrgGrant.query.with_entities(
            WorkflowNodeOrgGrant.node_type
        ).filter(
            WorkflowNodeOrgGrant.node_type.in_(restricted),
            WorkflowNodeOrgGrant.org_secure_code == org_secure_code,
            WorkflowNodeOrgGrant.is_deleted.is_(False),
        ).all()
        return {row[0] for row in rows if row[0]}
    except Exception:
        logger.exception('allowed restricted node types check failed')
        return set()


def _node_types_in_graph(graph) -> Set[str]:
    if not isinstance(graph, dict):
        return set()
    nodes = graph.get('nodes')
    if not isinstance(nodes, list):
        return set()

    node_types = set()
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_type = node.get('type')
        if isinstance(node_type, str) and node_type:
            node_types.add(node_type)
    return node_types


def find_unauthorized_node_types(graph, org_secure_code: str) -> list:
    """
    掃 graph 內出現的 node type，回傳其中「屬於 restricted 且該企業沒有授權」的
    型別清單（排序後、去重）。
    """
    graph_types = _node_types_in_graph(graph)
    if not graph_types:
        return []

    try:
        restricted_in_graph = graph_types & restricted_node_types()
        if not restricted_in_graph:
            return []

        if not isinstance(org_secure_code, str) or not org_secure_code.strip():
            return sorted(restricted_in_graph)

        rows = WorkflowNodeOrgGrant.query.with_entities(
            WorkflowNodeOrgGrant.node_type
        ).filter(
            WorkflowNodeOrgGrant.node_type.in_(restricted_in_graph),
            WorkflowNodeOrgGrant.org_secure_code == org_secure_code,
            WorkflowNodeOrgGrant.is_deleted.is_(False),
        ).all()
        allowed = {row[0] for row in rows if row[0]}
        return sorted(restricted_in_graph - allowed)
    except Exception:
        logger.exception('unauthorized node type scan failed')
        return sorted(graph_types)
