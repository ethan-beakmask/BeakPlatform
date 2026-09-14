"""
流程節點型別企業授權服務。

所有設計器可見性、graph 寫入驗證與 handler 執行期授權判定都應呼叫本服務。
"""
import logging
from datetime import datetime
from typing import Set

from app import db
from app.models import Organization
from modules.form_workflow.models import WorkflowNodeDefinition, WorkflowNodeOrgGrant


logger = logging.getLogger(__name__)


class NodeGrantError(ValueError):
    """授權操作的可辨識錯誤。code 是機器可讀字串，不要包翻譯函式。"""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _restricted_node_or_error(node_type):
    node_def = WorkflowNodeDefinition.query.filter(
        WorkflowNodeDefinition.node_type == node_type,
        WorkflowNodeDefinition.is_deleted.is_(False),
    ).first()
    if not node_def:
        raise NodeGrantError('node_not_found', f'找不到節點型別：{node_type}')
    if not node_def.org_restricted:
        raise NodeGrantError('node_not_restricted', f'節點型別不是 restricted：{node_type}')
    return node_def


def _org_or_error(org_secure_code):
    org = Organization.query.filter(
        Organization.secure_code == org_secure_code,
        Organization.is_deleted.is_(False),
    ).first()
    if not org:
        raise NodeGrantError('org_not_found', f'找不到企業：{org_secure_code}')
    return org


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


def find_runtime_denial(node_type: str, org_secure_code: str):
    """執行期統一守門（node_runner 在 validate() 之前呼叫，PF-194）。

    只擋「restricted 且該企業未授權」；定義不存在或已軟刪除的節點一律回 None——
    退役節點（如 ParallelFork）仍存在於既有發行快照，這裡擋了會弄壞既有流程。
    查詢失敗也回 None，fail-closed 的最後防線是各受限 handler 內的
    is_node_allowed()（那邊對定義消失與查詢失敗都拒絕）。

    Returns:
        未授權時回傳訊息字串（與 handler 內的訊息一致），可用時回傳 None。
    """
    try:
        node_def = WorkflowNodeDefinition.query.filter(
            WorkflowNodeDefinition.node_type == node_type,
            WorkflowNodeDefinition.is_deleted.is_(False),
        ).first()
        if not node_def or not node_def.org_restricted:
            return None

        if isinstance(org_secure_code, str) and org_secure_code.strip():
            grant = WorkflowNodeOrgGrant.query.filter(
                WorkflowNodeOrgGrant.node_type == node_type,
                WorkflowNodeOrgGrant.org_secure_code == org_secure_code,
                WorkflowNodeOrgGrant.is_deleted.is_(False),
            ).first()
            if grant is not None:
                return None
        return f'企業未取得 {node_type} 節點授權'
    except Exception:
        logger.exception('runtime node grant precheck failed node_type=%s', node_type)
        return None


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


def grant_node_to_org(
    node_type,
    org_secure_code,
    granted_by_secure_code=None,
    granted_by_name=None,
    note=None,
) -> bool:
    """授權企業使用 restricted 節點型別。已授權時不重複建立，回傳 changed(bool)。"""
    try:
        _restricted_node_or_error(node_type)
        _org_or_error(org_secure_code)

        existing = WorkflowNodeOrgGrant.query.filter(
            WorkflowNodeOrgGrant.node_type == node_type,
            WorkflowNodeOrgGrant.org_secure_code == org_secure_code,
            WorkflowNodeOrgGrant.is_deleted.is_(False),
        ).first()
        if existing:
            return False

        grant = WorkflowNodeOrgGrant(
            node_type=node_type,
            org_secure_code=org_secure_code,
            granted_by_secure_code=granted_by_secure_code,
            granted_by_name=granted_by_name,
            note=note,
        )
        db.session.add(grant)
        db.session.commit()
        return True
    except NodeGrantError:
        raise
    except Exception:
        db.session.rollback()
        logger.exception(
            'grant node to org failed node_type=%s org_secure_code=%s',
            node_type,
            org_secure_code,
        )
        raise


def revoke_node_from_org(node_type, org_secure_code) -> bool:
    """軟刪除授權。沒有可撤銷的授權時回傳 False。"""
    try:
        _restricted_node_or_error(node_type)
        _org_or_error(org_secure_code)

        grant = WorkflowNodeOrgGrant.query.filter(
            WorkflowNodeOrgGrant.node_type == node_type,
            WorkflowNodeOrgGrant.org_secure_code == org_secure_code,
            WorkflowNodeOrgGrant.is_deleted.is_(False),
        ).first()
        if not grant:
            return False

        grant.is_deleted = True
        grant.deleted_at = datetime.utcnow()
        grant.updated_at = datetime.utcnow()
        db.session.commit()
        return True
    except NodeGrantError:
        raise
    except Exception:
        db.session.rollback()
        logger.exception(
            'revoke node from org failed node_type=%s org_secure_code=%s',
            node_type,
            org_secure_code,
        )
        raise
